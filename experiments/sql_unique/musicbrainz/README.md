# MusicBrainz: filtered unique indexes in an open-data PostgreSQL application (2026-10-28)

## Sources

All sources are read only.
- **Data:** `fullexport/20261028-002228/mbdump.tar.bz2` from data.metabrainz.org (7 GB, CC0).
  - SHA-256 verified: `641c8c4a…ef83c`.
  - Dump timestamp 2026-10-28 00:22 UTC, schema sequence 31.
  - 19 tables are extracted (2.8 GB). `mood_alias` is not in the core dump.
- **Schema:** `admin/sql` of metabrainz/musicbrainz-server, `production` branch at c295efc (2026-10-21). It is applied as SQL by `load_mb.sh`; no MusicBrainz code is run.
- **Workload:**
  - the MusicBrainz server's Perl data modules, read only;
  - ListenBrainz (metabrainz/listenbrainz-server, 7b7dfc8, 2026-10-27): 20 queries extracted statically by `extract_lb.py` (Python `ast`, nothing imported or executed).

## Scripts

1. `load_mb.sh BIN PORT SQLDIR DUMPDIR|- DB` builds the core schema in the order of `admin/InitDb.pl`:
   - core schema only;
   - no triggers, replication, CHECK/FK constraints or other schemas;
   - the ICU collation is replaced by a deterministic C collation, since this build has no ICU. This changes order, not equality.
2. `load_tables.sh BIN PORT DUMPDIR DB TABLE…` loads the selected tables into it.
3. `mb_plan.py DSN` plans the ListenBrainz queries and 10 constructed consumer queries with the setting off and on. Output: `mb_plan.json` on the loaded data, and `mb_plan_empty.json` on the empty schema.
4. `mb_stats.py DSN` writes `mb_stats.json`:
   - for each filtered index: rows, rows in scope, and a check that the key is unique in the scope;
   - for each constructed query whose plan changes: timing (10 alternating rounds after a warm-up) and result equality in one transaction.

## Results

**The 17 filtered unique indexes**
- **13 alias tables:** `(entity, locale) WHERE primary_for_locale = TRUE AND locale IS NOT NULL`.
- **Artist and label:** `(name) WHERE comment IS NULL` and `(name, comment) WHERE comment IS NOT NULL`.
  - This is the U= encoding by two nulls-distinct indexes (Proposition "Translation").
  - `comment` is now `NOT NULL DEFAULT ''`. So `*_idx_null_comment` covers 0 rows and `*_idx_uniq_name_comment` is an unconditional key; stock PostgreSQL ignores it for being partial.

| Index | Rows | Scope | Duplicates |
|---|---|---|---|
| artist_alias_idx_primary | 549,381 | 65,658 (12.0%) | 0 |
| recording_alias_idx_primary | 1,083,860 | 45,218 (4.2%) | 0 |
| work_alias_idx_primary | 163,707 | 36,418 (22.2%) | 0 |
| area_alias_idx_primary | 67,911 | 66,673 (98.2%) | 0 |
| artist_idx_null_comment | 3,026,026 | 0 | 0 |
| artist_idx_uniq_name_comment | 3,026,026 | 3,026,026 | 0 |
| … (all 16 loaded) | | | 0 |

**Workload**
- **MusicBrainz server:** no query filters on `primary_for_locale`. The primary alias is chosen in Perl (`Data/Alias.pm` orders by it; `Data/Utils.pm` picks it). The only join to an alias table (`instrument_alias`) has no primary filter.
- **ListenBrainz:** none of the 20 queries filters on any scope; they reach artists by id. 5 plan on the core schema and none changes. 15 need cover-art or ListenBrainz's own `mapping` tables, or have parameters our placeholders do not fit.
- **MetaBrainz forum (users, 2026-10-29):** `mb_forum.py CACHE` searched community.metabrainz.org (15 Discourse searches, read only, 1.5 s apart, generic crawler name) and kept fenced code blocks that SELECT from MusicBrainz tables: 67 blocks from 41 of 2,736 topics (`forum_queries.json`, log `log_mb_forum.txt`). `mb_forum_plan.py DSN` splits them into 35 distinct SELECTs; 15 plan (20 are fragments, or need cover-art, edit or user tables). None filters on a filtered key's scope; 2 get a proof, and no plan changes (`mb_forum_plan.json`, `log_mb_forum_plan.txt`).
- **Constructed consumer queries (ours):** with CHECK premises (2026-10-29), 9 of 10 get a proof and change plan with the costing hint on; 7 under the default.
  - `SELECT DISTINCT artist, locale FROM artist_alias WHERE primary_for_locale` uses the CHECK `(locale IS NULL AND NOT primary_for_locale) OR locale IS NOT NULL`. Before CHECK premises it was the one miss.
  - The tenth (labels grouped by name and comment) needs nothing: `label.id` is already in the key.
  - Earlier numbers are in `mb_plan_before_check.json` and `mb_stats_before_check.json`.

Under the default (costing hint off, 2026-10-29; `mb_stats.json`, log `log_mb_stats.txt`). The rows marked * keep the stock plan under the default; the hint changes them. The earlier run with the hint on is in `mb_stats_costing.json`.

| Query | Off (ms) | On (ms) | Speed-up | With hint (earlier) |
|---|---|---|---|---|
| distinct artist names and comments (legacy key) | 2,123.9 | 430.3 | 4.94× | 4.84× |
| artist list, alias join unused | 1,588.8 | 443.4 | 3.58× | 2.88× |
| primary aliases with `locale IS NOT NULL` | 6.3 | 2.4 | 2.58× | 2.51× |
| primary aliases per artist and locale (via CHECK) | 44.6 | 29.8 | 1.50× | 1.32× |
| credits per artist grouped with alias | 192.7 | 140.2 | 1.37× | 1.35× |
| distinct artists with primary English alias | 54.4 | 46.8 | 1.16× | 1.16× |
| works via IN on the alias scope | 1.5 | 1.3 | 1.15× | 1.09× |
| artist with primary English alias * | 1,055.6 | 1,078.8 | (0.98×) | 1.83× |
| releases with release-group primary alias (ja) * | 3,726.8 | 3,686.2 | (1.01×) | 1.24× |

All results are identical with the setting off and on.
