# Recommending filtered unique indexes on Stack Exchange data (2026-10-28)

## Data

- **Dump:** `stats.stackexchange.com.7z` from archive.org/download/stackexchange.
  - 596,572,001 bytes; MD5 `e26deb6c…b9ab02`, matching archive.org's `stackexchange_files.xml`.
  - April 2024, CC BY-SA 4.0.
  - Extracted with `bsdtar`.
- **Tables:** 8 tables, 5,564,864 rows:

  | Table | Rows |
  |---|---|
  | Votes | 1,747,225 |
  | PostHistory | 1,525,713 |
  | Comments | 819,648 |
  | Badges | 612,258 |
  | Posts | 425,735 |
  | Users | 345,754 |
  | PostLinks | 86,919 |
  | Tags | 1,612 |

## Scripts

1. `se_convert.py XMLDIR CSVDIR` streams the XML to CSV, keeping only columns that can be keys or conditions:
   - **kept:** ids and foreign keys, type/status/class columns, flags;
   - **reduced to presence flags:** nullable dates and text (Closed, CommunityOwned, HasWebsite, HasLocation, AnonymousName);
   - **kept only for the hold-out:** the creation date;
   - **dropped:** free text, scores and counts.
2. `se_mine.py CSVDIR` writes `se_mine.json` and `log_se_mine.txt`. This is the recommendation section's recipe:
   - **Conditions from schema roles:**
     - `col = v` for categorical columns (at most 40 values);
     - `IS [NOT] NULL` for nullable columns;
     - one equality AND one null test;
     - the empty condition.
   - **Keys from data:** minimal UCCs of each encoded scope (Proposition "Reduction") from HPIValid (Desbordante), under U and U=, with `Id` left out.
   - **What is recommended:** (C, K, semantics) with
     - |K| ≤ 3, scope ≥ 50, and ≥ 50 scope rows with K wholly non-null;
     - K not a key of the whole table;
     - for a conjunction, K not already a key under either atom alone.
   - **Hold-out:** mined on rows created before 2020-01-01, then checked on the full dump.

## Results

The run takes 59 s.

| Table | Conditions | Recommended | Still hold in 2024 |
|---|---|---|---|
| PostHistory | 164 | 79 | 75 |
| Votes | 120 | 12 | 10 |
| Posts | 135 | 2 | 2 |
| PostLinks | 3 | 4 | 4 |
| Users | 15 | 4 | 4 |
| Badges | 6 | 2 | 2 |
| Tags (no dates) | 5 | 4 | – |
| Comments | 9 | 0 | – |
| **Total** | **457** | **107** (59 distinct condition–key pairs) | **97 of 103** |

- **Vacuous keys:** under U, a column null throughout a scope is a key, e.g. `UserId` of upvotes, which the dump anonymises, or `ParentId` of questions. The support requirement removed 46 such candidates.
- **81 invariants of the platform** (classification is ours; `kind()` in the README snippet below):
  - PostHistory: `RevisionGUID` unique per `PostHistoryTypeId` (one history row per kind of change in a revision); `PostId` unique for types 1, 2, 3 (initial title, body, tags), 25 and 36.
  - Votes: `PostId` unique where `VoteTypeId = 1` (accepted by originator) and where 12.
  - Posts: U=(`AcceptedAnswerId`) where `AcceptedAnswerId IS NOT NULL` (an answer is accepted by at most one question).
  - PostLinks: (`PostId`, `RelatedPostId`) per `LinkTypeId` 1 and 3.
  - Badges: (`Class`, `Name`, `UserId`) where `TagBased`.
  - Tags: U=(`ExcerptPostId`) / U=(`WikiPostId`) among tags that have them.
- **26 correlations,** with conditions on `ContentLicense` (follows time), `BountyAmount`, `HasLocation`/`HasWebsite`, or `CommunityOwned`. The hold-out rejects only 2 of them (bounty 200).
- **4 invariants rejected by the hold-out, which turned out false:** `PostId` unique for `PostHistoryTypeId` 16 (community owned) and 52 (hot network question), each under U and U=. A post can go through either twice.

Classification used:
```python
def kind(r):
    c = r['cond']
    if any(x in c for x in ('ContentLicense', 'HasLocation', 'HasWebsite', 'BountyAmount', 'CommunityOwned')): return 'correlation'
    if r['table'] == 'PostHistory' and 'UserId' in c and 'PostHistoryTypeId' not in c: return 'correlation'
    return 'invariant'
```

## Real consumer queries: SEDE over the recommended keys (2026-10-29)

**Workload:** the SEDE corpus (Hazoom, Malik, Bogin, NLP4Prog@ACL 2021; github.com/hirupert/sede at 2bf2612, Apache-2.0).
- 12,023 T-SQL queries that users wrote in the Stack Exchange Data Explorer, from `train`, `val_original` and `test_original`. They were read as data; none of the repository's code was run.

**Scripts**
1. `se_load.py XMLDIR DSN`
   - loads the 8 tables with all attributes, with Data Explorer names in lower case and primary keys;
   - adds `posttags` (662,394 rows, derived from `Posts.Tags`) and the lookup tables `posttypes` and `votetypes`;
   - database `se` on port 5444.
2. `se_keys.py DSN [drop]` declares the recommender's output as filtered unique indexes.
   - Every recommendation that holds on the full dump, one per (condition, key), NULLS NOT DISTINCT if U= was recommended: 56 indexes `rec_*`.
   - All were created, so all hold.
3. `se_workload.py SEDE_DIR DSN [OUT]` prepares and plans each query:
   - parameters `##Name:type?default##` and `DECLARE @v = …` are substituted;
   - anything but one read-only SELECT is skipped;
   - T-SQL is translated to PostgreSQL with sqlglot;
   - each query gets EXPLAIN off/on in a read-only transaction.
   - Runs:

     | Indexes | Output |
     |---|---|
     | primary keys only | `se_workload_nokeys.json` |
     | with the 56 indexes | `se_workload.json` |
4. `se_timing.py DSN` writes `se_timing.json` and `log_se_timing.txt`:
   - times the changed queries: 10 alternating rounds after a warm-up, 30 s limit;
   - checks results in one transaction without LIMIT (`../discourse/x11_timing.py`).

**Results**

| | Queries |
|---|---|
| corpus | 12,023 |
| not one read-only SELECT, or untranslatable | 2,078 |
| duplicates | 327 |
| do not plan (other Data Explorer tables, T-SQL functions) | 3,040 |
| **plan** | **6,578** |
| name a table with a recommended filtered key and its predicate columns | 2,250 (34%) |
| plan changed, primary keys only | 105 |
| plan changed, with the 56 keys | 142 (50 need a recommended key) |
| timed (8 hit the 30 s limit) | 134; all results identical |

**Speed-ups** of the 124 changed queries over 1 ms:
- **Overall:** median 1.00; 13 more than 1.1× faster (max 2.86×, "Most upvoted questions by tag", PK-based; 2.45×, "Users with N accepted answers", via a key); 15 more than 1.1× slower (min 0.38×).
- **By kind of change:**

  | Kind | Count | Median | Slower (< 0.9) |
  |---|---|---|---|
  | GROUP BY key shortened | 74 | 1.01 | 3 |
  | DISTINCT/aggregate removed | 25 | 1.00 | 1 |
  | costing only | 15 | 0.48 | 9 |
  | Inner Unique only | 8 | 1.01 | 1 |
  | join removed | 2 | 1.00 | 0 |

- **What causes the slowdowns:** physical plan choices made with the new knowledge.
  - 757648: a hash join with a sequential scan of `posts` replaces a merge join over `posts_pkey`.
  - 601817: GROUP BY by the primary key is dropped entirely, so the planner scans `posts` sequentially instead of by `posts_pkey`. That scan is slower with the default 128 MB `shared_buffers`: 224 vs 98 ms for the scan.

### With the data cached (2026-10-29)

`SE_OUT=se_timing_4GB.json se_timing.py DSN` with `shared_buffers = 4GB` (the 2.8 GB of data fit), then reset to 128 MB. `se_timing.json` is the 128 MB run, also kept as `se_timing_128MB.json`.

| | 128 MB | 4 GB |
|---|---|---|
| changed queries over 1 ms | 124 | 126 |
| more than 1.1× faster | 13 (max 2.86×) | 23 (max 3.30×) |
| more than 1.1× slower | 15 (min 0.38×) | 4 |
| costing-only changes, median | 0.48 | 1.08 |

- Of the four still slower, three lose at most 1.14×; 445757 takes 13 ms instead of 5.
- The hash-vs-merge-join and sequential-scan choices above cost with a cold cache and mostly do not with a warm one.
- All results identical in both runs.

## Do the recommendations hold on other sites? (2026-10-29)

`se_transfer.py dba=DIR academia=DIR travel=DIR` (CSV made by `se_convert.py` from the archive.org dumps of dba, academia and travel; 0.5M posts together) tests every recommendation of `se_mine.json` on each site: untestable below 50 rows with the key non-null, else holds or fails on the whole dump. Output `se_transfer.json`.

- The 101 that hold on stats in 2024 (97 dated, 4 without dates): 99 testable, **86 hold on all three sites, 13 fail**.
- The 13: 7 of the 24 correlations, and 6 we had read as invariants (PostHistoryType 19 protected and 25 tweeted can repeat; VoteType 12 spam votes can repeat on some sites).
- The 17 correlations that pass follow the platform's history (e.g. licence versions over time), which all sites share.
- Other sites are a sharper filter than later data (the hold-out rejected 2 correlations).

## Stricter scope count, gains by source, and a rewrite-only variant (2026-10-29)

**Scope in the planner's sense** (`se_scope.py DSN` → `se_scope.json`, `log_se_scope.txt`).
- `names_filtered` in `se_workload.json` is lexical: the query mentions the table and the predicate columns (2,250 queries).
- `se_scope.py` asks what the prover asks: does the restriction of some table instance (WHERE and ON conjuncts on that instance alone) imply the predicate of a recommended index? Atoms are read as the prover reads them; join clauses never count.
- **555 of 6,578** queries select a scope. Most often: `rec_48` users with a location (111), `rec_42` accepted answers (88), `rec_9` close events (73), `rec_38`/`rec_39` history rows with a user (66), `rec_41` duplicate links (64).
- Of the 50 plan changes that need a recommended key, 36 select a scope. 11 of the other 14 join on `AcceptedAnswerId`, whose key `rec_42` excludes only null keys and so holds for every join. One gets its constant through an equivalence class (`Pt.Id = 2`), which a lexical reader misses.

**Speed-ups by source** (changed queries over 1 ms):

| | 128 MB | 4 GB |
|---|---|---|
| need a filtered key | 43: 5 faster (max 2.45), 11 slower | 45: 10 faster (max 1.67), 3 slower (min 0.88) |
| primary keys (DISTINCT, through joins) | 81: 8 faster (max 2.86), 4 slower | 81: 13 faster (max 3.30), 1 slower (445757, 5 → 13 ms) |

**Rewrite-only variant** (`se_norc.py DSN` → `se_norc.json`, `log_se_norc.txt`).
- Build `inst-norc`, experiment only: `innerrel_is_unique`, when called from `add_paths_to_joinrel` for costing, does not ask the prover. Join removal, semi-join reduction, and DISTINCT and GROUP BY removal are unchanged. The patch itself is unchanged.
- Replanning the 142 changed queries: 24 return to the stock plan, 118 keep the full prover's plan, and none gets a third plan. So the variant's timings are the stock timings for the 24 and the full prover's for the rest.

| | full prover, 128 MB | variant, 128 MB | full prover, 4 GB | variant, 4 GB |
|---|---|---|---|---|
| > 1.1× faster | 13 | 10 | 23 | 15 |
| > 1.1× slower | 15 | 4 | 4 | 1 |

## STATS-CEB (2026-10-29)

`se_statsceb.py FILE DSN` plans the 146 queries of STATS-CEB (Han et al., PVLDB 15(4), 2021; `workloads/stats_CEB/stats_CEB.sql` of github.com/Nathaniel-Han/End-to-End-CardEst-Benchmark, read as data) on database `se` with the 56 recommended keys. The prover is run off, on, and on with the costing hint. Output: `se_statsceb.json`, `log_se_statsceb.txt`.

- All 146 plan.
- 40 restrict a table to a recommended scope (as in `se_scope.py`); 17 of those are `postLinks.LinkTypeId = 1`.
- None changes plan: the queries are `COUNT(*)` over inner joins on non-key columns (UserId, PostId), with no DISTINCT, GROUP BY or left join.

## Miner fix (2026-10-29)
`se_mine.keys()` now hashes values before writing the scope for HPIValid, because Desbordante's CSV reader misparses quoted values with commas, quotes or newlines (found on MediaWiki's `page_props`; see `../quarry/README.md`). The rerun gives the same 107 recommendations; the previous output is in the scratch directory as `se_mine.before_md5.json`. Mining takes 147 s (was 59 s).

## Which changes need a recommended key (2026-10-29)

- **Earlier count (50):** compared plan texts with and without the 56 keys.
  - That counts 13 queries that change in both runs, but with different plans, mostly because the extra indexes change access paths.
  - It also moved to 48 when the primary-keys-only run was redone on the build without the GROUP BY gate.
- **Count now used: changes only when the keys are declared.** 37 (`se_needs_key.json`), the same before and after that change.
  - 28 select a recommended scope.
  - 8 of the other 9 join on `AcceptedAnswerId` (key `rec_42`, null keys excluded).
  - The ninth, 138197 ("Users with over 2000 answers"), selects a scope without writing it: `Pt.Id = Ph.PostHistoryTypeId AND Pt.Id = 2` puts `posthistory.posthistorytypeid = 2` into its restrictions through the equivalence class, the scope of `rec_18`. The costing hint swaps the hash join's sides. `se_scope.py` reads only the restrictions written on the table, so it misses this one.
- `se_workload_nokeys.json` is the rerun on the new build: 105 changed, as before.

**Speed-ups by source, strict definition** (changed queries over 1 ms):

| | 128 MB | 4 GB |
|---|---|---|
| change only with a recommended key | 30: 5 faster (max 2.45), 11 slower | 32: 8 faster (max 1.67), 3 slower (min 0.88) |
| others | 94: 8 faster (max 2.86), 4 slower | 94: 15 faster (max 3.30), 1 slower |
| key-only changes under the default (no costing hint) | 2 faster, 0 slower | 0 faster, 0 slower |

With the data cached, every timed filtered-key change that runs faster or slower is among the 24 plans that the costing hint alone changes (`se_norc.json`). So on Stack Exchange the recommended keys pay off through join costing only.
