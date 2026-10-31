# Filtered uniqueness and left joins in public dbt projects (2026-10-28)

**Why these projects.** The user suggested GitLab's analytics repository, but `gitlab-data/analytics` is no longer public: the GitLab API returns 404 and a clone asks for credentials. Two large public dbt projects were analysed instead, read only, with nothing in them executed:

| Project | Commit | Models | Parsed | Dialect |
|---|---|---|---|---|
| Cal-ITP `data-infra/warehouse` (California transit data warehouse) | 6b49eee, 2026-10-26 | 626 | 606 | BigQuery |
| Tuva `tuva-core` (healthcare claims) | 9ab0d1c, 2026-10-23 | 337 | 256 | Snowflake |

## How it works (`dbt_scopes.py`)

1. **Uniqueness from YAML.** The analysts' uniqueness tests are read from the YAML: `unique` and `dbt_utils.unique_combination_of_columns`, each with its `where:` scope. A test with a scope asserts C : U(K).
2. **SQL from models.** Models are parsed with sqlglot after crude Jinja stripping. Macros that cannot be stripped make a model unparsable; those models are counted and skipped.
3. **Left joins.** Every LEFT JOIN is followed through simple CTEs to the model it reads, collecting its scope (the CTE WHERE conjuncts and the right-only ON conjuncts) and its key (right columns equated to the left). Each join is classified:
   - **unconditional:** a test without a scope covers the key;
   - **conditional:** a scoped test covers the key and its scope occurs among the join's scope conjuncts, by textual match;
   - **current:** the scope selects current or undeleted rows;
   - **removable shape:** no column of the right side is used outside the ON clause.

## Results

| | Cal-ITP | Tuva |
|---|---|---|
| Uniqueness tests | 314 (on 245 models) | 55 (on 50 models) |
| … with a `where:` scope | **38** | 0 |
| … of these, test-cost filters (sampling, recent time windows) | 11 | — |
| … of these, semantic | **27** | — |
| LEFT JOINs (parsed models) | 334 | 331 |
| … right side unconditionally unique by a test | 45 | 4 |
| … right side unique only by a scoped test | 0 | 0 |
| … to a current-version scope (`_is_current`, …) | 12 | 0 |
| … removable shape (right side unused) | **9** | **5** |
| … removable shape and unique by any test | 0 | 0 |

**Reading**
- **Scoped tests state documented exceptions.**
  - In Cal-ITP, 24 of the 27 semantic scopes say that a key holds except on one quarantined feed (`feed_key != '…'`) or on rows flagged as duplicates (`NOT warning_duplicate_gtfs_key`).
  - The others: `reports_order IS NOT NULL`, and twice `NOT contains_warning_duplicate_trip_primary_key`.
  - These are `<>` and boolean atoms, inside the polynomial fragment.
  - Queries that join these models do not repeat the exclusion, so a planner could use the scoped keys only if a query did.
- **Transformation code fetches columns.** Only 14 of 665 left joins are removable in shape, and none of them is on a key a test declares. All 12 joins to current-version scopes use the joined columns.
- **Where join removal can pay off.** dbt materialises models as tables, so the planner sees these joins once, at build time. Join removal pays off where consumers query wide views and select a few columns: BI semantic layers and views over history. That is what `../pg_patch/tpcds_views.py` measures.

The data is in `dbt_scopes_calitp.json` and `dbt_scopes_tuva.json`.
