# Wikimedia Quarry and wiki dumps (2026-10-29)

## Sources (all read as data; nothing in them is executed)
- **Queries:** Hugging Face dataset `htriedman/wikidb` (`data/train-00000-of-00001-7bf87dd1694d6fef.parquet`, 8.3 MB).
  - It holds 25,555 Quarry queries with title, wiki and SQL. It was built for Wikimedia's task T337019 ("Build dataset of Quarry queries", resolved June 2023), whose stated licence for Quarry SQL is CC0. The dataset card itself is empty.
  - Quarry's own interface needs a Wikimedia login, so it was not used.
- **Schema:** MediaWiki REL1_40 `maintenance/postgres/tables-generated.sql`, the release current when the dataset was built. It loads as database `wiki` on port 5444 (58 tables).
  - The schema itself declares one filtered unique index: `page_props (pp_propname, pp_sortkey, pp_page) WHERE pp_sortkey IS NOT NULL`. It excludes only null keys.
- **Data:** `dumps.wikimedia.org` SQL dumps (`*-latest-*.sql.gz`) of 16 tables of Simple English Wikipedia (simplewiki, 164 MB) and the same 14 tables of Afrikaans Wikipedia (afwiki), converted by `wiki_convert.py` (log `log_wiki_convert_*.txt`).

## Scripts
1. `quarry_workload.py PARQUET DSN OUT` prepares and plans every query with the prover off, on, and on with the costing hint.
   - **Preparation:** comments, USE and SET are dropped, and anything but one read-only SELECT is skipped. MySQL is translated to PostgreSQL by sqlglot.
   - **Schema made replica-like:**
     - timestamps become 14-digit strings, and numeric constants compared with them are quoted;
     - `templatelinks` regains `tl_namespace`/`tl_title`;
     - `user` is quoted;
     - the Wiki Replicas' alias views (`revision_userindex`, `actor_revision`, …) are views over the base tables.
2. `wiki_mine.py CSVDIR CHECKDIR` mines on simplewiki and checks on afwiki. It is the Stack Exchange miner (`../stackexchange/se_mine.py`) with the dumps' tables. Keys implied by a whole-table key plus the columns a condition fixes are not recommended.
3. `wiki_keys.py DSN [drop]` declares the recommendations that hold on afwiki and whose table is in the core schema (26) as `wk_*`.

## Results
**Plans** (`quarry_workload_empty.json`; with the 26 keys: `quarry_workload_empty_keys.json`; plans on the empty schema)

| | Queries |
|---|---|
| dataset | 25,555 |
| not one read-only SELECT, or untranslatable | 4,650 |
| duplicates | 4,565 |
| do not plan (columns dropped before 2023 such as `rev_user`; Wikibase and other extension tables; MySQL-only syntax) | 7,604 |
| **plan** | **8,736** |
| have DISTINCT, GROUP BY or LEFT JOIN | 3,587 |
| plan changed (default = with costing hint) | 174: 107 DISTINCT removed, 54 GROUP BY shortened, 13 both |
| ... with the 26 mined keys declared | 178 |
| select a mined scope | 14, none changed |

**Where the changes come from:**
- Most are `GROUP BY page_title` / `DISTINCT page_title` with `page_namespace = c`. There the unconditional key `(page_namespace, page_title)` is a key on `page_title` under the query's restriction, which stock PostgreSQL does not see.
- None needs a mined key.

**Coverage gap found, and fixed (see `../pg_patch/README.md`):** the 4 extra changes with the keys declared also use the unconditional key. The prover's single-table GROUP BY pass (`cu_remove_useless_groupby_columns`) only considers relations that have a partial unique index, so declaring any filtered index on `page` switches it on. Unconditional keys under a restriction that fixes a key column are therefore used for single-table GROUP BY only on such tables. The join pass and DISTINCT removal are not gated this way.

**Mining** (`wiki_mine.json`, `log_wiki_mine.txt`): 61 recommendations on simplewiki; 29 hold on afwiki, 17 fail there, and 15 cannot be tested.
- **Invariant:** `geo_tags: UNIQUE (gt_page_id) WHERE gt_primary = 1`, one primary coordinate per page (GeoData extension, so not in the core schema).
- **Correlations, as far as we can tell:** page titles unique among JavaScript, CSS and Scribunto pages (content model determines namespace); `page_props` display titles unique; `pp_sortkey` values tied to one property.
- **Failing on afwiki:** all four `categorylinks` keys for files.

## Miner fix (affects `../stackexchange/se_mine.py` too)
Desbordante's CSV reader misparses quoted values that contain commas, quotes or newlines: on `page_props` it found no key at all, not even the primary key. `keys()` now hashes every value (md5) before handing the scope to HPIValid. Rerunning `se_mine.py` gives the same 107 recommendations as before, one for one; mining now takes 147 s instead of 59 s.

**After the fix** (GROUP BY pass without the gate): 178 plans change with and without the 26 mined keys; still none needs a mined key.
