# Filtered unique indexes in SchemaPile (2026-10-29)

**Data:** SchemaPile-Perm (T. Döhmen, R. Geacu, M. Hulsebos, S. Schelter, "SchemaPile: A Large Collection of Relational Database Schemas", Proc. ACM Manag. Data 2(3), 2024).
- Zenodo record 12682521, v0.2, CC BY 4.0: `schemapile-perm-sqlfiles.tar.gz`, 152.8 MB.
- 22,989 permissively licensed schemas from public GitHub repositories, as 39,720 SQL files.
- The full corpus of 221,171 schemas is not distributed.

**Script:** `sp_count.py TARBALL` reads the SQL straight from the tarball as text and writes `sp_count.json`.
- **Unique indexes:** counts `CREATE UNIQUE [CLUSTERED|NONCLUSTERED] INDEX`, plus UNIQUE/PRIMARY KEY in CREATE TABLE and ALTER TABLE.
- **Predicates:** classifies the predicate of each filtered unique index into the paper's shapes.
- **Dialect:** guessed from lexical cues (`dialect()`).
- It is a lexical count, not a parse; comments are stripped and statements are split at `;`.

## Results

| Dialect (guessed) | Files | `CREATE UNIQUE INDEX` | Filtered | Share | Files with one |
|---|---|---|---|---|---|
| SQL Server | 3,561 | 913 | 118 | 12.9% | 45 |
| PostgreSQL | 5,218 | 3,362 | 182 | 5.4% | 46 |
| SQLite | 683 | 397 | 5 | 1.3% | 2 |
| MySQL (no filtered indexes) | 20,234 | 1,496 | 1 (mis-guessed file) | – | 1 |
| unknown | 10,024 | 8,412 | 50 | 0.6% | 30 |
| **all** | 39,720 | 14,580 | 356 | 2.4% | 124 |

Plus 403,788 UNIQUE/PRIMARY KEY clauses in CREATE TABLE and 86,494 in ALTER TABLE. These cannot carry a predicate.

**Predicate shapes** of the 356. A predicate can count under several shapes.
- Constant or flag: 184.
- `IS [NOT] NULL` on another column: 101.
- Excludes null keys: 119 contain such an atom; for 66 it is the only kind.
- `IN`: 6. Inequality: 6. Range: 6. Other: 5.
- Conjunctions: 69. With OR: 8. Expression key: 28.

These match the paper's ten application schemas: mostly conjunctions of constants, flags and null tests, rarely OR, almost no ranges.
