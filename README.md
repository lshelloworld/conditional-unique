# When Can the Planner Trust a Filtered Unique Index?

Supplemental material for the ICDE 2027 submission by Ziheng Wei and Sebastian Link: the prover as patches to PostgreSQL 18.6 and CockroachDB 26.2.9, the experiment scripts, their results and logs, and the extended version of the paper with proofs.

## What is here

| Path | Contents |
|---|---|
| `paper/` | The LaTeX source and `conditional-unique-extended.pdf` (appendix with proofs, axiomatisation, recommender) |
| `experiments/sql_unique/pg_patch/` | `condunique-pg18.6.patch`, the differential test, feature tests, mutants, planning and speed-up measurements |
| `experiments/sql_unique/crdb/` | `condunique-crdb-v26.2.9.patch`, probes and decisions on CockroachDB |
| `experiments/sql_unique/` | Theory checks, decision experiments, discovery timings, and one folder per workload |
| `experiments/tpcds/` | TPC-DS loading, key mining, stability and refresh emulation |
| `experiments/qo_reasoning/`, `reasoning/`, `cleaning/`, `cleaning_real/`, `qo/`, `rewriter/` | Query generator, implication code and earlier experiments it builds on |
| `discovery/` | The conditional-key miner, its results, and the LakeBench sampling scripts |
| `validation/` | Early checks of the axioms and the theory |

Every experiment folder has a `README.md` with its setup, commands and results, written as the work went along. Some of them mention earlier runs (`*_before_*`) and scratch directories that are not in this repository. Paths are shown as `<repo>`, `<scratch>` and `<data>`.

## Where each result comes from

| Paper | Script (under `experiments/sql_unique/` unless stated) | Output |
|---|---|---|
| Table I, predicate shapes | `schemas_study.py`, `schemas_ext.py`, `schemapile/sp_count.py` | `schemas_study.json`, `schemas_ext.json`, `schemapile/sp_count.json` |
| Table II, what systems do | `pg_baseline.sql`, `sqlite_baseline.sql`, `crdb/probe.sh`, `mssql/probe.sh` | `*.out`, `*/log_probe.txt` |
| Theorems, on random instances | `cunique_test.py`, `cunique_complexity.py`, `translate_test.py`, `cell_lemma_test.py`, `color_check.py`, `color_check2.py` | stdout |
| VI-A soundness | `pg_patch/x2_difftest.py`, `pg_patch/cu_feature.sql`, `pg_patch/mutants/` | `pg_patch/x2_difftest*.json`, `pg_patch/log_x2*.txt` |
| VI-B decisions, Table IV | `x4_decisions.py`, `crdb/x4_crdb.py` | `x4_decisions*.json(.gz)`, `crdb/x4_crdb*.json` |
| VI-C cost | `pg_patch/plan_overhead.py` | `pg_patch/plan_overhead*.json` |
| VI-D gains, Table V | `apps/`, `dbt/`, `discourse/`, `musicbrainz/`, `stackexchange/`, `sdss/`, `quarry/`, `pg_patch/speedup.py`, `pg_patch/tpcds_views.py` | logs and JSON in each folder |
| VI-E keys | `stackexchange/se_mine.py`, `experiments/tpcds/` , `discovery/`, `x6_hyucc.py` | `se_mine.json`, `experiments/tpcds/*.json`, `x6_hyucc*.json` |

## Build the patched PostgreSQL

```bash
curl -O https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2
tar xf postgresql-18.6.tar.bz2 && cd postgresql-18.6
patch -p1 < ../experiments/sql_unique/pg_patch/condunique-pg18.6.patch
./configure --prefix=$PWD/../inst --without-icu --without-readline --without-zlib --enable-debug CFLAGS=-O2
make -j8 && make install
../inst/bin/initdb -D ../pgdata -U ck --auth=trust
../inst/bin/pg_ctl -D ../pgdata -l ../pg.log -w start -o "-p 5444"
```

The prover is off by default. Turn it on with `SET enable_conditional_unique = on`; `enable_conditional_unique_costing` additionally lets a proof over a filtered index mark a join `Inner Unique`.

## Run the differential test

```bash
python -m venv venv && . venv/bin/activate && pip install -r requirements.txt
python experiments/sql_unique/pg_patch/x2_difftest.py "host=localhost port=5444 user=ck dbname=postgres" 50 40 7
```

This compares each query with the setting off and on and writes `x2_difftest.json` next to the script. `X2_SHAPES`, `X2_JOINS` and `X2_CHECKS` select the shapes, as the script's docstring explains; `X2_SHAPES=B` is bug #17975.

To check that the test has power, apply a mutant to the patched tree and rebuild, for example:

```bash
patch -p1 < ../experiments/sql_unique/pg_patch/mutants/M11_bug17975_predOK.patch
```

## Limitations

- **Mutants.** `pg_patch/mutants/` re-expresses the 11 mutants against the final source; each applies and compiles there. The numbers in the paper and logs were measured on the source of the time, as `pg_patch/README.md` records, and M11 is the only one run on the final source.
- **Experiment-only builds.** `pg_patch/one_index.py` and `stackexchange/se_norc.py` used builds (`inst-one`, `inst-norc`) whose small changes are described in `pg_patch/README.md` but not provided as patches.
- **Timings** come from one Apple M5 Max and will differ elsewhere; decisions and plan changes should not.
- **Data** is mostly not redistributed, see [DATA.md](DATA.md). Scripts that read it take its location from arguments or from `CU_DATA1`, `CU_DATA2` and `CU_EXPORTS`.

## Licence

See [LICENSE](LICENSE).
