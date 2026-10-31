# SDSS SkyServer: queries astronomers type, over a schema built on scopes (2026-10-29)

## Sources
All metadata and queries were read through SkyServer's public SQL search web service (`https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch`), which needs no login.

- **Query log:** `WebLog..SqlLog`, filtered to `access = 'Skyserver.Search.SQL'` (the SQL search form, where people type queries; the web service traffic is mostly scripts) and `error = 0`, January 2025 to July 2026 (the log has no rows after July 2026).
  - `sdss_log.py CACHE 2025-01 2026-10` fetches one month per request, 5 s apart, as JSON.
  - It fetches only the statement, its database and the number of runs, never client addresses.
  - Result: 23,135 distinct statements from 41,282 runs (`sdss_log.json`, `log_sdss_log.txt`).
- **Schema:** INFORMATION_SCHEMA and the view definitions of BestDR18, saved as JSON in the scratch directory.

## The scopes
- **Scope views:**
  - `PhotoPrimary = PhotoObjAll WHERE mode = 1`; `Galaxy` and `Star` are PhotoPrimary by type.
  - `PhotoObj = PhotoObjAll WHERE mode IN (1, 2)`.
  - `SpecObj = SpecObjAll WHERE sciencePrimary = 1`.
- **Documented key:** the PhotoPrimary view's documentation says "Each physical object on the sky has only one primary object associated with it", that is `UNIQUE (thingID) WHERE mode = 1`.
  - In a 1°×1° sample (ra 180–181, dec 0–1), 27,438 primary rows have 27,438 distinct thingIDs, while all 84,268 rows have only 33,443.
- **Assumed key that fails:** users join `PhotoObj LEFT JOIN SpecObj ON s.bestObjID = p.objID` (376 statements), which treats bestObjID as unique among science-primary spectra.
  - On the full DR18 it is not: 69 bestObjIDs (other than 0) have two science-primary spectra, 138 rows in all.
  - It cannot be declared. A planner that trusted the documentation's intent here would be wrong.
- **No filtered indexes:** SkyServer (SQL Server) declares none; it has 189 unique indexes, all primary keys.

## Scripts
1. `sdss_schema.py METADATA_DIR DSN` builds database `sdss` on port 5444, with no data.
   - 214 base tables with types, NOT NULL and primary keys.
   - 38 of the 60 views; 21 bit-mask helper views and TableDesc are skipped.
   - Functions in schema `dbo` are stand-ins with the declared signatures: table functions return no rows, scalar ones NULL. They are for planning only.
   - DDL in `sdss_schema.sql`, log in `log_sdss_schema.txt`. The key `UNIQUE (thingid) WHERE mode = 1` is added by hand.
2. `sdss_workload.py DSN OUT` prepares queries as SEDE does (sqlglot T-SQL → PostgreSQL; quoted names lower-cased; hex masks to integers) and plans each with the prover off, on, and on with `enable_conditional_unique_costing`.

## Results (`sdss_workload_empty.json`; without the thingID key: `sdss_workload_empty_nokey.json`)

| | Queries |
|---|---|
| distinct statements | 23,135 |
| not one read-only SELECT, or untranslatable | 2,264 |
| duplicates after preparation | 755 |
| do not plan (T-SQL functions such as `str`, `newid`; double-quoted strings) | 2,378 |
| **plan** | **17,738** |
| read science-primary spectra (`sciencePrimary = 1` in the plan) | 10,444 |
| read primary photometry (`mode = 1`) | 757 |
| mention thingID and read primary photometry | 0 |
| have DISTINCT, GROUP BY or LEFT JOIN | 1,158 |
| plan changed (default, and with the costing hint) | 26: 12 GROUP BY shortened, 11 DISTINCT removed, 3 both |
| ... that need the thingID key | 0 (the same 26 change without it) |

- All 26 changes come from primary keys carried through joins. For example, `SELECT DISTINCT spec.programname FROM Star s JOIN SpecObj spec ON spec.bestobjid = s.objid WHERE spec.specobjid = …` loses its DISTINCT, because the specobjid constant fixes the spectrum and objid fixes the photometric row.
- Plans were made on the empty schema. With the key present, the partial index also becomes an access path, which changes 7 stock plans too. That is why "needs the key" compares whether a plan changes, not the plan text.
- Not timed: the changed queries are 26 of 17,738, and loading DR18 data is out of scope.
