# SQL Server and filtered unique indexes (2026-10-28)

**Setup:**
- Microsoft SQL Server 2025 (RTM-CU10, 17.0.5035.5), Developer edition.
- Official image `mcr.microsoft.com/mssql/server:2025-latest`, run in OrbStack under Rosetta (x86-64 emulation).
- Licence accepted at the user's instruction.
- The container listens only on `127.0.0.1:14333`. The `sa` password is a generated local test password in `.sa_password` (mode 600; not for reuse).

**Running it:** `probe.sh` runs `setup.sql` and prints the `SHOWPLAN_TEXT` operators for the same queries as `../crdb`. Output: `log_probe.txt`.

```bash
./probe.sh cu-mssql > log_probe.txt
```

**Pitfall:** `sqlcmd` runs with `QUOTED_IDENTIFIER OFF` by default, and SQL Server then refuses to create filtered indexes (Msg 1934). The script passes `-I`, and checks `sys.indexes` for the three filtered indexes. A first run without `-I` had no filtered indexes and was discarded.

| Rewrite | Unique constraint (`bu`) | Filtered unique index, query predicate = index predicate (`bf`) |
|---|---|---|
| Left-join removal (subquery or `ON` form) | yes | no |
| Semi-join to join | yes (hash inner join) | no (hash right semi join) |
| `DISTINCT` removal | yes | no (`Sort DISTINCT`) |
| `GROUP BY` removal | yes | no (`Sort DISTINCT`) |

Also not used:
- `UNIQUE (k) WHERE k IS NOT NULL` (`bn`): `DISTINCT k ... WHERE k IS NOT NULL` keeps a Stream Aggregate directly above an ordered scan of that filtered unique index.
- a filtered index whose predicate the query implies, `st = 0` against `WHERE st IN (0, 1)` (`bfs`).

The tables are tiny (100–1,000 rows). Join elimination and aggregate removal are simplifications applied before costing, so table size does not decide them.
