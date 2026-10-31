# Query optimisation with discovered conditional keys (PostgreSQL 18.6)

## Cases

| case | table | conditional key | scope predicate |
|---|---|---|---|
| SP | SeriesPost | candidate(year, tmIDLoser) | `"lgIDWinner" = 8925760856993695661` |
| GO | Goalies | candidate(playerID, year, tmID) | `"lgID" = 8925760856993695661` |
| CO | Coaches | candidate(coachID, year) | `"postg" IS NOT NULL` |
| GO2 | Goalies | candidate(playerID, year) | `"PostGP" IS NOT NULL` |
| HOF | HOF | candidate(name) | `"category" = 8632613616513808566` |
| SO | soldiers | candidate(number) | `"onboard_at_arrival" IS NOT NULL` |
| SE | seafarers | candidate(number) | `"onboard_at_arrival" IS NOT NULL` |
| VO1 | voyages | certain(number, arrival_date) | `"type_of_boat" IS NULL` |
| VO2 | voyages | candidate(number, departure_date) | `"type_of_boat" IS NULL` |
| VO3 | voyages | domain(boatname, departure_date) | `"master" IS NOT NULL` |
| IN | invoices | candidate(number, invoice) | `"chamber" = -5822201839289945793` |
| TR1 | voyages | possible(master, departure_date) | `"yard" IS NOT NULL` |
| TR2 | voyages | possible(master, departure_date) | `"cape_arrival" IS NOT NULL` |
| NV1 | voters | certain(last_name, first_name, middle_name, birth_age, res_street_address) | `"status_cd" = 'A' AND "drivers_lic" = 'Y'` |
| NV2 | voters | candidate(last_name, first_name, birth_age, res_street_address) | `"status_cd" = 'I' AND "drivers_lic" = 'Y'` |
| NV3 | voters | domain(first_name, middle_name, birth_age, birth_state, res_street_address) | `"status_cd" = 'A' AND "drivers_lic" = 'Y'` |
| NVT | voters | possible(first_name, middle_name, birth_age, res_street_address) | `"status_cd" = 'A' AND "drivers_lic" = 'Y'` |
| UP1 | proteins | certain(cross_reference_geneid, sequence_checksum) | `"cross_reference_oma" IS NOT NULL` |
| UP2 | proteins | certain(sequence_checksum, feature_chain) | `"feature_modified_residue" IS NULL` |

## Correctness

A rewrite is *licensed* when the class of the conditional key justifies it (DISTINCT and GROUP BY need a domain key, joins a possible key). *Correct* compares the result multisets of original and rewritten query; *without P* applies the same rewrite to the query without the scope predicate, where the key does not hold.

| case | class | template | licensed | correct | correct without P |
|---|---|---|---|---|---|
| SP | cand | DISTINCT | yes | yes | no |
| SP | cand | GROUPBY | yes | yes | no |
| SP | cand | LEFTJOIN | yes | yes | no |
| SP | cand | SEMIJOIN | yes | yes | no |
| GO | cand | DISTINCT | yes | yes | no |
| GO | cand | GROUPBY | yes | yes | no |
| GO | cand | LEFTJOIN | yes | yes | no |
| GO | cand | SEMIJOIN | yes | yes | no |
| CO | cand | DISTINCT | yes | yes | no |
| CO | cand | GROUPBY | yes | yes | no |
| CO | cand | LEFTJOIN | yes | yes | no |
| CO | cand | SEMIJOIN | yes | yes | no |
| GO2 | cand | DISTINCT | yes | yes | no |
| GO2 | cand | GROUPBY | yes | yes | no |
| GO2 | cand | LEFTJOIN | yes | yes | no |
| GO2 | cand | SEMIJOIN | yes | yes | no |
| HOF | cand | DISTINCT | yes | yes | no |
| HOF | cand | GROUPBY | yes | yes | no |
| HOF | cand | LEFTJOIN | yes | yes | no |
| HOF | cand | SEMIJOIN | yes | yes | no |
| SO | cand | DISTINCT | yes | yes | no |
| SO | cand | GROUPBY | yes | yes | no |
| SO | cand | LEFTJOIN | yes | yes | no |
| SO | cand | SEMIJOIN | yes | yes | no |
| SE | cand | DISTINCT | yes | yes | no |
| SE | cand | GROUPBY | yes | yes | no |
| SE | cand | LEFTJOIN | yes | yes | no |
| SE | cand | SEMIJOIN | yes | yes | no |
| VO1 | cert | DISTINCT | yes | yes | no |
| VO1 | cert | GROUPBY | yes | yes | no |
| VO1 | cert | LEFTJOIN | yes | yes | no |
| VO1 | cert | SEMIJOIN | yes | yes | no |
| VO2 | cand | DISTINCT | yes | yes | no |
| VO2 | cand | GROUPBY | yes | yes | no |
| VO2 | cand | LEFTJOIN | yes | yes | no |
| VO2 | cand | SEMIJOIN | yes | yes | no |
| VO3 | dom | DISTINCT | yes | yes | no |
| VO3 | dom | GROUPBY | yes | yes | no |
| VO3 | dom | LEFTJOIN | yes | yes | no |
| VO3 | dom | SEMIJOIN | yes | yes | no |
| IN | cand | DISTINCT | yes | yes | no |
| IN | cand | GROUPBY | yes | yes | no |
| IN | cand | LEFTJOIN | yes | yes | no |
| IN | cand | SEMIJOIN | yes | yes | no |
| TR1 | pos | DISTINCT | no | **no** | no |
| TR1 | pos | GROUPBY | no | **no** | no |
| TR1 | pos | LEFTJOIN | yes | yes | no |
| TR1 | pos | SEMIJOIN | yes | yes | no |
| TR2 | pos | DISTINCT | no | **no** | no |
| TR2 | pos | GROUPBY | no | **no** | no |
| TR2 | pos | LEFTJOIN | yes | yes | no |
| TR2 | pos | SEMIJOIN | yes | yes | no |
| NV1 | cert | DISTINCT | yes | yes | no |
| NV1 | cert | GROUPBY | yes | yes | no |
| NV1 | cert | LEFTJOIN | yes | yes | no |
| NV1 | cert | SEMIJOIN | yes | yes | no |
| NV2 | cand | DISTINCT | yes | yes | no |
| NV2 | cand | GROUPBY | yes | yes | no |
| NV2 | cand | LEFTJOIN | yes | yes | no |
| NV2 | cand | SEMIJOIN | yes | yes | no |
| NV3 | dom | DISTINCT | yes | yes | no |
| NV3 | dom | GROUPBY | yes | yes | no |
| NV3 | dom | LEFTJOIN | yes | yes | no |
| NV3 | dom | SEMIJOIN | yes | yes | no |
| NVT | pos | DISTINCT | no | **no** | no |
| NVT | pos | GROUPBY | no | **no** | no |
| NVT | pos | LEFTJOIN | yes | yes | no |
| NVT | pos | SEMIJOIN | yes | yes | no |
| UP1 | cert | DISTINCT | yes | yes | no |
| UP1 | cert | GROUPBY | yes | yes | no |
| UP1 | cert | LEFTJOIN | yes | yes | no |
| UP1 | cert | SEMIJOIN | yes | yes | no |
| UP2 | cert | DISTINCT | yes | yes | no |
| UP2 | cert | GROUPBY | yes | yes | no |
| UP2 | cert | LEFTJOIN | yes | yes | yes |
| UP2 | cert | SEMIJOIN | yes | yes | yes |

Licensed rewrites correct: 70/70. Unlicensed (GROUP BY trap) rewrites correct: 0/6. Rewrites still correct without the scope predicate: 2/70.

## Execution time, scale x1 (median ms; original -> rewritten)

| case | template | none | idx | uq (conditional key enforced) | speed-up (uq) | PG avoids it itself (none/idx/uq) |
|---|---|---|---|---|---|---|
| SP | DISTINCT | 0.13 -> 0.05 | 0.13 -> 0.05 | 0.13 -> 0.05 | 2.7x | no/no/no |
| SP | GROUPBY | 0.14 -> 0.05 | 0.14 -> 0.05 | 0.13 -> 0.05 | 2.9x | no/no/no |
| SP | LEFTJOIN | 0.16 -> 0.04 | 0.53 -> 0.04 | 0.50 -> 0.05 | 10.8x | no/no/no |
| SP | SEMIJOIN | 0.24 -> 0.17 | 0.24 -> 0.54 | 0.24 -> 0.52 | 0.5x | yes/yes/yes |
| GO | DISTINCT | 0.69 -> 0.22 | 0.71 -> 0.23 | 0.68 -> 0.23 | 3.0x | no/no/no |
| GO | GROUPBY | 0.75 -> 0.23 | 0.71 -> 0.23 | 0.74 -> 0.23 | 3.2x | no/no/no |
| GO | LEFTJOIN | 0.95 -> 0.26 | 3.08 -> 0.23 | 3.27 -> 0.22 | 14.8x | no/no/no |
| GO | SEMIJOIN | 1.30 -> 0.86 | 1.51 -> 3.06 | 1.31 -> 2.94 | 0.4x | yes/yes/yes |
| CO | DISTINCT | 0.20 -> 0.09 | 0.20 -> 0.09 | 0.18 -> 0.08 | 2.2x | no/no/no |
| CO | GROUPBY | 0.19 -> 0.10 | 0.21 -> 0.09 | 0.21 -> 0.09 | 2.3x | no/no/no |
| CO | LEFTJOIN | 0.32 -> 0.10 | 0.32 -> 0.09 | 0.32 -> 0.09 | 3.4x | no/no/no |
| CO | SEMIJOIN | 0.37 -> 0.28 | 0.39 -> 0.30 | 0.37 -> 0.27 | 1.4x | yes/yes/yes |
| GO2 | DISTINCT | 0.34 -> 0.19 | 0.34 -> 0.19 | 0.37 -> 0.22 | 1.7x | no/no/no |
| GO2 | GROUPBY | 0.37 -> 0.20 | 0.37 -> 0.21 | 0.37 -> 0.20 | 1.8x | no/no/no |
| GO2 | LEFTJOIN | 0.79 -> 0.22 | 0.73 -> 0.22 | 0.74 -> 0.21 | 3.4x | no/no/no |
| GO2 | SEMIJOIN | 0.72 -> 0.59 | 0.77 -> 0.66 | 0.80 -> 0.64 | 1.2x | yes/yes/yes |
| HOF | DISTINCT | 0.03 -> 0.01 | 0.02 -> 0.01 | 0.02 -> 0.01 | 1.8x | no/no/no |
| HOF | GROUPBY | 0.02 -> 0.01 | 0.02 -> 0.01 | 0.02 -> 0.01 | 1.7x | no/no/no |
| HOF | LEFTJOIN | 0.05 -> 0.02 | 0.05 -> 0.02 | 0.05 -> 0.02 | 2.4x | no/no/no |
| HOF | SEMIJOIN | 0.04 -> 0.04 | 0.04 -> 0.04 | 0.04 -> 0.04 | 1.0x | no/no/no |
| SO | DISTINCT | 0.44 -> 0.19 | 0.44 -> 0.19 | 0.44 -> 0.19 | 2.3x | no/no/no |
| SO | GROUPBY | 0.46 -> 0.20 | 0.46 -> 0.20 | 0.46 -> 0.20 | 2.3x | no/no/no |
| SO | LEFTJOIN | 0.67 -> 0.21 | 0.67 -> 0.21 | 0.67 -> 0.21 | 3.1x | no/no/no |
| SO | SEMIJOIN | 0.61 -> 0.61 | 0.61 -> 0.62 | 0.62 -> 0.63 | 1.0x | no/no/no |
| SE | DISTINCT | 0.51 -> 0.22 | 0.51 -> 0.22 | 0.50 -> 0.22 | 2.2x | no/no/no |
| SE | GROUPBY | 0.51 -> 0.22 | 0.52 -> 0.23 | 0.51 -> 0.23 | 2.3x | no/no/no |
| SE | LEFTJOIN | 0.76 -> 0.24 | 0.73 -> 0.23 | 0.73 -> 0.23 | 3.1x | no/no/no |
| SE | SEMIJOIN | 0.67 -> 0.71 | 0.70 -> 0.72 | 0.69 -> 0.70 | 1.0x | no/no/no |
| VO1 | DISTINCT | 1.08 -> 0.51 | 1.11 -> 0.52 | 1.10 -> 0.52 | 2.1x | no/no/no |
| VO1 | GROUPBY | 1.10 -> 0.50 | 1.09 -> 0.50 | 1.08 -> 0.49 | 2.2x | no/no/no |
| VO1 | LEFTJOIN | 1.60 -> 0.50 | 1.59 -> 0.50 | 1.60 -> 0.51 | 3.2x | no/no/no |
| VO1 | SEMIJOIN | 1.61 -> 1.66 | 1.58 -> 1.54 | 1.51 -> 1.50 | 1.0x | no/no/no |
| VO2 | DISTINCT | 1.03 -> 0.50 | 1.09 -> 0.48 | 0.98 -> 0.44 | 2.2x | no/no/no |
| VO2 | GROUPBY | 1.04 -> 0.44 | 1.12 -> 0.52 | 1.06 -> 0.47 | 2.3x | no/no/no |
| VO2 | LEFTJOIN | 1.64 -> 0.47 | 1.59 -> 0.48 | 1.59 -> 0.47 | 3.4x | no/no/no |
| VO2 | SEMIJOIN | 1.78 -> 1.60 | 1.54 -> 1.44 | 1.56 -> 1.53 | 1.0x | no/no/no |
| VO3 | DISTINCT | 1.27 -> 0.50 | 1.27 -> 0.51 | 1.32 -> 0.54 | 2.5x | no/no/no |
| VO3 | GROUPBY | 1.45 -> 0.56 | 1.29 -> 0.51 | 1.27 -> 0.51 | 2.5x | no/no/no |
| VO3 | LEFTJOIN | 1.85 -> 0.45 | 1.84 -> 0.47 | 1.74 -> 0.46 | 3.8x | no/no/no |
| VO3 | SEMIJOIN | 2.58 -> 1.78 | 2.54 -> 1.65 | 2.38 -> 1.76 | 1.3x | yes/yes/yes |
| IN | DISTINCT | 0.32 -> 0.16 | 0.31 -> 0.16 | 0.32 -> 0.15 | 2.1x | no/no/no |
| IN | GROUPBY | 0.33 -> 0.16 | 0.36 -> 0.18 | 0.36 -> 0.17 | 2.1x | no/no/no |
| IN | LEFTJOIN | 0.73 -> 0.23 | 0.64 -> 0.19 | 0.64 -> 0.20 | 3.2x | no/no/no |
| IN | SEMIJOIN | 0.50 -> 0.54 | 0.51 -> 0.54 | 0.54 -> 0.59 | 0.9x | no/no/no |
| TR1 | LEFTJOIN | 1.84 -> 0.50 | 1.85 -> 0.48 | 1.89 -> 0.48 | 4.0x | no/no/no |
| TR1 | SEMIJOIN | 2.47 -> 1.61 | 2.44 -> 1.75 | 2.36 -> 1.59 | 1.5x | yes/yes/yes |
| TR2 | LEFTJOIN | 1.72 -> 0.46 | 1.75 -> 0.47 | 1.88 -> 0.48 | 3.9x | no/no/no |
| TR2 | SEMIJOIN | 2.60 -> 1.85 | 2.25 -> 1.81 | 2.46 -> 1.93 | 1.3x | yes/yes/yes |

Median speed-up of the licensed rewrite with the key enforced (uq), by template: DISTINCT 2.2x, GROUPBY 2.3x, LEFTJOIN 3.4x, SEMIJOIN 1.0x.

## Execution time, scale x50 (median ms; original -> rewritten)

| case | template | none | idx | uq (conditional key enforced) | speed-up (uq) | PG avoids it itself (none/idx/uq) |
|---|---|---|---|---|---|---|
| SP | DISTINCT | 7.36 -> 2.39 | 7.37 -> 2.38 | 7.01 -> 2.31 | 3.0x | no/no/no |
| SP | GROUPBY | 8.69 -> 2.51 | 7.96 -> 2.44 | 7.85 -> 2.53 | 3.1x | no/no/no |
| SP | LEFTJOIN | 9.39 -> 2.13 | 32.23 -> 2.25 | 31.93 -> 2.37 | 13.5x | no/no/no |
| SP | SEMIJOIN | 16.13 -> 9.04 | 14.00 -> 31.80 | 15.34 -> 32.38 | 0.5x | yes/yes/yes |
| GO | DISTINCT | 75.26 -> 12.32 | 67.76 -> 12.03 | 69.31 -> 12.06 | 5.7x | no/no/no |
| GO | GROUPBY | 72.35 -> 11.60 | 73.71 -> 11.77 | 71.31 -> 12.54 | 5.7x | no/no/no |
| GO | LEFTJOIN | 132.28 -> 12.00 | 226.74 -> 11.79 | 215.38 -> 12.29 | 17.5x | no/no/no |
| GO | SEMIJOIN | 149.01 -> 127.00 | 147.86 -> 219.11 | 145.86 -> 212.20 | 0.7x | yes/yes/yes |
| CO | DISTINCT | 10.17 -> 4.78 | 9.68 -> 4.38 | 9.91 -> 4.77 | 2.1x | no/no/no |
| CO | GROUPBY | 11.29 -> 4.45 | 11.24 -> 4.73 | 10.05 -> 4.20 | 2.4x | no/no/no |
| CO | LEFTJOIN | 21.11 -> 4.73 | 21.92 -> 4.89 | 61.67 -> 4.70 | 13.1x | no/no/no |
| CO | SEMIJOIN | 23.91 -> 18.20 | 24.55 -> 17.05 | 23.54 -> 60.18 | 0.4x | yes/yes/yes |
| GO2 | DISTINCT | 19.80 -> 10.79 | 21.00 -> 10.04 | 7.45 -> 3.51 | 2.1x | no/no/no |
| GO2 | GROUPBY | 20.43 -> 10.05 | 22.24 -> 10.04 | 8.87 -> 4.22 | 2.1x | no/no/no |
| GO2 | LEFTJOIN | 60.41 -> 11.11 | 190.13 -> 10.84 | 153.32 -> 10.74 | 14.3x | no/no/no |
| GO2 | SEMIJOIN | 48.76 -> 49.58 | 46.86 -> 180.67 | 43.88 -> 145.42 | 0.3x | yes/yes/yes |
| HOF | DISTINCT | 0.95 -> 0.60 | 0.97 -> 0.57 | 0.50 -> 0.25 | 2.0x | no/no/no |
| HOF | GROUPBY | 1.03 -> 0.55 | 1.06 -> 0.59 | 0.57 -> 0.26 | 2.2x | no/no/no |
| HOF | LEFTJOIN | 2.56 -> 0.97 | 2.48 -> 0.94 | 2.10 -> 0.94 | 2.2x | no/no/no |
| HOF | SEMIJOIN | 1.98 -> 1.94 | 1.81 -> 1.83 | 1.47 -> 1.44 | 1.0x | no/no/no |
| SO | DISTINCT | 28.75 -> 10.01 | 30.53 -> 10.23 | 13.38 -> 7.12 | 1.9x | no/no/no |
| SO | GROUPBY | 38.86 -> 10.32 | 38.56 -> 10.09 | 16.38 -> 7.71 | 2.1x | no/no/no |
| SO | LEFTJOIN | 48.91 -> 10.73 | 43.13 -> 10.38 | 45.86 -> 11.11 | 4.1x | no/no/no |
| SO | SEMIJOIN | 38.77 -> 42.78 | 36.78 -> 39.41 | 37.56 -> 42.83 | 0.9x | no/no/no |
| SE | DISTINCT | 29.69 -> 10.78 | 29.77 -> 11.34 | 14.27 -> 7.26 | 2.0x | no/no/no |
| SE | GROUPBY | 41.18 -> 10.62 | 42.39 -> 11.25 | 17.74 -> 7.94 | 2.2x | no/no/no |
| SE | LEFTJOIN | 53.51 -> 11.52 | 47.71 -> 11.50 | 46.17 -> 11.51 | 4.0x | no/no/no |
| SE | SEMIJOIN | 43.30 -> 47.13 | 40.99 -> 45.31 | 43.74 -> 40.24 | 1.1x | no/no/no |
| VO1 | DISTINCT | 124.30 -> 36.75 | 98.31 -> 24.63 | 99.81 -> 25.40 | 3.9x | no/no/no |
| VO1 | GROUPBY | 107.51 -> 25.77 | 103.93 -> 25.87 | 106.69 -> 25.83 | 4.1x | no/no/no |
| VO1 | LEFTJOIN | 136.77 -> 25.43 | 139.36 -> 25.69 | 129.57 -> 25.75 | 5.0x | no/no/no |
| VO1 | SEMIJOIN | 133.22 -> 132.51 | 132.41 -> 136.72 | 126.63 -> 119.35 | 1.1x | no/no/no |
| VO2 | DISTINCT | 94.66 -> 22.15 | 94.60 -> 22.63 | 27.35 -> 13.43 | 2.0x | no/no/no |
| VO2 | GROUPBY | 106.34 -> 22.58 | 107.81 -> 22.65 | 31.79 -> 14.85 | 2.1x | no/no/no |
| VO2 | LEFTJOIN | 134.14 -> 22.57 | 134.61 -> 23.43 | 126.44 -> 24.48 | 5.2x | no/no/no |
| VO2 | SEMIJOIN | 132.56 -> 137.12 | 129.79 -> 130.84 | 125.80 -> 122.30 | 1.0x | no/no/no |
| VO3 | DISTINCT | 116.68 -> 24.91 | 115.75 -> 24.34 | 31.58 -> 16.30 | 1.9x | no/no/no |
| VO3 | GROUPBY | 129.80 -> 24.75 | 131.25 -> 25.68 | 39.18 -> 18.55 | 2.1x | no/no/no |
| VO3 | LEFTJOIN | 144.89 -> 23.15 | 226.06 -> 24.65 | 152.64 -> 24.50 | 6.2x | no/no/no |
| VO3 | SEMIJOIN | 154.81 -> 150.40 | 154.79 -> 147.98 | 153.04 -> 138.52 | 1.1x | no/no/no |
| IN | DISTINCT | 17.18 -> 7.47 | 18.13 -> 7.34 | 7.14 -> 3.58 | 2.0x | no/no/no |
| IN | GROUPBY | 17.77 -> 7.29 | 17.49 -> 7.26 | 9.02 -> 4.10 | 2.2x | no/no/no |
| IN | LEFTJOIN | 35.59 -> 8.92 | 49.80 -> 8.99 | 31.58 -> 8.75 | 3.6x | no/no/no |
| IN | SEMIJOIN | 46.20 -> 40.01 | 40.80 -> 39.45 | 37.12 -> 37.04 | 1.0x | yes/yes/yes |
| TR1 | LEFTJOIN | 147.37 -> 25.40 | 146.41 -> 24.38 | 142.78 -> 24.97 | 5.7x | no/no/no |
| TR1 | SEMIJOIN | 136.96 -> 141.40 | 138.85 -> 139.07 | 139.19 -> 134.20 | 1.0x | no/no/no |
| TR2 | LEFTJOIN | 144.75 -> 25.18 | 144.08 -> 24.33 | 139.21 -> 24.03 | 5.8x | no/no/no |
| TR2 | SEMIJOIN | 139.00 -> 139.46 | 139.43 -> 139.12 | 130.78 -> 128.54 | 1.0x | no/no/no |

Median speed-up of the licensed rewrite with the key enforced (uq), by template: DISTINCT 2.0x, GROUPBY 2.2x, LEFTJOIN 5.7x, SEMIJOIN 1.0x.

## Execution time, real scale (NCVoter 1,023,993 rows, UniProt 24,173 rows) (median ms; original -> rewritten)

| case | template | none | idx | uq (conditional key enforced) | speed-up (uq) | PG avoids it itself (none/idx/uq) |
|---|---|---|---|---|---|---|
| NV1 | DISTINCT | 215.11 -> 60.28 | 213.42 -> 60.06 | 214.35 -> 59.70 | 3.6x | no/no/no |
| NV1 | GROUPBY | 219.03 -> 60.70 | 223.76 -> 62.29 | 222.48 -> 61.05 | 3.6x | no/no/no |
| NV1 | LEFTJOIN | 848.65 -> 55.11 | 498.18 -> 52.95 | 1284.05 -> 54.09 | 23.7x | no/no/no |
| NV1 | SEMIJOIN | 675.81 -> 864.08 | 663.89 -> 515.10 | 646.27 -> 1335.87 | 0.5x | yes/yes/yes |
| NV2 | DISTINCT | 77.19 -> 45.27 | 80.54 -> 44.78 | 43.99 -> 15.73 | 2.8x | no/no/no |
| NV2 | GROUPBY | 82.59 -> 46.47 | 82.17 -> 45.57 | 50.24 -> 14.03 | 3.6x | no/no/no |
| NV2 | LEFTJOIN | 630.40 -> 54.76 | 269.29 -> 56.47 | 585.25 -> 54.52 | 10.7x | no/no/no |
| NV2 | SEMIJOIN | 252.46 -> 587.27 | 268.00 -> 229.82 | 216.94 -> 559.25 | 0.4x | yes/yes/yes |
| NV3 | DISTINCT | 224.28 -> 61.35 | 220.61 -> 59.99 | 221.04 -> 62.30 | 3.5x | no/no/no |
| NV3 | GROUPBY | 231.03 -> 63.14 | 227.77 -> 61.50 | 229.47 -> 64.52 | 3.6x | no/no/no |
| NV3 | LEFTJOIN | 1184.95 -> 54.87 | 803.01 -> 52.46 | 1645.73 -> 52.66 | 31.3x | no/no/no |
| NV3 | SEMIJOIN | 569.56 -> 1151.53 | 572.99 -> 776.86 | 598.72 -> 1646.00 | 0.4x | yes/yes/yes |
| NVT | LEFTJOIN | 1115.46 -> 54.23 | 798.31 -> 52.45 | 1791.92 -> 55.55 | 32.3x | no/no/no |
| NVT | SEMIJOIN | 614.29 -> 1114.26 | 575.88 -> 807.63 | 552.39 -> 1789.36 | 0.3x | yes/yes/yes |
| UP1 | DISTINCT | 2.91 -> 1.05 | 2.79 -> 1.06 | 2.90 -> 1.05 | 2.8x | no/no/no |
| UP1 | GROUPBY | 2.94 -> 1.06 | 2.94 -> 1.06 | 2.96 -> 1.07 | 2.8x | no/no/no |
| UP1 | LEFTJOIN | 4.47 -> 1.06 | 4.85 -> 1.09 | 4.18 -> 1.08 | 3.9x | no/no/no |
| UP1 | SEMIJOIN | 4.12 -> 4.15 | 4.13 -> 4.20 | 3.73 -> 3.73 | 1.0x | no/no/no |
| UP2 | DISTINCT | 3.78 -> 1.16 | 3.80 -> 1.16 | 3.78 -> 1.16 | 3.3x | no/no/no |
| UP2 | GROUPBY | 3.98 -> 1.18 | 3.97 -> 1.18 | 3.97 -> 1.18 | 3.4x | no/no/no |
| UP2 | LEFTJOIN | 5.80 -> 1.09 | 6.06 -> 1.12 | 5.79 -> 1.10 | 5.3x | no/no/no |
| UP2 | SEMIJOIN | 5.83 -> 5.73 | 5.90 -> 5.67 | 5.80 -> 5.67 | 1.0x | no/no/no |

Median speed-up of the licensed rewrite with the key enforced (uq), by template: DISTINCT 3.3x, GROUPBY 3.6x, LEFTJOIN 17.2x, SEMIJOIN 0.4x.

