# Feasibility checks for a paper on conditional UNIQUE (filtered unique indexes)

`schemas_study.py SCHEMADIR REPO` counts and classifies the unique indexes of public application
schemas and tests each for redundancy by implication (`schemas_study.json`). Schemas used
(fetched 2026-10-27, default branches):

- GitLab: https://gitlab.com/gitlab-org/gitlab/-/raw/master/db/structure.sql
- Mastodon, Forem, Chatwoot, Loomio, Consul, Open Food Network, Maybe, DocuSeal, Campsite:
  `db/schema.rb` on GitHub (Campsite: `api/db/schema.rb`)

Partition copies of GitLab's indexes are not counted.

`fragment_test.py REPO N` checks, against the SAT decider, the decision procedure for
single-template (conjunctive) conditions: one canonical pair for a nulls-distinct goal; for a
nulls-not-distinct goal, one pair per null/value choice on the open nullable key columns.

`pg_baseline.sql` / `.out` (PostgreSQL 18.6): each uniqueness-based planner optimisation with an
unconditional unique index and with a partial one whose predicate equals the query's.
Left-join removal, semi-join to inner join, inner-unique joins, GROUP BY column removal and
self-join elimination all fire for the unconditional index and none for the partial one; neither
removes DISTINCT. Source: `relation_has_unique_index_for` / `rel_supports_distinctness` /
`remove_useless_groupby_columns` skip any index with a predicate since commit 7fcd7ef2a9
(D. Rowley, 2023-06-19, bug #17975, back-patched to 11): predOK could be proved from join
clauses, which gave wrong results. Partial indexes with predOK still feed the planner's
distinct-count estimate (`has_unique_index`).

`sqlite_baseline.sql` / `.out` (SQLite 3.54.0). DISTINCT removal (`isDistinctRedundant`, where.c)
skips partial indexes. LEFT-join omission (`whereOmitNoopJoin`) uses the WHERE_ONEROW flag of the
chosen access path, which a partial unique index gets when every conjunct of its predicate is
implied *syntactically* by one ON/WHERE term (`whereUsablePartialIndex`, `sqlite3ExprImpliesExpr`:
equal expression, a branch of an OR, or IS NOT NULL). Measured: `ON ... AND b.d IS NULL` omits the
join; `b.st = 0` against `WHERE st IN (0, 1)` and `NOT (b.d IS NOT NULL)` against `WHERE d IS NULL`
do not, although both are implied.

SQL Server (documentation only; no local engine): filtered-index predicates are conjunctions of
`column op constant` (op in =, <>, IS [NOT] NULL, <, >, ...) and `column IN (constants)`, no OR;
a UNIQUE index treats NULL as a value (one NULL allowed), i.e. nulls-not-distinct semantics.
Filters are not allowed on PRIMARY KEY/UNIQUE constraints, only on unique indexes
(learn.microsoft.com, CREATE INDEX and Create Filtered Indexes, 2026). P. White (sql.kiwi,
2013-04) shows the optimizer does not derive uniqueness from a filtered unique index (one-to-one
merge join costed as many-to-many); not verified on a current version.

## Extended condition language (IN, NOT IN / <>)

`cunique.py`: template entries any / IS NOT NULL / IS NULL / IN(S) / NOT IN(S) (= and <> are the
singleton cases); exact implication by maximal per-column states (see its docstring).
`cunique_test.py REPO N`: agrees with brute force over all pairs (3,000 instances, extended
language) and with `implication.implies_sat` (3,000 instances, old language).
`cunique_complexity.py REPO N`: under the side conditions of the polynomial theorem (no NOT IN in
premises and no multi-constant IN in the goal on value-forced columns) no column has two maximal
states (10,640 instances); the two coNP-hardness reductions agree with a SAT solver (2 x 200 CNFs).
`color_check.py`, `color_check2.py`: the 3-colourability reductions for NOT IN (and IN with three
constants) on NOT NULL columns outside the key agree with brute force on 120 random graphs each (2026-10-30).
`schemas_ext.py SCHEMADIR REPO` -> `schemas_ext.json`: all 168 plain-column predicates of the
application schemas translate; every unique index as goal (both semantics) against the others:
2,953 of 2,960 decisions need one canonical pair, 7 have one open column; median 0.04 ms.
`cell_lemma_test.py REPO N`: the cell lemma behind a 3-ary axiomatisation of the extended
language (with NOT IN over all constants every profile is one template; Sigma |= phi iff each
cell of two profiles in phi's scope is vacuous or its canonical pair violates a member of
Sigma) agrees with brute force on 3,000 random instances (1,437 implied).
`armstrong_obstruction.py`: Armstrong tables need not exist. Two witnesses (one with constants,
one with nulls only): Sigma implies neither phi1 nor phi2, yet no table satisfying Sigma violates
both (argument in the docstring; exhaustive search up to four rows confirms).
`cover_test.py N`: the cell cover of a table (one constraint per pair of profiles over the
active domains and per minimal clean key, both semantics) implies exactly the conditional
UNIQUE constraints that hold on the table, with any constants: 400 random tables x 5 random
constraints, 0 mismatches. Cover sizes for tables of at most 5 rows and 3 columns: median 146,
max 4,232 members.

## X4: decisions on filtered-index-only catalogs (`x4_decisions.py`, 2026-10-28)

**Setup**
- Data: the E6b tables, mined keys and query generator (seed 11).
- Catalogs hold filtered unique indexes only, with no CHECKs.
- Decisions come from the real planners: PostgreSQL 18.6 (stock and with condunique), PostgreSQL 15.3 (built from source, the last release before the bug #17975 fix) and SQLite 3.54.0. They are compared with the implication models, and every decision is checked on the data.

**Results** for 1,454 left joins and 1,454 DISTINCT queries:

| Decider | Left joins removed | DISTINCT removed |
|---|---|---|
| PostgreSQL 18 | 0 | 0 |
| PostgreSQL 15.3 | 0 | 0 |
| SQLite | 33, plus 14 planner errors | 0 |
| Patched PostgreSQL | 1,094 | 171 (after the DISTINCT hook, 2026-10-28) |
| One index at a time (model) | 1,033 | 117 |
| Whole catalog (model) | 1,094 | 171 |
| Predicate read as UNIQUE (model) | 1,033 | 1,033, of which 167 wrong |

- PostgreSQL 15.3 removes no join: `predOK` is computed in `make_one_rel`, after `remove_useless_joins`. It does mark 1,033 joins as Inner Unique, none of them wrong.
- The patched planner agrees with the whole-catalog model on all 1,454 left-join decisions, and since the DISTINCT hook on all 1,454 DISTINCT decisions (171 removed, none wrong). The rerun is in `log_x4.txt`; the earlier run is kept as `log_x4_before_distinct.txt` and `x4_decisions_before_distinct.json`.

**SQLite planner error**

SQLite 3.54.0 (Apple build) raises "internal query planner error" on `sqlite_planner_error_min.sql`:

```sql
CREATE TABLE t (e INTEGER, a INTEGER);
CREATE UNIQUE INDEX i39 ON t (a) WHERE (e = 1);
CREATE UNIQUE INDEX i48 ON t (a) WHERE (e = 2);
SELECT a.a FROM t a LEFT JOIN t b ON a.a = b.a AND a.e = b.e AND ((b.e = 1) OR (b.e = 2));
```

- It fails both in EXPLAIN and on execution, and also with two different tables.
- With only one of the indexes, or with `b.e IN (1, 2)` instead of the OR, it plans normally.
- `sqlite_repro.py` minimises the failing case from the experiment's own tables.
- It has not been checked against current SQLite trunk.

## X4b: decisions on more tables (2026-10-29)

**Tables.** The second data folder (`Data sets 2`, the HPI dependency-discovery benchmarks), loaded by `../../discovery/datasets2.py` (per-file separator, header and null marker; `?` is NULL). Keys mined by `../../discovery/run_ds2.py` (the run_csv.py miner, all rows, keys of at most 3 columns, top 40 verified). Adult and chess give no keys: every column has under 1% distinct values, so no key column qualifies. The other seven: bridges (108 rows), flight (1,000 × 109), plista (20,000 × 40; 3 keys), cd (9,747 × 107), horse (300), hepatitis (155), breast (699).

**Run.** `X4_TABLES=bridges:uci.bridges,flight:hpi.flight,plista:hpi.plista,cd:hpi.cd,horse:uci.horse,hepatitis:uci.hepatitis,breast:uci.breast X4_OUT=x4_decisions_ds2.json python x4_decisions.py ...` (log `log_x4_ds2.txt`); CockroachDB in `crdb/` (`x4_crdb_ds2.json`).

**Classifier fix.** `SELECT DISTINCT k ... WHERE k = c` is planned as `Limit` by PostgreSQL 18 (and as a limit by CockroachDB): one row, correct. The first run counted that as DISTINCT removed (3 + 2 'wrong' removals by stock PostgreSQL on hepatitis and breast). A `Limit` now counts as keeping DISTINCT. The original X4 run is unaffected (the patched planner agreed with the model on every decision there).

| Decider | Left join (of 1,024) | DISTINCT (of 1,024) |
|---|---|---|
| removable on the data | 841 | 728 |
| PostgreSQL 18.6 | 0 | 0 |
| PostgreSQL 15.3 | 0 (760 Inner Unique) | 0 |
| SQLite 3.54 | 240, plus 35 planner errors | 0 |
| patched PostgreSQL 18.6 | 822, none wrong | 173, none wrong |
| one index at a time (model) | 764 | 164 |
| whole catalog (model) | 822 | 173 |
| predicate read as UNIQUE (model) | 764 | 764, of which 110 wrong |

The patched planner agrees with the whole-catalog model on all 2,048 decisions.

## X6b: discovery timings on more tables (`x6_hyucc.py ds2 20`, 2026-10-29)

The 9 tables above, all rows, 21 conditions × 2 semantics (330 non-trivial scopes), `x6_hyucc_ds2.json`, `log_x6_ds2.txt`. Run while another project's experiment kept the load average near 8; algorithms are compared within the run.
- HyUCC and HPIValid agree on all 330 scopes. FixC (unbounded) finished 298 within 20 s and agrees on all; FixC≤3 finished and agrees on all 330.
- HPIValid median per table 0.04–19 ms; HyUCC 0.2–750 ms (flight: about 27,000 minimal keys per scope); FixC≤3 1–1,550 ms.

## X4c: decisions on sampled open-data tables (LakeBench, 2026-10-30)

**Sample.** LakeBench's OpenData archives (github.com/BIT-DataLab/LakeBench), read over HTTP byte ranges without downloading the whole archive (`remotezip.py`, scripts kept outside the data directories). The CAN and UK links return 404. Each CSV was screened on its first 32 KB (`screen.py`): a column with 2–20 values (a scope), an identifier-like column, a column with 5–80% NULLs, an estimated 1,000+ rows, at most 60 MB.
- SG: 800 CSVs parsed, 85 promising, all 85 taken.
- USA (5,177 CSVs, 51 GB): 1,089 of a random 1,200 parsed, 331 promising, 200 taken.
- NA-like strings (`na`, `n/a`, `null`, `none`, `nan`, `-`) are NULL. Header names are cut to 56 bytes, because PostgreSQL cuts identifiers at 63 bytes and longer names collided. Five USA files carry stray zip-header bytes before the first column name (a flaw in LakeBench's files); the rest of each file is ordinary CSV, so they are kept.
- Tables listed in `../../discovery/lakebench_tables.json`; keys mined by `run_ds2.py` (budget 300 s; logs in `../../discovery/results_lb/`).

**Keys.** 217 of the 285 tables (148 USA, 69 SG) have verified conditional keys: 6,917 in all (3,293 cand, 1,930 cert, 1,079 pos, 615 dom). The tables have 738 to 210,552 rows (median 14,296).

**Run.** `X4_TABLES=$(cat ../../discovery/results_lb/withkeys.txt) X4_OUT=x4_decisions_lb.json python x4_decisions.py ...` (log `log_x4_lb.txt`). 15,173 indexes built; 119 failed on PostgreSQL's B-tree row limit (long geometry text on 9 tables) and are left out of the model.

**Classifier fixes in this run.** Plans are now classified by node names only. The first run matched words in the whole plan text, and the column `"In City Limits"` read as a `Limit` node (4 DISTINCTs on lbusa.t22404 counted as kept). The earlier runs are unaffected: no key or predicate there contains a node name. The query generator also allowed a table with a single condition atom (it sampled two).

| Decider | Left join (of 29,408) | DISTINCT (of 29,408) |
|---|---|---|
| removable on the data | 24,843 | 21,231 |
| PostgreSQL 18.6 | 0 | 0 |
| PostgreSQL 15.3 | 0 (22,070 Inner Unique) | 0 |
| SQLite 3.54 | 4,192, plus 1,123 planner errors on 50 tables | 0 |
| patched PostgreSQL 18.6 | 23,692, none wrong | 4,962, none wrong |
| one index at a time (model) | 22,209 | 3,999 |
| whole catalog (model) | 23,692 | 4,962 |
| predicate read as UNIQUE (model) | 22,171 | 22,171, of which 3,121 wrong |

- The patched planner agrees with the whole-catalog model on all 58,816 decisions.
- It removes a DISTINCT on 130 of the 217 tables. Reading the index predicate as plain UNIQUE would give a wrong DISTINCT removal on 133 tables.
- SQLite's errors are all "internal query planner error"; they count as not removed.

## X6c: discovery timings on sampled open-data tables (`x6_hyucc.py lb 20`, 2026-10-30)

40 of the 217 tables, chosen at random (seed 7, `../../discovery/results_lb/subset40.txt`); `x6_hyucc_lb.json`, `log_x6_lb.txt`. Each table is cut to the at most 18 key columns of the miner plus up to 12 columns with 2–20 values for conditions. Unbounded FixC ran out of memory on a 176-column table, which killed the first run.
- 1,630 non-trivial scopes (1,539 to 163,414 rows). HyUCC, HPIValid, FixC and FixC≤3 agree on all; no timeouts.
- Median per table: HPIValid 0.03–8.5 ms (median 0.4), HyUCC 0.06–178 ms (median 4.3), FixC≤3 1.7–3,601 ms (median 77).

## X6: discovery against UCC algorithms (`x6_hyucc.py`, 2026-10-28)

**Setup.** Each scope is encoded as for `fixc.py` (U: every null a value of its own; U=: all nulls one value), written to CSV, and given to HyUCC and HPIValid of Desbordante 2.4.1 (C++, one thread; not Metanome's Java HyUCC). FixC (Python) runs unbounded and with keys of at most 3 columns, each with a 20 s budget.

- `conditions`: 7 tables × 21 conditions × 2 semantics (288 non-trivial scopes).
- `cols`: UniProt 20k rows, 10/25/50/100 columns, empty condition.
- `rows`: the complete 30-column UniProt exports with 16k, 32k, 128k, 256k and 512k rows.
- The local copy of `uniprot_539166r_100c.csv` is truncated (44 MiB, 24,173 complete rows). The first `rows` run on it is kept as `*_rows_100c_truncated.*`, but it is not a row-scaling result.

**Results**
- **Agreement:** HyUCC and HPIValid agree on all 336 scopes. FixC agrees wherever it finished: unbounded on 236 of 288 conditions scopes, ≤3 columns on 281.
- **Speed (conditions):** HPIValid medians are 0.1–61 ms per table and HyUCC 0.4–50,091 ms. HyUCC needs up to 21 min under U= on UniProt, where the median number of minimal keys is about 76,000. FixC≤3 takes 6.4× as long as HPIValid in the median, load included.
- **Columns:** HPIValid grows from 0.5 to 45 ms. HyUCC under U= takes 181 s at 100 columns.
- **Rows (16k→512k, 32×):**
  - HPIValid grows from 2.5 to 54 ms, and HyUCC from 18 to 1,479 ms (U, empty condition).
  - Loading the CSV takes 0.4 to 16 s and dominates both.
  - FixC≤3 takes 0.7 s at 16k and 16 s at 256k, and times out at 512k.
- **Framing:** the contribution is the reduction (scope plus encoding), not a new UCC algorithm.
