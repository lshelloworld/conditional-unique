# E7: cleaning with discovered conditional keys (results_e7)

## Precision over the keys on which CK, UK and CFD all flag something (used in the paper); recall over all keys

| error type | keys (common) | CK P/R | UK P/R | CFD P/R |
|---|---|---|---|---|
| dup | 22 (22) | 1.00/0.99 | 0.81/0.99 | 0.85/0.83 |
| partial | 15 (12) | 0.92/0.67 | 0.67/0.67 | 0.62/0.04 |
| missing | 15 (7) | 0.64/0.21 | 0.36/0.22 | 0.27/0.03 |
| mixed | 22 (22) | 0.99/0.74 | 0.74/0.74 | 0.80/0.47 |

## Macro-average over keys (each key counts once): discovered class, unconditional, CFD

| error type | keys | CK (discovered class) P/R | UK (same class) P/R | CFD P/R |
|---|---|---|---|---|
| dup | 22 | 1.00/0.99 | 0.81/0.99 | 0.85/0.83 |
| partial | 15 | 0.92/0.67 | 0.54/0.67 | 0.57/0.04 |
| missing | 15 | 0.64/0.21 | 0.19/0.22 | 0.18/0.03 |
| mixed | 22 | 0.99/0.74 | 0.74/0.74 | 0.80/0.47 |

## Macro-average over keys: class of the conditional key (same condition)

| error type | CK-pos P/R | CK-dom P/R | CK-part P/R | CK-cert P/R | CK-cand P/R |
|---|---|---|---|---|---|
| dup | 1.00/0.97 | 0.94/1.00 | 0.93/1.00 | 0.92/1.00 | 0.77/1.00 |
| partial | --/0.00 | 0.87/0.04 | 0.75/1.00 | 0.75/1.00 | 0.57/1.00 |
| missing | --/0.00 | 0.51/0.03 | 0.31/0.20 | 0.37/0.26 | 0.56/1.00 |
| mixed | 1.00/0.54 | 0.93/0.56 | 0.87/0.82 | 0.86/0.83 | 0.73/1.00 |

# Pooled counts (micro-average; dominated by the large NCVoter error sets)

## Discovered class: conditional vs. unconditional vs. CFD

| error type | keys | CK (discovered class) P/R | UK (same class) P/R | CFD P/R |
|---|---|---|---|---|
| dup | 22 | 1.00/0.99 | 0.85/0.99 | 0.97/0.94 |
| partial | 15 | 0.95/0.40 | 0.66/0.40 | 0.23/0.01 |
| missing | 15 | 0.97/0.07 | 0.18/0.07 | 0.03/0.00 |
| mixed | 22 | 1.00/0.49 | 0.72/0.49 | 0.92/0.32 |

## Class of the conditional key (same condition), pooled over all keys

| error type | CK-pos P/R | CK-dom P/R | CK-part P/R | CK-cert P/R | CK-cand P/R |
|---|---|---|---|---|---|
| dup | 1.00/0.91 | 0.99/1.00 | 0.98/1.00 | 0.98/1.00 | 0.31/1.00 |
| partial | --/0.00 | 0.31/0.01 | 0.82/1.00 | 0.82/1.00 | 0.20/1.00 |
| missing | --/0.00 | 0.05/0.00 | 0.03/0.01 | 0.04/0.02 | 0.18/1.00 |
| mixed | 1.00/0.30 | 0.96/0.34 | 0.78/0.67 | 0.78/0.67 | 0.24/1.00 |

## Unconditional key of each class, pooled

| error type | UK-pos P/R | UK-dom P/R | UK-part P/R | UK-cert P/R | UK-cand P/R |
|---|---|---|---|---|---|
| dup | 0.86/0.91 | 0.85/1.00 | 0.80/1.00 | 0.80/1.00 | 0.18/1.00 |
| partial | 0.00/0.00 | 0.04/0.01 | 0.69/1.00 | 0.69/1.00 | 0.11/1.00 |
| missing | 0.00/0.00 | 0.00/0.00 | 0.02/0.02 | 0.02/0.02 | 0.10/1.00 |
| mixed | 0.67/0.30 | 0.65/0.34 | 0.61/0.67 | 0.61/0.68 | 0.13/1.00 |

## Per key (mixed errors)

| key | class | CK P/R | UK P/R | CFD P/R |
|---|---|---|---|---|
| SP SeriesPost(year, tmIDLoser) | cand | 1.00/1.00 | 0.62/1.00 | 1.00/0.96 |
| GO Goalies(playerID, year, tmID) | cand | 1.00/1.00 | 0.96/1.00 | 1.00/0.68 |
| CO Coaches(coachID, year) | cand | 1.00/1.00 | 0.30/1.00 | 0.28/0.90 |
| GO2 Goalies(playerID, year) | cand | 1.00/1.00 | 0.04/1.00 | 0.04/0.88 |
| HOF HOF(name) | cand | 1.00/1.00 | 0.80/1.00 | 1.00/1.00 |
| MA1 Master(playerID, firstName, hrefID) | part | 0.91/0.67 | 0.10/0.72 | 0.52/0.18 |
| MA2 Master(firstName, lastName, hrefID) | cert | 0.98/0.69 | 0.76/0.70 | 1.00/0.19 |
| SO soldiers(number) | cand | 1.00/1.00 | 0.95/1.00 | 0.93/0.69 |
| SE seafarers(number) | cand | 1.00/1.00 | 0.95/1.00 | 0.95/0.90 |
| VO1 voyages(number, arrival_date) | cert | 1.00/0.67 | 0.96/0.67 | 0.97/0.27 |
| VO2 voyages(number, departure_date) | cand | 1.00/1.00 | 0.96/1.00 | 0.91/0.27 |
| VO3 voyages(boatname, departure_date) | dom | 1.00/0.37 | 0.98/0.37 | 0.97/0.29 |
| VO4 voyages(number, chamber) | cert | 1.00/0.67 | 0.98/0.67 | 0.97/0.23 |
| IN invoices(number, invoice) | cand | 1.00/1.00 | 0.20/1.00 | 1.00/0.33 |
| TR1 voyages(master, departure_date) | pos | 1.00/0.28 | 0.98/0.28 | 0.12/0.39 |
| TR2 voyages(master, departure_date) | pos | 1.00/0.31 | 0.98/0.31 | 0.11/0.39 |
| NV1 voters(last_name, first_name, middle_name, birth_age, res_street_address) | cert | 1.00/0.67 | 0.85/0.67 | 1.00/0.31 |
| NV2 voters(last_name, first_name, birth_age, res_street_address) | cand | 1.00/1.00 | 0.52/1.00 | 1.00/0.32 |
| NV3 voters(first_name, middle_name, birth_age, birth_state, res_street_address) | dom | 1.00/0.34 | 0.77/0.34 | 1.00/0.32 |
| NVT voters(first_name, middle_name, birth_age, res_street_address) | pos | 1.00/0.32 | 0.69/0.32 | 1.00/0.32 |
| UP1 proteins(cross_reference_geneid, sequence_checksum) | cert | 0.99/0.67 | 0.92/0.67 | 0.89/0.29 |
| UP2 proteins(sequence_checksum, feature_chain) | cert | 1.00/0.67 | 0.97/0.67 | 0.94/0.31 |
