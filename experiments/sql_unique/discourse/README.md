# X11: Discourse Data Explorer reports (2026-10-28)

**Sources** (read only: nothing from Discourse is executed; the schema is applied as SQL, and the reports are only planned or run in a read-only session):

| Source | Blocks |
|---|---|
| discourse-data-explorer built-ins (`lib/discourse_data_explorer/queries.rb`) | 19 |
| meta.discourse.org: 784 topics tagged `sql-query` or in category 148, read via `/raw/<id>` (1.5 s between requests, generic crawler name) | 843 |
| SidVal/discourse-data-explorer list (`querys.md` and the `.sql` files it links) | 79 |

- **Schema:** `db/structure.sql` of discourse/discourse (main, 2026-10-27), loaded as database `x11_discourse` on the patched server (port 5444) by `load_schema.py`.
  - pgvector is not built, so `halfvec` columns become `bytea`.
  - The 5 triggers guarding deprecated columns are skipped.
  - Result: 396 tables, 708 unique indexes, 41 with predicates.
- **Copyright:** the reports are user posts, so they are cited by URL and not redistributed. `queries_raw.json` is a local working copy; do not publish it.

**Scripts**
1. `collect.py CACHE`: writes `queries_raw.json`.
2. `x11_workload.py DSN`: writes `x11_workload.json` and `log_x11_workload.txt`.
   - Parameters are replaced by typed literals.
   - Blocks that list several queries are split only at complete statements (sqlglot).
   - Non-`SELECT`s are dropped, as are duplicates.
   - Each report gets `EXPLAIN` off/on.
3. `x11_timing.py DSN N`: writes `x11_timing.json` and `log_x11_timing.txt`.
   - Discourse-shaped data for N = 100,000 users.
   - Each affected report is timed off/on: median of 5 after 2 warm-ups.

**Results**

| | Reports |
|---|---|
| distinct read-only reports | 824 (19 built-in, 722 meta, 83 SidVal) |
| plan on the current schema | 722 (the rest: elided snippets, tables or columns since dropped) |
| read a table with a filtered unique index | 395 |
| name its predicate columns | 39 |
| prover proves uniqueness stock PostgreSQL lacks | **25** (22 via `user_emails (user_id, primary) WHERE primary`) |
| plan changed | 5 (1 left join removed, /t/275036; 1 GROUP BY key shortened, /t/272301; join order) |
| a join newly `Inner Unique` | 15 |

- **Index usage:** every planned report that joins `user_emails` on `primary` gets the proof.
- **Shapes not handled:** 14 of those 22 de-duplicate with `DISTINCT` or `GROUP BY` over the join. That needs uniqueness carried through joins, which neither PostgreSQL nor the patch does.

**Run times**
- **Data:** 100k users, each with one primary address and 0–2 others (300k addresses); 200k topics (5% deleted); 1M posts (3% deleted); 2M visits; 500k post actions.
- **Coverage:** 24 of the 25 reports ran; /t/408953 divides by zero on this data.
- **Speed:** the 17 that take over 1 ms run 0.96–1.15× as fast with the prover. That is within run-to-run noise.
  - The removed join gives 1.05× (940 → 893 ms).
- **Results:** identical.

**First data attempt:** X5's filler narrows every column any report compares with a constant to 1..3, which left `posts` with 9 rows and most reports empty. It was replaced by the Discourse-shaped generator in `x11_timing.py`.

## Retimed on the current build (2026-10-29)

- `x11_timing.py 'host=/tmp port=5477 user=ck dbname=x11_discourse' 100000`, with `PGOPTIONS='-c enable_conditional_unique_costing=on'`, over the 30-change workload. Previous run: `x11_timing_before_gate.json`.
- 60 reports timed, 1 error, every result the same. 32 plans change on this data.
- 23 changed reports take over 1 ms: 0.96–1.06× by 11 alternating rounds (was 0.93–1.07).
- The paper's range is the alternating measurement (`speedup_alt`); `speedup` is the five-run median per setting, kept for reference.
