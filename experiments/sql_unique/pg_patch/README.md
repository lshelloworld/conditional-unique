# condunique: PostgreSQL 18.6 patch (experiment X1)

`condunique-pg18.6.patch` applies to the PostgreSQL 18.6 release tarball (sha256
555610c2…881d9f). It adds:
- `src/backend/optimizer/util/condunique.c` (1,206 lines), with the header `condunique.h`;
- a field `cu_premises` in `RelOptInfo` (`pathnodes.h`): the premise cache;
- hooks in `indxpath.c` (`relation_has_unique_index_ext`), `analyzejoins.c`
  (`rel_supports_distinctness`), `planmain.c` (a second GROUP BY pass) and `planner.c`
  (DISTINCT removal, added after X5); 30 changed lines in the five files with `pathnodes.h`;
- the setting `enable_conditional_unique`, off by default;
- the updated `sysviews` expected output.

## Build (macOS, this machine)
The default SDK 27 does not link with the installed command-line tools, so use 26.5:

```bash
export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk PG_SYSROOT=$SDKROOT
./configure --prefix=$PREFIX --without-icu --without-readline --without-zlib --enable-debug CFLAGS=-O2
make -j16 && make install
```

The scratchpad paths have Unix-socket paths that are too long, so start servers with
`-c unix_socket_directories=''` and connect over TCP.

## Results (2026-10-28)

**Regression suite**
- With the setting off, all 231 tests pass.
- With `PGOPTIONS="-c enable_conditional_unique=on"`, there are no result changes. The only plan change is in `join`: the partial index `UNIQUE (id2) WHERE id2 IS NOT NULL` now yields `Inner Unique: true`. That is correct, because the join on `id2` admits only non-null values.

**Feature tests**
- `cu_feature.sql` and `cu_feature.out` hold 12 queries. Each records the plan with the setting off and on, plus a comparison of the results.
- The cases are: soft delete, per-status scopes, a tenant scope, `NULLS NOT DISTINCT` versus nulls distinct under GROUP BY, the shape of bug #17975, and an untranslatable predicate.
- All 12 return the same result with the setting off and on.

**Run times (`speedup.py`)**

The tables are `users` 1M, `orders` 5M, `items` 1M and `refs` 2M rows. Times are medians of five runs.

| Query | Default (2026-10-29) | Costing hint on (earlier) |
|---|---|---|
| Left-join removal, soft delete | 1.64× | 3.65× |
| Left-join removal, tenant scope | 4.46× | 5.61× |
| Semi-join to join | 1.01× | 1.02× |
| GROUP BY reduction | 1.06× | 1.03× |
| DISTINCT removal, soft delete | 5.75× | 3.87× |

Results were identical with the setting off and on. The plans are the same in both runs, so the differences are run-to-run noise (the times include fetching up to 5M rows). The paper uses the default run. Data: `speedup.json` (default) and `speedup_costing.json` (earlier).

**Planning overhead (`plan_overhead.py`, TPC-DS SF1, 97 plannable queries)**

| Catalog | Planning median, off | Overhead median | Overhead max | Plans changed |
|---|---|---|---|---|
| 5 current-version business keys | 0.13 ms | +0.002 ms | +0.13 ms | 0 |
| All 4,001 stable mined keys (stress) | 1.4 ms | +0.035 ms | +4.9 ms | 0 |

- In the stress catalog the maximum overhead falls on queries that already take 140–160 ms to plan.
- Before the premise filter the maximum was 830 ms.
- These are the numbers after the DISTINCT hook (rerun 2026-10-28, measured twice).
  - The first measurement, before the X5 translation changes, had a maximum of +19 ms on queries that took 140–160 ms to plan. It is kept in `*_before_distinct.*`.
  - The +45 ms now falls on q14, q37 and q82. None of them has DISTINCT, so the new hook never runs for them. They plan in 2–8 ms without the prover and all join `item`, which has 948 indexes.
  - The likely cause is the X5 translation extensions, but this has not been isolated.
  - A per-relation cache of compiled premises would remove most of it.
- Speed-ups were rerun with the DISTINCT query added; the previous numbers are kept in `*_before_distinct.*`.
- The data is in `plan_overhead.json`.

## X2: differential testing (`x2_difftest.py`, 2026-10-28)

**Setup**
- **Random schemas:**
  - 3–6 columns over small domains (int 0..3, text 'a'..'d', bool), some NOT NULL.
  - 1–4 unique indexes, 85% of them partial, with random predicates: `=`, `<>`, `IN`, `NOT IN`, `IS [NOT] NULL`, boolean columns, AND/OR, and occasionally an untranslatable atom.
  - Random `NULLS NOT DISTINCT`.
- **Random data:** inserted with `ON CONFLICT DO NOTHING`, so keys repeat freely outside each scope.
- **Seven query shapes:**
  - left join;
  - left join scoped through a join clause, the shape of bug #17975;
  - inner join;
  - semi-join;
  - GROUP BY;
  - GROUP BY over an inner join;
  - GROUP BY over the nullable side of a left join.
- **Each query** runs with the setting off and on under random join and aggregation method settings. Results are compared as multisets.

**Result (seed 2027): 5,000 schemas, 200,000 queries**
- 20,737 plans changed, including 8,723 left joins removed only with the patch.
- **No result differed.**
- **Power check:** on 14,845 left joins, some unique index has its key within the join columns. Reading such an index as a plain UNIQUE (predicate ignored) would license removing the join, and 5,269 of those removals return a wrong result on the data.

**Mutants (seed 7: 500 schemas, 20,000 queries each; the correct build changes 2,204 plans and no results)**

| Mutant | Result differences | Shapes |
|---|---|---|
| M1: index predicates ignored | 2,706 | GROUP BY 1,064; left join 1,036; GROUP BY over left join 307; inner join 296; semi-join 3 |
| M2: GROUP BY proved with nulls distinct (U instead of U=) | 232 | all GROUP BY |
| M3: outer-join check (`nulling_relids`) removed | 0 plan changes | none |
| M4: both outer-join guards removed (`nulling_relids` and `varnullingrels`) | 3 | all GROUP BY over left join |

M3 is an equivalent mutant: Vars above an outer join carry nulling marks, and the prover's column test rejects them, so the removed check is a redundant second guard.

The logs are `log_x2*.txt` and the data `x2_difftest*.json`. The mutant binaries were built in the scratchpad (`inst-mut1..4`) by sed edits to `condunique.c`, which was then restored.

**Mutant M11: bug #17975 restored (2026-10-30)**
- **Mutant** (`inst-mut11`, data `data-mut11`, port 5491): one line in `relation_has_unique_index_for` (indxpath.c) brings back the pre-2023 test. With `enable_conditional_unique` on, a partial unique index is accepted as soon as `predOK` is set. `check_index_predicates` also proves `predOK` from join clauses, which is the cause of the bug. The source was restored and rebuilt afterwards.
- **L2 does not trigger the bug.**
  - L2 is `ON o.J = t.J AND t.cm = o.cm`, so both clauses sit in the same join.
  - Inner Unique stops only after a row has passed every join clause, so the result stays right.
  - M11 on the default shapes (seed 7, 500 schemas, 20,000 queries): 2,260 plans changed, 0 results differ (`log_x2_mut11.txt`).
- **New shape B** (`X2_SHAPES=B`): the bug itself, where the predicate is implied only by the clause of *another* join.
  - Query: `SELECT o.*, u.cm FROM o JOIN t ON o.K = t.K JOIN o u ON t.cm = u.cm`.
  - K is the key of a partial index of t. If t has an index with predicate `cm IS NOT NULL`, K and cm are taken from it; the strict equality implies that predicate.
  - Hand case: `bug17975.sql` (3 tables; a nested loop under `join_collapse_limit = 1`). M11 returns 0 rows instead of 1; the patched build returns 1.

| Build | Run | Plans changed | Results differ |
|---|---|---|---|
| M11 | seed 7, 500 schemas, 20,000 queries | 974 | 442 |
| patched | seed 7, 500 schemas, 20,000 queries | 647 | 0 |
| patched | seed 2027, 5,000 schemas, 200,000 queries | 6,713 | 0 |

- **Example mismatch:**
  - indexes `t (c2) WHERE c1 IS NOT NULL` and `t (c0, c2, c3) WHERE c2 IS NULL`;
  - query: `o JOIN t ON o.c2 = t.c2 JOIN o u ON t.c1 = u.c1`;
  - plan: a merge join on c2 below a merge join on c1.
- **Data:** `x2_difftest_mut11.json`, `x2_difftest_bug_mut11.json`, `x2_difftest_bug.json`, `x2_difftest_bug_2027.json`, with the matching `log_x2_*` files.
- **Settings:** the costing hint was on in all runs (server option for M11, `PGOPTIONS` for the patched build).

## Limitations

**Not covered**
- DISTINCT over joins, DISTINCT ON, and DISTINCT above grouping (only single-relation DISTINCT is removed).
- Expression indexes.
- Self-join elimination: the prover does not report which clauses established uniqueness.


## Changes after X5 (2026-10-28)

- An index may use any opclass whose equality is the column type's default equality, for example `text_pattern_ops`.
- Atoms may use any equality of the column type's default btree family, cross-type included (`int2 = int4`, `int2 = ANY (int4[])`). Constants are identified with the family's cross-type equality.
- Retested after both changes:
  - the regression suite, setting off: all 231 tests pass;
  - the regression suite, setting on: the same single plan difference as before;
  - the feature tests: unchanged;
  - differential testing: 40,000 queries (seed 99, `x2_difftest_seed99.json`) and 60,000 queries with smallint columns compared with int4 constants (seed 314, `x2_difftest_crosstype.json`), with no result differences.
- `condunique-pg18.6.patch` is regenerated.

## DISTINCT removal (2026-10-28)

**The rewrite**
- Stock PostgreSQL 18 never removes DISTINCT over a base relation.
- `cu_distinct_is_redundant` (in `condunique.c`, called from `grouping_planner` in `planner.c`) skips `create_distinct_paths` when all of these hold:
  - the query reads exactly one base relation (`all_baserels` is a singleton);
  - the query has no DISTINCT ON, grouping, aggregates, HAVING, window functions, set operations or target-list SRFs;
  - the prover shows that the relation's rows passing its restriction clauses are unique on the DISTINCT columns **with nulls equal (U=)**.
- DISTINCT items count only if they are plain columns whose equality is the column type's default btree equality, under a deterministic collation. Other items only make rows more distinct.

**Tests**

| Test | Result |
|---|---|
| Regression suite, setting off | all 231 tests pass |
| Regression suite, setting on | the same two differences as before (`join` Inner Unique, `sysviews`) |
| Feature tests (`cu_feature.sql` cases 7a–7g, 18 result checks in all) | all the same with the setting off and on |
| Differential testing (shapes `D` = `SELECT DISTINCT G FROM t WHERE P` and `DJ` = the same over a join; `X2_SHAPES=D,D,DJ`), seed 2028, 5,000 schemas, 200,000 queries | 27,809 plans changed, 26,331 DISTINCTs removed only with the patch, **0 results differ** |

- The feature cases in detail:
  - removed: a NULLS NOT DISTINCT scope; a nulls-distinct scope with `k IS NOT NULL`; extra DISTINCT columns; a NOT NULL key;
  - kept: a nulls-distinct scope; outside the scope; over a join; DISTINCT ON.
- **Power of the differential test:** the naive rule (an index with its key within G, predicate and null semantics ignored) licenses 78,619 removals, and 23,796 of them would be wrong. Data: `x2_difftest_distinct.json`, log `log_x2_distinct.txt`.

**Mutant M5: DISTINCT proved with U instead of U=** (seed 7, 500 schemas, 20,000 queries; built in `inst-mut5`)

| Build | DISTINCTs removed | Result differences |
|---|---|---|
| Mutant M5 | 4,839 | 551 |
| Correct build | 2,886 | 0 |

Data: `x2_difftest_distinct_mut5.json` and `_seed7.json`.

## Premise cache (2026-10-28)

**Why**
- Profiling q82 on the stress catalog showed the time going into `cu_decide`'s loop over every unique index of `item` (948).
- For every question, the loop repeated catalog lookups per key column: `get_opfamily_member` and `get_collation_isdeterministic`.

**What changed**
- The question-independent checks are now made once per relation and planner run:
  - the index is unique, immediate and has no expressions;
  - every key column uses the default equality of its type under a deterministic collation.
- The result is stored as a list of (index, key-attno set) in the new `RelOptInfo.cu_premises`.
- It is allocated in the rel's memory context, so it survives GEQO's per-tour contexts.
- Per question, only the premise filter (`bms_is_subset` against the usable attnos) and the translation of the surviving predicates remain.
- The struct change needs a clean rebuild (`make clean`), because the tree is configured without dependency tracking.

**Effect**
- Under the profiler (`sample`), planning q82 went from 70 ms to 7.4 ms per plan.

  | Measure (stress catalog) | Before | After |
  |---|---|---|
  | Median overhead | +0.08 ms | +0.035 ms |
  | Maximum overhead | +45 ms | +4.9 ms |
  | p95 planning-time ratio | 14.6 | 2.3 |

- The SCD catalog is unchanged at +0.002 ms median and +0.13 ms maximum.
- Data: `plan_overhead.json` and `log_plan_overhead.txt`; the uncached runs are kept as `*_nocache.*` and `*_run1.*`.

**Retested**

| Test | Result |
|---|---|
| Regression suite, setting off | all 231 pass |
| Regression suite, setting on | the same two differences as before |
| `cu_feature.out` | byte-identical |
| Differential testing: 80,000 queries of the seven original shapes (seed 2029) and 80,000 DISTINCT queries (seed 2030) | no result differences (`log_x2_cache.txt`, `log_x2_distinct_cache.txt`) |
| All TPC-DS queries planned with GEQO forced (`geqo_threshold = 2`), setting off and on | no errors beyond the two unplannable queries, no plan differences |
| X4 decisions on the cached build | 1,094 joins and 171 DISTINCTs, identical to the uncached run on every query (`x4_decisions_nocache.json`) |

## TPC-DS through current-attribute views (`tpcds_views.py`, 2026-10-28)

**Setup**
- Each history-keeping dimension `d` (item, store, call_center, web_page, web_site) is offered as a view `sl.d`:
  ```sql
  SELECT h.*, c.<a> AS cur_<a>, ... FROM d h
    LEFT JOIN d c ON c.<business key> = h.<business key> AND c.<rec_end_date> IS NULL
  ```
- The 99 queries run unchanged with `search_path = sl, public`.
- The catalog is the primary keys plus the five SCD partial unique indexes; the mined indexes are dropped.
- Configurations:
  - base: no views;
  - off: views, setting off;
  - on: views, setting on.
- SF1, one core, median of 3 runs, 60 s limit.
- Data: `tpcds_views.json`; log: `log_tpcds_views.txt`.

**Results**
- **Queries:** 94 ran. q1, q4 and q11 hit the 60 s limit, and q2 and q78 are not plannable in PostgreSQL. Of the 94, 76 read a history-keeping dimension.
- **Joins:** the views add 146 self-joins. Stock PostgreSQL keeps all of them; the patch removes all of them.
- **Results:** identical in all three configurations.
- **Execution, total over the 76 queries:**

  | Configuration | All 76 | Without q72 |
  |---|---|---|
  | base | 120.2 s | 119.9 s |
  | off | 155.2 s (+29%) | 139.9 s (+17%) |
  | on | 134.0 s | 118.6 s (−1%) |

- **Per query (off/on):** median 1.03×, maximum 1.63× (q6: 47.6 s → 29.2 s), above 1.1× for 9 queries.
- **Planning, median:** base 0.14 ms, off 0.26 ms, on 0.20 ms.
- **q72** takes 0.33 s on base tables and about 15.4 s through the views, whether or not the join is removed.
  - The view's join tree is not merged into the query's: `from_collapse_limit` is 8, and q72 joins more relations.
  - With `from_collapse_limit` and `join_collapse_limit` set to 20, it runs in 0.34 s through the views with the patch, against 0.35 s on base.
  - So this is a view-flattening effect, independent of the prover.

### Scale factor 10 (`tpcds_views_sf10.json`, `log_tpcds_views_sf10.txt`)

**Setup**
- Database `tpcds10` on port 5444, loaded by `../../tpcds/load_tpcds.py 10`. store_sales has 28.8M rows; item has 102k.
- Settings: `VIEWS_RUNS=1 VIEWS_TIMEOUT=600 VIEWS_DIMS_ONLY=1`. The result fetch serves as the warm-up, then one measured run per configuration.

**Results**
- **Queries:** 75 ran. q1, q6, q54 and q95 hit the 600 s limit. 73 read a history-keeping dimension.
- **Joins:** the views add 141 joins. All are kept with the setting off; all are removed with it on.
- **Results:** identical.
- **Totals over the 73, q72 aside:**

  | Configuration | Total |
  |---|---|
  | base | 783.4 s |
  | off | 835.7 s (+6.7%) |
  | on | 777.5 s (−0.7%) |

- **Per query:** off/on median 1.02×, maximum 1.43× (q53: 37.5 s → 26.2 s), above 1.1× for 13 queries.
- **q72:** 4.1 s on base, 25.9 s off, 25.1 s on. This is the view-flattening artifact seen at SF1.
- **Planning, median:** base 0.15 ms, off 0.26 ms, on 0.20 ms.

**Comparison with SF1**
- At SF1, q6 accounts for 18 of the 20 s of view overhead (47.6 s off against 29.5 s base).
- Without q6, SF1 costs 2.1% off (92.3 s against 90.4 s) and −1.1% on.
- The overhead therefore grows from about 2% to 7% between SF1 and SF10 on comparable queries. The prover removes it at both scales.

## Uniqueness through joins (2026-10-28)

**What it does** (`condunique.c`: `CuDet`, `cu_det_*`, `cu_distinct_is_redundant`, `cu_reduce_groupby_through_joins`; hook in `planmain.c` after the single-relation GROUP BY pass)

A relation is *determined* by the DISTINCT/GROUP BY columns G if its part of every joined row is a function of G. It is determined if:
- **from G:** it is U= unique on its own G columns with no nullingrels; or
- **through an equality:** it is U unique on columns equated with columns of determined relations. Equated means by an equivalence class with at least 2 members, or by an outer-join clause read from a determined outer side.

Further rules:
- A relation on the nullable side of a left join is only considered once its whole outer side is determined.
- Semi- and anti-join inner sides need no determining, and their columns fix nothing.
- Full joins: the pass is skipped.

What it then does:
- **All relations determined:** DISTINCT is dropped, and so is a GROUP BY without aggregates, HAVING, window functions or SRFs.
- **With aggregates:** a relation's GROUP BY columns are dropped if the other columns determine it, keeping at least one.

**Bugs found and fixed while testing, each kept as a mutant**

| Mutant | Error | Caught by |
|---|---|---|
| M7 (`inst-mut7`) | single-member equivalence classes (made for sort keys) read as equalities | random join shapes: 34 / 20,000 results differ |
| M6 (`inst-mut6`) | nullable side entered while its outer side is only partly known | random shapes: 0 / 40,000; feature test 8g: wrong result (hand-checked on M6) |
| M8 (`inst-mut8`) | semi-join inner columns read as fixed values (found on TPC-DS q35: `ca_state` dropped) | random shapes with semi-joins: 11 / 20,000; feature test 8j: `DIFFERENT: 3` |

**Tests on the final version**
- **Regression:** passes with the setting off. With it on, `join`, `aggregates` and `sysviews` differ in plans only (redundant GROUP BY/DISTINCT gone, Inner Unique); `regression_joins_on.diffs` is in the scratchpad.
- **Feature tests (`cu_feature.sql`):** 27/27 same result. Section 8 adds 10 join cases (8a–8j).
- **`x2_difftest.py` with `X2_JOINS=1`, shapes XD/XL/X3/XG/XA** (a third with a semi-join; the third join's ON may read both outer tables):
  - 200,000 queries, seed 2031: 30,011 plans changed, 3,031 DISTINCT/GROUP BY dropped, 12,829 group keys shortened, 0 results differ.
  - Files: `x2_difftest_joins.json`, `log_x2_joins.txt`.
- **Original shapes rerun** (L, L2, I, S, G, GJ, GL, D, DJ; seed 2032): 200,000 queries, 21,383 plans changed, 0 differ (`x2_difftest_after_joins.json`).
- **Table x4:** identical to before (1,094 / 171).
- **Planning overhead** (`plan_overhead.py`):
  - SCD catalog: +0.022 ms median, +0.41 ms max on 0.14 ms (was +0.002 / 0.13 before the join pass).
  - Mined stress catalog: +0.12 ms median, 3.9 ms max.
  - q46 and q68 change (GROUP BY loses `ca_city`, customer address joined on its primary key), with the same results.
- Earlier runs on the build with the semi-join bug are kept as `*_semibug.*`. That build's TPC-DS run is where q35's wrong result showed.

**Patch:** `condunique-pg18.6.patch` regenerated (12 files; `condunique.c` 1,540 lines; 33 changed lines in five planner files as the paper counts them). Dry run on the 18.6 tarball: applies cleanly.

## CHECK constraints as premises (2026-10-29)

**What it does** (`cu_checks`, `cu_null_sources`, in `cu_decide`)
- **Which constraints:** validated, enforced, inheritable CHECK constraints are read once per relation and planning run, cached with the premise indexes. They are prepared as `get_relation_constraints` prepares them: `eval_const_expressions`, `canonicalize_qual(…, true)`, Var renumbering.
- **How they are used:** each translatable one narrows the goal's scope.
  - A row passes `CHECK c` when c is true *or null*. So the scope is narrowed by `c OR (x IS NULL)` for every nullable column x through which c can be null: the columns c compares or tests as booleans.
  - Columns only under `IS [NOT] NULL` or `IS TRUE/FALSE/UNKNOWN` are not counted, since they cannot make c null.
  - `NOT VALID` / `NOT ENFORCED` (PG 18) and `NO INHERIT` constraints are ignored.
- **New atoms:** `IS TRUE` / `IS FALSE` / `IS [NOT] UNKNOWN` on boolean columns are now translated, both in queries and in CHECKs.
- **Fix found on MusicBrainz:** a CHECK can contribute templates that contradict the query, e.g. `locale IS NULL` with `locale = 'en'`. `cu_fixed` used to let such a template veto the premise filter, which cost two earlier proofs. It now ignores templates that match no row. This affects completeness only.

**Tests**

| Test | Result |
|---|---|
| Feature tests | 32/32 same result; section 9 has 5 CHECK cases (null-passing comparison, MusicBrainz alias check, NOT VALID with violating rows, NOT ENFORCED, nullable boolean) |
| `x2_difftest.py`, `X2_CHECKS=1`, original shapes + D/DJ, seed 2033 | 200,000 queries, 44,887 plans changed, 0 differ (`x2_difftest_checks.json`) |
| `X2_CHECKS=1 X2_JOINS=1`, join shapes, seed 2034 | 200,000 queries, 31,088 plans changed, 0 differ (`x2_difftest_checks_joins.json`) |
| Mutant M9 (`inst-mut9`): CHECK read as if nulls failed it | 120 / 20,000 results differ |
| Mutant M10 (`inst-mut10`): NOT VALID / NOT ENFORCED used | 327 / 20,000 results differ |
| Regression suite | off: all 231 pass; on: the same plan-only differences as before |
| Planning overhead, SCD catalog | +0.021 ms median, 0.24 ms max (base 0.13 ms) |
| Planning overhead, stress catalog | +0.12 ms median, 5.6 ms max; q46/q68 change, same results |

- **Totals:** across all runs, 1,000,000 random queries (original, DISTINCT, joins, CHECK, CHECK + joins), 154,532 plans changed, 0 results differ.
- **Patch:** regenerated; `condunique.c` is now 1,670 lines; the dry run applies cleanly.

## Rewrite-only variant (experiment, 2026-10-29)

`inst-norc` in the scratch build: `cu_skip_costing` is set around the two `innerrel_is_unique` calls in `add_paths_to_joinrel` (joinpath.c), and the prover hook in `relation_has_unique_index_for` (indxpath.c) is skipped while it is set. The prover's proofs then serve the logical rewrites but not the Inner Unique costing hint. This is not part of `condunique-pg18.6.patch`. Results: `../stackexchange/README.md`.

## Costing hint behind its own setting (2026-10-29)

**Change:** `enable_conditional_unique_costing` (default off).
- `add_paths_to_joinrel` sets `cu_costing_only` while it asks `innerrel_is_unique` for the inner_unique costing hint.
- In that window the prover hook in `relation_has_unique_index_for` answers only if the new setting is on.
- Join removal, semi-join reduction, and DISTINCT and GROUP BY removal are unchanged. So is the hint for keys without predicates.
- This is what the `inst-norc` experiment above measured, now as a setting.

**Patch:** regenerated; 13 files (joinpath.c is new); `condunique.c` 1,674 lines; 38 changed lines in six planner files (the earlier count method gives 33 for the previous patch); dry run on the 18.6 tarball applies cleanly. The previous patch is in the scratch build as `condunique-pg18.6.patch.pre-costing`.

**Tests:**
- **Regression:** all 231 pass with the settings off (`sysviews.out` now lists the new setting).
- **Setting on, costing off:** join, aggregates and sysviews differ in plans only. The earlier Inner Unique change in `join` is gone.
- **Both on:** the diffs are as before.
- **Feature tests:** 32/32 same result under the default. `cu_feature.out` is now the default output; plans differ from before only in join method (hash left join → hash right join). `cu_feature_costing.out` (both settings on) is byte-identical to the previous `cu_feature.out`.
- **Differential testing under the default** (costing hint off, CHECKs on):
  - join shapes, seed 2035: 40,000 queries, 7,804 plans changed, 0 differ (`x2_difftest_default_joins.json`, `log_x2_default_joins.txt`);
  - original shapes plus D/DJ, seed 2036: 40,000 queries, 6,547 plans changed, 0 differ (`x2_difftest_default.json`, `log_x2_default.txt`).

## GROUP BY pass without the gate (2026-10-29)

**Change:** the single-table GROUP BY pass (`cu_remove_useless_groupby_columns`) used to skip relations without a partial unique index (`cu_rel_has_partial_unique`). It now considers every relation with a unique index (`cu_rel_has_unique(rel, false)`), because a restriction can fix key columns of an unconditional index: `WHERE ns = 0` makes `UNIQUE (ns, title)` a key on `title`, which stock PostgreSQL's first pass does not see. The join-shaped test keeps its gate: for unconditional indexes, stock `relation_has_unique_index_for` already counts `col = const` restrictions. Found on Wikimedia Quarry (`../quarry/README.md`). Backup: `condunique.c.pre-gate`.

**Patch:** regenerated; 13 files, 38 changed planner lines, `condunique.c` 1,683 lines; dry run applies cleanly.

**Tests:**
- **Regression:** 231/231 with the settings off. With the setting on, the diffs are identical to the previous build.
- **Feature tests:** 35/35 same result. New section 10:
  - 10a: GROUP BY title, len under `ns = 0` reduces to title;
  - 10b: `ns IN (0, 1)` keeps both columns;
  - 10c: a nullable title keeps both columns.
  - `cu_feature_costing.out` is also regenerated.
- **Differential**, both with CHECKs:
  - original shapes plus D/DJ, seed 2037: 40,000 queries, 6,401 changed, 0 differ (`x2_difftest_gate.json`);
  - join shapes, seed 2038: 40,000 queries, 7,461 changed, 0 differ (`x2_difftest_gate_joins.json`).
- **Planning overhead** (`log_plan_overhead.txt`; previous run in `*_before_gate.*`):
  - SCD catalog: +0.026 ms median (was 0.021), max 0.29 ms (0.24), planning 0.14 ms;
  - mined stress catalog: +0.15 ms median (0.12), max 2.8 ms (5.6, noise), p95 ratio 2.4;
  - q46 and q68 change as before.
- **Workloads replanned** (with the costing hint on, as the earlier runs):
  - SEDE: the same 142 plans, identical;
  - SkyServer: 26, unchanged;
  - Quarry: 178 (was 174), the same with or without the mined keys;
  - Discourse: 30 (was 29), the new one a GROUP BY on `topic_users` under `topic_id = 1`;
  - applications: 6 (the final run had 5); the new one is a GitLab DISTINCT on `subscription_add_on_purchases` proved through its validated `CHECK (subscription_add_on_uid IS NOT NULL)`, a CHECK-premise case that the earlier final run predates. Not timed.

## One index at a time on real workloads (2026-10-29)

**Question:** do the real plan changes that need a filtered key need several indexes together, or would a prover that uses one index at a time find them?

**Build `inst-one`, experiment only:** `cu_decide` calls `cu_implies` once per premise index, and once with none, instead of once with all. Restrictions, NOT NULL and CHECK constraints still combine. Made by patching `condunique.c`, building, and copying the `postgres` binary into a copy of `inst-ck`; the source was restored and rebuilt. The patch is unchanged.

**Check that the variant differs:** `t (k int, c int NOT NULL CHECK (c = 1))` with `UNIQUE (k)` and `UNIQUE (c) WHERE k IS NULL`. `SELECT DISTINCT k FROM t` keeps its HashAggregate on `inst-one` and is a plain scan on `inst-ck`: the two indexes together give U=(k), neither alone does.

**Run:** `one_index.py 'host=/tmp port=5444 user=ck' 'host=/tmp port=5477 user=ck'`, prover and costing hint on, on `inst-one` (`one_index.json`), then on `inst-ck` back to back as a control (`one_index_control.json`).
- Queries: the 37 SEDE changes that need a recommended key, the 3 Discourse changes that need a filtered index, and the 6 changed application queries.
- **Result: 46 of 46 plans are the same on both builds.** One index at a time finds every real change that needs a filtered key.
- A first control run, after the server was restarted, showed 3 Discourse plans differing from the stored ones in access paths only (index-only scans after autovacuum set visibility maps). Hence the back-to-back comparison in the same state.

## Constructed workloads retimed under the default (2026-10-29)

`speedup.py`, `../musicbrainz/mb_stats.py` and `tpcds_views.py` (SF10) were rerun with `enable_conditional_unique_costing` off (the default). Earlier outputs are kept as `*_costing.json` / `log_*_costing.txt`.
- **Soft delete, tenants:** same plans as with the hint; speed-ups 1.01–5.75× (see the table above).
- **MusicBrainz:** the hint changes the plans of two queries (artist with primary English alias; releases with the release-group primary alias). Under the default they keep the stock plan, so 7 of 10 change, at 1.15–4.94×.
- **TPC-DS views, SF10:** the costing setting changes none of the 99 view plans (checked with `EXPLAIN`, prover on, hint on vs off). The rerun (`tpcds_views_sf10.json`) overlapped another experiment on the machine: base totals were 30% slower, and stock q41 took 918 s once. Re-timed alone, stock q41 takes 10.1 s three times. The paper keeps the earlier, uncontended run (`tpcds_views_sf10_costing.json`: 0.91–1.43×; 836 / 783 / 778 s), whose plans are the default's.
