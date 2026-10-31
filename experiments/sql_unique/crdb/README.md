# CockroachDB and filtered unique indexes (2026-10-28)

**Setup:** CockroachDB v26.3.0, the official darwin arm64 binary (checksum verified), one in-memory node. `probe.sh` creates the tables of `setup.sql` and prints `EXPLAIN (OPT)` for each rewrite, with an unconditional unique index on `k` (`bu`) and a partial one, `UNIQUE (k) WHERE d IS NULL` (`bf`), queried with exactly that predicate. Output: `log_probe.txt`.

```bash
./probe.sh /path/to/cockroach localhost:26299 > log_probe.txt
```

| Rewrite | Unconditional | Partial |
|---|---|---|
| Left-join removal (subquery or `ON` form) | yes | no |
| `DISTINCT` removal | yes | no |
| `GROUP BY` reduction | yes | no |
| Semi-join to join | no | no |

Also not used:
- a partial `UNIQUE WITHOUT INDEX (k) WHERE d IS NULL` constraint (`bc`);
- an index that only excludes NULL keys, `UNIQUE (k) WHERE k IS NOT NULL` (`bn`);
- a predicate the query implies, `st = 0` against `WHERE st IN (0, 1)` (`bfs`).

**Source** (`pkg/sql/opt/memo/logical_props_builder.go`, master):
- `MakeTableFuncDep` skips partial unique indexes and partial unique constraints, because "their keys are only unique for a subset of the rows".
- `buildScanProps` adds the key of a partial unique index to a scan *of that index*.
- That scan is an alternative found during exploration. Join elimination, `DISTINCT` removal and grouping reduction are normalisation rules, applied to the table's canonical scan. So the key reaches none of them: `DISTINCT k` stays above `scan bf@bf_k,partial`.
- This last step is inferred from the plans and the norm/explore split, not traced line by line.

# A second implementation: the prover in CockroachDB (2026-10-29)

**Build.** CockroachDB v26.2.9, the newest public release tag; the v26.3.0 release commit is not in the public repository. Source cloned from github.com/cockroachdb/cockroach, built with Bazelisk (`bazel build //pkg/cmd/cockroach-short`) in the session scratchpad. Stock behaviour of v26.2.9 matches the 26.3 probe above (setting off: no partial key used).
- Host fix: the Command Line Tools default to the macOS 27.0 SDK, whose library stubs this linker cannot read (plain `clang hello.c` fails too). The build uses `SDKROOT=.../MacOSX.sdk` (26.5), set in `.bazelrc.user` and in Bazel's generated `cc_wrapper.sh`.

**Patch** (`condunique-crdb-v26.2.9.patch`, 8 files, 825 added lines):
- `pkg/sql/opt/memo/cond_unique.go` (793 lines): the prover in Go.
- `logical_props_builder.go` (4 lines): in `buildSelectProps`, for a `Select` directly over a `Scan`, add the keys the prover proves to the Select's functional dependencies. A strict key where NULLs may be equal (U=), a lax key where they are distinct (U).
- Session setting `optimizer_use_conditional_unique` (default off): `vars.go`, `session_var_descriptions.go`, `sessionmutator/mutator.go`, `local_only_session_data.proto`, `memo.go` (staleness check).

**How it fits.** CockroachDB's existing rules (join elimination, `DISTINCT` and grouping reduction) and its propagation of keys through joins read functional dependencies, so the patch only adds keys. Filters that read only the inner table are pushed into a `Select` over its scan; filters that read the outer side stay in the join. So the prover sees base restrictions only, which excludes the bug #17975 shape by construction.

**Prover:**
- **Templates:** per column any, IS NOT NULL, IS NULL, IN S, NOT IN S.
- **Index predicates:** translated exactly, with `OR` giving several templates; otherwise the index is not a premise.
- **Filters and validated CHECKs** (those CockroachDB keeps as never-NULL filters) are over-approximated: an untranslatable conjunct is dropped, and a range comparison with a constant reads as IS NOT NULL.
- **Search:** for a violating pair, with per-column feature sets "row 1/2 fails template l of premise p" and "rows differ on p's key", keeping maximal sets only. Values tried per column are the constants mentioned there, NULL and two fresh values.
- **Premise filter:** a premise is used only if its key lies in the goal key plus the columns the goal fixes.
- **Candidate keys:** each unique index key, and each extended by the columns that every goal template restricts to finitely many values (the key of a union of scopes).
- **Limits:** 16 templates, 256 premises, 10^5 search nodes. Partial `UNIQUE WITHOUT INDEX` constraints are not read.

**Development steps,** each found on the Table IV catalogs (Hockey.Coaches):
1. Splitting an `OR` predicate into one premise per disjunct (sound, weaker): 62 of 131.
2. Premises with several templates: 107.
3. Premise cap 64 → 256: 122.
4. Union-of-scopes candidate keys: 130.
5. Premise filter: Hockey.Teams 140 → 152 of 152.
6. Each index key also extended by a single finite column (found on uci.breast in the data-set extension below): Table IV 1,143 → 1,146 of 1,148.

**Probes** (`probe_cu.py`, output `log_probe_cu.txt`), each with the setting off and on, results compared:

| Query | Off | On |
|---|---|---|
| left join, query predicate = index predicate (both forms) | kept | removed |
| DISTINCT, GROUP BY under the index predicate | kept | removed |
| implied predicate (`st = 0` against `st IN (0, 1)`) | kept | removed |
| `UNIQUE (k) WHERE k IS NOT NULL`: left join, DISTINCT | kept | removed |
| one of two scopes | kept | removed |
| left join over a nullable key (U suffices) | kept | removed |
| CHECK gives every primary alias a locale (MusicBrainz) | kept | removed |
| bug #17975 shape, predicate only via a join clause | kept | kept |
| union of two scopes on `k` | kept | kept |
| DISTINCT over a nullable key (needs U=) | kept | kept |
| running example without `e.prim` | kept | kept |
| semi-join to join | kept | kept (stock CockroachDB has no such rewrite, even for full keys) |
| running example (DISTINCT through the join) | kept | kept, plan reduced to grouping by `email` |

All 17 return the same result with the setting off and on.

The running example keeps its DISTINCT because of CockroachDB's functional dependencies, not the prover. The prover gives `cu_e` a lax key `(uid, prim)`. CockroachDB does not turn it into a strict key of the join, although the join equality makes `uid` non-null. With `uid NOT NULL` declared (`cu_e2`) the DISTINCT is removed.

**Table IV catalogs** (`x4_crdb.py`, output `x4_crdb.json`, log `log_x4_crdb.txt`). Same tables, keys, queries and seed as `../x4_decisions.py`. CockroachDB has no NULLS NOT DISTINCT, so dom and cert keys become one nulls-distinct index per null pattern, without the all-NULL pattern. That catalog implies fewer DISTINCTs than PostgreSQL's, so the numbers are not comparable with Table IV line by line. The model is implication from exactly the indexes CockroachDB built (all built, none failed).

| Decider | Left join (of 1,454) | DISTINCT (of 1,454) |
|---|---|---|
| removable on the data | 1,208 | 985 |
| stock CockroachDB (setting off) | 6 | 0 |
| one index at a time (model) | 1,087 | 0 |
| patched CockroachDB | 1,146, none wrong | 83, none wrong |
| whole catalog (model) | 1,148 | 83 |

- The 6 stock removals are joins that can never match (`b.SHA = a.SHA` with `b.SHA IS NULL`), not uses of the partial indexes.
- The patched planner misses 2 left joins that the catalog implies, both sound refusals: one scope of 7 disjuncts (likely the search limit) and one union of two scopes. An earlier build missed 5; the last 3 came back when each index key was also extended by single finite columns (step 6 below).

**More tables** (`X4_TABLES=... X4_OUT=x4_crdb_ds2.json`, log `log_x4_crdb_ds2.txt`): the seven tables of `../../../discovery/datasets2.py` with mined keys (see `../README.md`, X4b).

| Decider | Left join (of 1,024) | DISTINCT (of 1,024) |
|---|---|---|
| stock CockroachDB | 14 (joins that never match) | 0 |
| one index at a time (model) | 764 | 0 |
| patched CockroachDB | 821, none wrong | 57, none wrong |
| whole catalog (model) | 822 | 58 |

The classifier counts a `limit` as keeping `DISTINCT`: over columns the query fixes to constants, CockroachDB (like PostgreSQL) de-duplicates with a limit of one.

**Sampled open-data tables** (`X4_TABLES=$(cat ../../../discovery/results_lb/subset40.txt) X4_OUT=x4_crdb_lb.json`, log `log_x4_crdb_lb.txt`): 40 of the 217 LakeBench tables with mined keys, chosen at random (see `../README.md`, X4c). 2,939 indexes, all built.

| Decider | Left join (of 5,515) | DISTINCT (of 5,515) |
|---|---|---|
| removable on the data | 4,679 | 3,978 |
| stock CockroachDB | 91 (joins that never match) | 0 |
| one index at a time (model) | 4,250 | 0 |
| patched CockroachDB | 4,535, none wrong | 225, none wrong |
| whole catalog (model) | 4,543 | 229 |

- The 12 misses are refusals: 4 DISTINCTs over a union of two scopes (lbsg.t75), 3 left joins under scopes of 3 to 8 disjuncts, and 5 left joins for random keys of 2 or 3 columns under one-atom conditions. They are not diagnosed one by one; likely causes are the search limit and the candidate-key list.
- **Loading.** COPY into a table that already has the partial unique indexes failed on lbsg.t12. It reported a violation of `UNIQUE (date, street, ssic) WHERE (type = 'Sole Proprietor' OR type = 'Partnership') AND ... IS NOT NULL` for two rows whose type is NULL. Row-by-row INSERT with the same indexes succeeds, and so does COPY with that index alone. Not checked on a stock build. The script now loads the rows first and then creates the indexes.
- **Classifier.** Plans are classified by operator names only (column names such as `"In City Limits"` contain `limit`). A limit pushed into a scan (`limit: 1` under `scan ...,partial`, for `DISTINCT k ... WHERE k IS NULL`) counts as a limit.

