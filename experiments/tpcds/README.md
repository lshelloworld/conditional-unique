# TPC-DS experiments

## Scripts

| Script | What it does |
|---|---|
| `load_tpcds.py` | Generates TPC-DS with DuckDB's dsdgen and loads it into PostgreSQL with the specification's keys. |
| `mine_tpcds.py` | Mines the dimension tables (per-table output in `mined/`, merged into `mined.json`). |
| `stable.py` | Re-checks the mined keys at another scale factor (`stable` in `mined.json`). |
| `audit.py`, `oracle.py` | Which query constructs keys license, and an upper bound from the data. |
| `rewrite_run.py` | Times the licensed rewrites in PostgreSQL. |
| `query_mining.py` | Mines conditions and key demands from the 99 queries. |
| `x8_refresh.py` | Stability under data maintenance (below). |

## X8: stability under data maintenance (`x8_refresh.py`, 2026-10-28)

**Setup**

DuckDB's dsdgen cannot generate refresh sets. The official kit needs a tpc.org registration and acceptance of its EULA, so the user chose to emulate the dimension maintenance of the specification on a copy of SF1. This is an emulation, not the official refresh.

- **History-keeping dimensions** (item, store, call_center, web_page, web_site): each round, 5% of the current versions get a new version. The current row is closed and a successor is inserted with the same business key.
- **Other maintained dimensions** (catalog_page, customer, customer_address, promotion, warehouse): 5% of rows are updated in place.
- **New entities:** every maintained dimension also gets 2.5% new entities.
- **New attribute values:** each attribute keeps its old value with probability 1/2. Otherwise it is drawn from the column's existing values.
- **Static dimensions** are left alone: date_dim, time_dim, household_demographics, customer_demographics, income_band, reason and ship_mode.
- **Validation:** after each of 3 rounds, all 11,988 mined keys are re-validated with `stable.holds()`. A key that breaks counts as broken from then on.

**Results**

Share of keys on maintained tables that still hold:

| Keys | Count | After round 1 | After round 3 |
|---|---|---|---|
| Conditional, stable at SF1 and SF10 | 3,126 | 88% | 79% |
| Conditional, not stable | 7,496 | 70% | 58% |
| Unconditional, stable | 846 | 61% | 45% |
| Unconditional, not stable | 483 | 52% | 26% |

- All 30 keys on the static tables hold.
- The 5 current-version business keys (`UNIQUE (i_item_id) WHERE i_rec_end_date IS NULL`, etc.) and the 9 unconditional business keys hold. The emulation maintains them by construction, so this is a sanity check, not evidence.
- **Stability at SF10 as a filter:** of the conditional keys it keeps, 79% survive three rounds, against a baseline of 64%. It catches 36% of the keys that survive.
- **Survival of the stable conditional keys after round 3, by class:**

  | Class | Survival |
  |---|---|
  | cand | 81% |
  | dom | 81% |
  | pos | 73% |
  | cert | 73% |

**Caveat**

Drawing new values column by column breaks correlations between columns that dsdgen would keep. Keys that rest on such correlations therefore break more often here than under the official refresh, so the survival rates are lower bounds.
