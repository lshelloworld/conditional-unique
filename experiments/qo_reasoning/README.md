# E6b: query optimisation that has to reason

`run_e6b.py` builds, per table, the catalog an optimiser would see for the verified mined
keys (filtered unique indexes, NULLS NOT DISTINCT indexes, conditional NOT NULL checks,
per-null-pattern index families for certain keys), generates queries whose predicates differ
from the index predicates (refined scopes, extended keys, unions of scopes, random controls),
decides the DISTINCT and LEFT JOIN rewrites by implication from the whole catalog (Algorithm 1
when b <= 10, else SAT), from one catalog constraint at a time, and by UNIQUE semantics, and
checks every decision against the data in PostgreSQL. Licensed rewrites are timed with
EXPLAIN ANALYZE (median of 5). `summarize_e6b.py` writes `results_e6b.md`.

Uses the private PostgreSQL instance described in `../qo/README.md` (port 5444).

```bash
python run_e6b.py
```

```bash
python summarize_e6b.py
```

## Fewer open positions

`rerun_decisions.py` recomputes every E6b decision without the database, with and without the
exact reductions of `reasoning/implication.py` (`restrict`: drop premise templates incompatible
with the target's templates; `dominated`: fix the choice on columns outside the target key that
have a dominant choice). All 2,908 decisions are unchanged; b drops from 6-40 to 2-20 and
Algorithm 1 (b <= 10) decides 71% of the queries instead of 9%. Output: `results_e6b_pruned.json`.
Validation: `reasoning/test_implication.py` (1,500 instances against exhaustive search) and
`reasoning/test_pruning.py` (3,000 eight-column instances against the SAT baseline).

## E6c: partial- and certain-key rewrites

`run_e6c.py`: subsumption removal (licensed by partial keys) and null-as-wildcard lookups
(licensed by certain keys) on the scopes of mined keys of every class; ground truth computed
exactly in Python, licensed rewrites timed in PostgreSQL (originals are quadratic; 60 s statement
timeout, timed-out originals reported as lower bounds). Hockey and VOC: 3 runs per query;
UniProt: 1 run (`--reps 1`). Output: `results_e6c.json`.
