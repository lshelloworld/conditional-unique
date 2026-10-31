# E7: cleaning with discovered conditional keys (results_e7_anywhere)

## Precision over the keys on which CK, UK and CFD all flag something (used in the paper); recall over all keys

| error type | keys (common) | CK P/R | UK P/R | CFD P/R |
|---|---|---|---|---|
| dup | 22 (22) | 1.00/0.68 | 0.81/0.98 | 0.85/0.66 |
| partial | 15 (11) | 0.99/0.47 | 0.71/0.67 | 0.58/0.04 |
| missing | 15 (6) | 0.57/0.09 | 0.32/0.24 | 0.12/0.03 |
| mixed | 22 (22) | 1.00/0.47 | 0.73/0.76 | 0.80/0.37 |

## Macro-average over keys (each key counts once): discovered class, unconditional, CFD

| error type | keys | CK (discovered class) P/R | UK (same class) P/R | CFD P/R |
|---|---|---|---|---|
| dup | 22 | 1.00/0.68 | 0.81/0.98 | 0.85/0.66 |
| partial | 15 | 0.99/0.47 | 0.53/0.67 | 0.53/0.04 |
| missing | 15 | 0.65/0.09 | 0.18/0.24 | 0.11/0.03 |
| mixed | 22 | 1.00/0.47 | 0.73/0.76 | 0.80/0.37 |

## Macro-average over keys: class of the conditional key (same condition)

| error type | CK-pos P/R | CK-dom P/R | CK-part P/R | CK-cert P/R | CK-cand P/R |
|---|---|---|---|---|---|
| dup | 1.00/0.67 | 0.94/0.69 | 0.93/0.69 | 0.92/0.69 | 0.74/0.69 |
| partial | --/0.00 | 0.85/0.03 | 0.81/0.73 | 0.80/0.73 | 0.54/0.73 |
| missing | --/0.00 | 0.33/0.02 | 0.32/0.18 | 0.36/0.23 | 0.53/0.73 |
| mixed | 1.00/0.34 | 0.92/0.36 | 0.88/0.55 | 0.86/0.57 | 0.71/0.68 |

# Pooled counts (micro-average; dominated by the large NCVoter error sets)

## Discovered class: conditional vs. unconditional vs. CFD

| error type | keys | CK (discovered class) P/R | UK (same class) P/R | CFD P/R |
|---|---|---|---|---|
| dup | 22 | 1.00/0.58 | 0.85/0.98 | 0.95/0.55 |
| partial | 15 | 1.00/0.22 | 0.60/0.40 | 0.13/0.01 |
| missing | 15 | 0.82/0.01 | 0.16/0.08 | 0.03/0.00 |
| mixed | 22 | 1.00/0.27 | 0.65/0.49 | 0.88/0.19 |

## Class of the conditional key (same condition), pooled over all keys

| error type | CK-pos P/R | CK-dom P/R | CK-part P/R | CK-cert P/R | CK-cand P/R |
|---|---|---|---|---|---|
| dup | 1.00/0.53 | 0.98/0.58 | 0.96/0.58 | 0.96/0.58 | 0.21/0.58 |
| partial | --/0.00 | 0.16/0.00 | 0.76/0.58 | 0.76/0.58 | 0.12/0.58 |
| missing | --/0.00 | 0.04/0.00 | 0.02/0.01 | 0.03/0.01 | 0.12/0.59 |
| mixed | 1.00/0.18 | 0.93/0.20 | 0.69/0.39 | 0.69/0.39 | 0.15/0.59 |

## Unconditional key of each class, pooled

| error type | UK-pos P/R | UK-dom P/R | UK-part P/R | UK-cert P/R | UK-cand P/R |
|---|---|---|---|---|---|
| dup | 0.86/0.90 | 0.85/1.00 | 0.80/1.00 | 0.80/1.00 | 0.18/1.00 |
| partial | 0.01/0.00 | 0.03/0.01 | 0.67/1.00 | 0.67/1.00 | 0.11/1.00 |
| missing | 0.00/0.00 | 0.00/0.00 | 0.02/0.02 | 0.03/0.03 | 0.10/1.00 |
| mixed | 0.67/0.30 | 0.66/0.34 | 0.57/0.68 | 0.57/0.68 | 0.13/1.00 |

## Per key (mixed errors)

| key | class | CK P/R | UK P/R | CFD P/R |
|---|---|---|---|---|
| SP SeriesPost(year, tmIDLoser) | cand | 1.00/0.93 | 0.62/1.00 | 1.00/0.87 |
| GO Goalies(playerID, year, tmID) | cand | 1.00/0.90 | 0.96/1.00 | 1.00/0.50 |
| CO Coaches(coachID, year) | cand | 1.00/0.50 | 0.30/1.00 | 0.28/0.89 |
| GO2 Goalies(playerID, year) | cand | 1.00/0.37 | 0.04/1.00 | 0.03/0.73 |
| HOF HOF(name) | cand | 1.00/0.08 | 0.80/1.00 | 1.00/0.08 |
| MA1 Master(playerID, firstName, hrefID) | part | 1.00/0.64 | 0.03/1.00 | 0.55/0.19 |
| MA2 Master(firstName, lastName, hrefID) | cert | 0.93/0.65 | 0.72/0.70 | 1.00/0.17 |
| SO soldiers(number) | cand | 1.00/0.63 | 0.95/1.00 | 0.92/0.58 |
| SE seafarers(number) | cand | 1.00/0.62 | 0.95/1.00 | 0.94/0.80 |
| VO1 voyages(number, arrival_date) | cert | 1.00/0.49 | 0.96/0.66 | 0.97/0.25 |
| VO2 voyages(number, departure_date) | cand | 1.00/0.70 | 0.96/1.00 | 0.91/0.24 |
| VO3 voyages(boatname, departure_date) | dom | 1.00/0.32 | 0.98/0.38 | 0.98/0.30 |
| VO4 voyages(number, chamber) | cert | 1.00/0.62 | 0.98/0.67 | 0.98/0.27 |
| IN invoices(number, invoice) | cand | 1.00/0.39 | 0.20/1.00 | 1.00/0.14 |
| TR1 voyages(master, departure_date) | pos | 1.00/0.26 | 0.98/0.28 | 0.12/0.42 |
| TR2 voyages(master, departure_date) | pos | 1.00/0.26 | 0.98/0.29 | 0.10/0.38 |
| NV1 voters(last_name, first_name, middle_name, birth_age, res_street_address) | cert | 1.00/0.40 | 0.85/0.67 | 1.00/0.19 |
| NV2 voters(last_name, first_name, birth_age, res_street_address) | cand | 1.00/0.14 | 0.52/1.00 | 1.00/0.04 |
| NV3 voters(first_name, middle_name, birth_age, birth_state, res_street_address) | dom | 1.00/0.20 | 0.77/0.33 | 1.00/0.19 |
| NVT voters(first_name, middle_name, birth_age, res_street_address) | pos | 1.00/0.19 | 0.69/0.32 | 1.00/0.19 |
| UP1 proteins(cross_reference_geneid, sequence_checksum) | cert | 0.99/0.49 | 0.92/0.66 | 0.89/0.29 |
| UP2 proteins(sequence_checksum, feature_chain) | cert | 0.99/0.60 | 0.97/0.67 | 0.94/0.31 |
