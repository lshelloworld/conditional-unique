# X5: application workloads (code-derived), 2026-10-28

Running the apps' test suites was not possible on this machine: it has system Ruby 2.6 and no Homebrew, Docker, Node or Redis. The user chose a **code-derived workload** instead.

## Steps

1. **`x5_indexes.py`** lists the filtered unique indexes from each app's current `db/schema.rb`, or `db/structure.sql` for GitLab, giving `x5_indexes.json`. The checkouts were shallow clones of 2026-10-27 (commits are recorded in the JSON):

   | App | Indexes |
   |---|---|
   | Mastodon | 14 |
   | Forem | 12 |
   | Chatwoot | 9 |
   | Loomio | 5 |
   | Maybe | 3 |
   | DocuSeal | 3 |
   | GitLab | 128 |
   | **Total** | **174** |

2. **Query sites (`sites_*.json`).** Four agents read the sources (read only, nothing executed). For each index they listed the code that reads the indexed table: joins, left joins, semi-joins, GROUP BY, DISTINCT and lookups. Each site comes with the SQL ActiveRecord generates and two flags:
   - the join binds the index key;
   - the query implies the index predicate.

   There are **325 sites**:

   | Construct | Sites |
   |---|---|
   | lookup (point query, upsert, validation) | 221 |
   | inner join | 41 |
   | semi-join | 32 |
   | distinct | 9 |
   | left join | 8 |
   | group by | 5 |
   | none | 9 |

   18 of the lookups carry an `ORDER BY ... LIMIT 1` that the partial key makes redundant. No system removes that, and we don't either.

3. **`x5_schema.py`** converts `schema.rb` into PostgreSQL DDL: tables, NOT NULL, primary keys, enums, and btree indexes exactly as declared, including `text_pattern_ops`. GitLab's `structure.sql` loads as is. All 174 indexes are created on the patched server (databases `x5_<app>`).

4. **`x5_workload.py`** (part A) plans each non-lookup site with the setting off and on. Placeholders the agents left in SQL (`...`, `<expr>`) are replaced by neutral SQL, listed in `x5_sql_fixes.json` (12 sites).

   | Measure | Count |
   |---|---|
   | Statements that plan | 90 of 95 |
   | Queries where the prover proves uniqueness stock PostgreSQL lacks | **22** (GitLab 18, Loomio 3, Chatwoot 1), on 18 indexes |
   | Joins newly marked Inner Unique | 11 |
   | Plans changed | 6 |

   The 6 changed plans:
   - 2 semi-joins become inner joins (Loomio poll exporter, GitLab virtual registries);
   - 2 IN sub-queries lose their de-duplication HashAggregate (GitLab `cd_rollouts`, merge-request closing issues);
   - 2 access paths change because the join is now known unique.

   No join is removed: the workload's left joins either use primary keys or need the joined columns.

   Of the 29 sites the agents flagged as interesting:
   - 16 get a proof;
   - the rest are joins on primary keys (stock PostgreSQL already proves those), or shapes PostgreSQL never asks about: anti-joins, IN under OR, DISTINCT.

   6 unflagged sites also get proofs.

5. **`x5_timing.py`** fills the tables these 22 queries read with 200,000 generated rows each, keeping all unique indexes, and dropping foreign keys and CHECKs. It then times each query with the setting off and on.
   - 12 of the 22 ran. GitLab's partitioned tables and deferrable unique constraints defeat generic data.
   - The queries are selective point-style lookups. Five returned rows, at 0.94–1.06×. All results were identical.
   - **Generated data shows no run-time gain here.** The large gains need workloads like those in `../pg_patch/speedup.py`.

6. **`x5_partb.py`** (part B): would a recommender propose the declared conditions? It hides the indexes and generates candidate conditions from two sources:
   - **schema roles:** nullable columns, booleans, and status/type/kind-like columns (constants from the data);
   - **workload:** the atoms in the code-derived queries, constants included.

   Recall of the 174 declared conditions (3 could not be parsed):

   | Kind of condition | Total | Schema roles | Workload (exact) | Either |
   |---|---|---|---|---|
   | Excluding nulls (`K IS NOT NULL`) | 87 | 86 | 14 | 86 |
   | Other conditions | 84 | 78 | 68 | **79** |

   - On the indexed tables, schema roles propose 2,776 candidate atoms and the workload 524.
   - The misses: `<> ''` non-empty-string conditions, two predicates the parser could not read (casts inside an ARRAY), and one condition that restates a NOT NULL column.
   - Keys from data (FixC) could not be evaluated: there is no real application data.

## Changes to the patch prompted by X5

Both were retested:
- the regression suite, with the setting off and on;
- the feature tests;
- differential runs of 40,000 queries (seed 99) and 60,000 with smallint columns (seed 314). None changed a result.

The changes:
- **Opclasses:** an index may use any opclass whose equality operator is the column type's default equality. This admits Mastodon's 5 `text_pattern_ops` indexes.
- **Cross-type equality:** any equality of the column type's default btree family is accepted, including cross-type ones such as `int2 = int4` and `int2 = ANY (int4[])`. Constants are identified by the family's cross-type equality. GitLab's enum columns are `smallint` but are compared with `integer` constants, so before this change the prover rejected them.

## After DISTINCT removal was added to the patch (2026-10-28)

Re-planning the 95 statements with the DISTINCT hook gives `x5_workload_distinct.json` and `log_x5_workload_distinct.txt`.

**The one new effect from DISTINCT removal**
- Query: GitLab `SELECT DISTINCT cd_rollouts.application_id FROM cd_rollouts WHERE state = 1 AND application_id IN (1, 2)`.
- Result: it loses its Sort and Unique nodes.
- Why: `index_cd_rollouts_on_application_id_non_terminal` is unique on `application_id` among non-terminal states, and `state = 1` implies that scope.
- The other 8 DISTINCT sites get no proof.

**Why the other differences don't count**
- By the time of this re-plan, the tables already held the 200,000 generated rows from `x5_timing.py`, and their foreign keys and CHECKs had been dropped.
- So the other differences from `x5_workload.json` reflect that changed data and constraints, not the patch.
- For example, two semi-joins now plan without a uniqueness test.
- The part A numbers above remain those of the empty schemas.

## Retimed on the current build (2026-10-29)

- `X5_IN=x5_workload_gate.json x5_timing.py 'host=/tmp port=5477 user=ck' 200000`, with `PGOPTIONS='-c enable_conditional_unique_costing=on'`. Previous run: `x5_timing_before_gate.json`, `log_x5_timing_before_gate.txt`.
- The script now re-times queries over 1 ms by 11 rounds alternating the setting (first dropped), as Discourse and SEDE do, and compares JSON result columns as text (a Forem query returns one, which crashed the first attempt).
- 28 queries; 9 fail on GitLab's generated data (inherited CHECKs, deferrable unique constraints, foreign keys already dropped). Every result is the same.
- 5 plans change on generated data. Only one takes over 1 ms: a Chatwoot query, 7.6 vs 7.7 ms, 0.93× by the alternating rounds. Its plan does not change in the workload run, only on these statistics.
- The GitLab DISTINCT proved through a CHECK is not timed: the timing drops CHECK constraints, since random rows violate them.
