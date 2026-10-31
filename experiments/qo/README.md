# Query optimisation experiment

Uses the top conditional keys of `discovery/report.md` (QO and GROUP BY trap lists) on the
pseudonymised Hockey and VOC exports. Results: `results.md` (summary), `results_qo_x1.json`
and `results_qo_x50.json` (all measurements, plans, SQL).

## Files

- `cases.py`: the 13 cases (conditional key, class, scope predicate). Constants are the hashed
  values looked up in `discovery/results/*.json`.
- `run_qo.py`: loads the tables, runs each query template original vs. rewritten under three
  physical configurations, checks correctness, writes JSON.
- `summarize.py`: writes `results.md`.

## Design

Templates per case (K the key, P the scope predicate, t the table):
DISTINCT over K, GROUP BY K, LEFT JOIN of t with the scope of t on K (join elimination), and
EXISTS over the scope (semi-join to join). DISTINCT/GROUP BY rewrites are licensed by domain keys
(and the stronger certain/candidate keys), join rewrites by possible keys; the GROUP BY trap
cases run the unlicensed DISTINCT/GROUP BY rewrites to show they are wrong.

Configurations: `none` (no index), `idx` (plain btree on K), `uq` (the conditional key enforced
as filtered unique index(es): `UNIQUE (K) WHERE P`, with `NULLS NOT DISTINCT` for domain keys and
one filtered index per null pattern for the certain key).

Each query: 2 warm-up runs, then the median of `--reps` `EXPLAIN (ANALYZE, FORMAT JSON)` runs.
Correctness compares result multisets of original and rewrite, with and without P. `--scale k`
loads every table k times, offsetting the key columns of each replica (keys, scopes and null
patterns are preserved, replicas never collide).

## Reproduce

A private PostgreSQL 18 instance (trust auth, localhost only, port 5444; no parallel workers,
JIT off) was used so that the shared server on this machine is not touched:

```bash
/Library/PostgreSQL/18/bin/initdb -D <dir>/pgdata -U ck --auth=trust -E UTF8 --locale=C
```

```bash
/Library/PostgreSQL/18/bin/pg_ctl -D <dir>/pgdata -o "-p 5444 -c listen_addresses=localhost -c shared_buffers=256MB -c max_parallel_workers_per_gather=0 -c jit=off" -l <dir>/pg.log start
```

```bash
/Library/PostgreSQL/18/bin/createdb -h localhost -p 5444 -U ck ckqo
```

```bash
python run_qo.py --reps 9 --out results_qo_x1.json
```

```bash
python run_qo.py --reps 7 --scale 50 --out results_qo_x50.json
```

```bash
python run_qo.py --datasets ncvoter,uniprot --reps 7 --out results_qo_xreal.json
```

```bash
python summarize.py
```

The real-scale run (NCVoter, 1,023,993 rows; UniProt, 24,173 rows; text columns, loaded with
`discovery/run_csv.py`) used `shared_buffers=1GB` and `work_mem=64MB`; the Hockey/VOC runs used
`shared_buffers=256MB`. Certain keys are enforced by one filtered unique index per null pattern
of the key columns that are nullable within the scope.

Requires `psycopg` (3.x). Timings were taken while another PostgreSQL server on the same
machine was running a long insert workload, so absolute times carry some noise; all
comparisons are paired (same session, same configuration).

## PostgreSQL and partial unique indexes

`pg_partial_index.sql` (output in `pg_partial_index.out`) isolates what PostgreSQL 18.6 does
on its own. With a partial unique index `UNIQUE (k) WHERE s = 1` and queries whose predicate
implies `s = 1`, neither the left join (predicate in `ON` or in a subquery) nor the inner
self-join is removed, and `DISTINCT` stays. With a full unique index on `k`, the left join and
the self-join (self-join elimination, on by default in PG 18) are removed; `DISTINCT` stays
in that case too.
