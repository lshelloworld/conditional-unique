# E7 with near-holding keys, errors anywhere (3 seeds)

| errors | keys (common) | CK P / R / FP per error found | UK P / R / FP per error found | CFD P / R / FP per error found |
|---|---|---|---|---|
| dup | 27 (27) | 0.96 / 0.75 / 0.021 | 0.95 / 0.88 / 0.113 | 0.92 / 0.69 / 0.892 |
| mixed | 27 (27) | 0.91 / 0.60 / 0.062 | 0.88 / 0.71 / 0.313 | 0.85 / 0.51 / 2.625 |

Keys where the condition raises precision by at least 0.05 (duplicates): 4 of 27: Master-2 0.85->0.99, voters-0 0.84->0.97, voters-1 0.72->0.97, voters-2 0.80->0.97

## Per key

| key | class | condition | errors | CK P/R | UK P/R | CFD P/R |
|---|---|---|---|---|---|---|
| Coaches-0 (year, tmID, stint) | cert | `(postg IS NULL)` | dup | 0.8696/0.3922 | 0.9444/1.0 | 0.9333/0.8235 |
| Coaches-0 (year, tmID, stint) | cert | `(postg IS NULL)` | mixed | 0.7692/0.5556 | 0.8571/1.0 | 0.8235/0.7778 |
| Coaches-1 (year, tmID, stint) | part | `(postg IS NULL)` | dup | 0.8889/0.4706 | 0.9444/1.0 | 0.9231/0.7059 |
| Coaches-1 (year, tmID, stint) | part | `(postg IS NULL)` | mixed | 0.7857/0.6111 | 0.8571/1.0 | 0.8125/0.7222 |
| Coaches-2 (year, tmID, stint) | dom | `(postg IS NULL)` | dup | 0.8571/0.3529 | 0.9444/1.0 | 0.9231/0.7059 |
| Coaches-2 (year, tmID, stint) | dom | `(postg IS NULL)` | mixed | 0.7273/0.4444 | 0.8571/1.0 | 0.85/0.9444 |
| Goalies-0 (playerID, year, tmID) | cert | `(ENG IS NOT NULL)` | dup | 0.9832/0.8381 | 0.9859/1.0 | 0.9788/0.6619 |
| Goalies-0 (playerID, year, tmID) | cert | `(ENG IS NOT NULL)` | mixed | 0.9516/0.8194 | 0.96/1.0 | 0.9423/0.6806 |
| Goalies-1 (playerID, year, tmID) | part | `(ENG IS NOT NULL)` | dup | 0.9815/0.7571 | 0.9858/1.0 | 0.9784/0.6524 |
| Goalies-1 (playerID, year, tmID) | part | `(ENG IS NOT NULL)` | mixed | 0.94/0.6528 | 0.9597/1.0 | 0.931/0.5694 |
| Goalies-2 (playerID, year, tmID) | dom | `(ENG IS NOT NULL)` | dup | 0.983/0.8238 | 0.9859/1.0 | 0.9773/0.6143 |
| Goalies-2 (playerID, year, tmID) | dom | `(ENG IS NOT NULL)` | mixed | 0.9516/0.8194 | 0.96/1.0 | 0.9455/0.7222 |
| Master-0 (firstName, lastName, legendsID) | dom | `(playerID IS NOT NULL)` | dup | 0.9931/0.9644 | 0.9934/1.0 | 0.9883/0.5622 |
| Master-0 (firstName, lastName, legendsID) | dom | `(playerID IS NOT NULL)` | mixed | 0.977/0.34 | 0.9772/0.3422 | 0.9607/0.1933 |
| Master-1 (lastName, nameGiven, hrefID) | dom | `(playerID IS NOT NULL)` | dup | 0.9931/0.9667 | 0.9934/1.0 | 0.9874/0.5267 |
| Master-1 (lastName, nameGiven, hrefID) | dom | `(playerID IS NOT NULL)` | mixed | 0.9792/0.3156 | 0.9802/0.3333 | 0.9627/0.1756 |
| Master-2 (firstName, lastName, hrefID) | cert | `(birthMon IS NOT NULL)` | dup | 0.9932/0.98 | 0.8494/1.0 | 1.0/0.5889 |
| Master-2 (firstName, lastName, hrefID) | cert | `(birthMon IS NOT NULL)` | mixed | 0.9516/0.6711 | 0.7476/0.7067 | 1.0/0.1889 |
| SeriesPost-0 (year, lgIDWinner, tmIDLoser) | cert | `(note IS NULL)` | dup | 0.8842/0.9333 | 0.8911/1.0 | 0.8911/1.0 |
| SeriesPost-0 (year, lgIDWinner, tmIDLoser) | cert | `(note IS NULL)` | mixed | 0.6842/0.8667 | 0.7143/1.0 | 0.7143/1.0 |
| SeriesPost-1 (year, lgIDWinner, tmIDLoser) | part | `(note IS NULL)` | dup | 0.8854/0.9556 | 0.89/1.0 | 0.89/1.0 |
| SeriesPost-1 (year, lgIDWinner, tmIDLoser) | part | `(note IS NULL)` | mixed | 0.7143/1.0 | 0.7143/1.0 | 0.7143/1.0 |
| SeriesPost-2 (year, lgIDWinner, tmIDLoser) | dom | `(note IS NULL)` | dup | 0.8696/0.8889 | 0.8824/1.0 | 0.88/0.9778 |
| SeriesPost-2 (year, lgIDWinner, tmIDLoser) | dom | `(note IS NULL)` | mixed | 0.7143/1.0 | 0.7143/1.0 | 0.7/0.9333 |
| seafarers-0 (number) | cert | `(onboard_at_departure IS NOT NULL)` | dup | 0.9876/0.9373 | 0.9883/1.0 | 0.984/0.7294 |
| seafarers-0 (number) | cert | `(onboard_at_departure IS NOT NULL)` | mixed | 0.9639/0.9195 | 0.9667/1.0 | 0.9524/0.6897 |
| seafarers-1 (number) | part | `(onboard_at_departure IS NOT NULL)` | dup | 0.988/0.9686 | 0.9883/1.0 | 0.9845/0.749 |
| seafarers-1 (number) | part | `(onboard_at_departure IS NOT NULL)` | mixed | 0.9663/0.9885 | 0.9667/1.0 | 0.9538/0.7126 |
| seafarers-2 (number) | dom | `(onboard_at_departure IS NOT NULL)` | dup | 0.9875/0.9373 | 0.9883/1.0 | 0.9832/0.698 |
| seafarers-2 (number) | dom | `(onboard_at_departure IS NOT NULL)` | mixed | 0.9647/0.9425 | 0.9667/1.0 | 0.9492/0.6437 |
| soldiers-0 (number) | cert | `(onboard_at_departure IS NOT NULL)` | dup | 0.9861/0.9307 | 0.9871/1.0 | 0.9732/0.4805 |
| soldiers-0 (number) | cert | `(onboard_at_departure IS NOT NULL)` | mixed | 0.9615/0.9615 | 0.963/1.0 | 0.9362/0.5641 |
| soldiers-1 (number) | part | `(onboard_at_departure IS NOT NULL)` | dup | 0.9859/0.9134 | 0.9871/1.0 | 0.9767/0.5498 |
| soldiers-1 (number) | part | `(onboard_at_departure IS NOT NULL)` | mixed | 0.9589/0.8974 | 0.963/1.0 | 0.9318/0.5256 |
| soldiers-2 (number) | dom | `(onboard_at_departure IS NOT NULL)` | dup | 0.9862/0.9351 | 0.9871/1.0 | 0.9754/0.5195 |
| soldiers-2 (number) | dom | `(onboard_at_departure IS NOT NULL)` | mixed | 0.96/0.9231 | 0.963/1.0 | 0.9302/0.5128 |
| voyages-0 (number, type_of_boat) | dom | `(arrival_date IS NOT NULL)` | dup | 0.9931/0.9499 | 0.9934/1.0 | 0.9916/0.7821 |
| voyages-0 (number, type_of_boat) | dom | `(arrival_date IS NOT NULL)` | mixed | 0.9803/0.4419 | 0.9809/0.4564 | 0.9725/0.3169 |
| voyages-1 (number, chamber) | cert | `(arrival_date IS NOT NULL)` | dup | 0.9932/0.9521 | 0.987/1.0 | 0.9913/0.7495 |
| voyages-1 (number, chamber) | cert | `(arrival_date IS NOT NULL)` | mixed | 0.9896/0.6294 | 0.9805/0.6667 | 0.9752/0.2632 |
| voyages-2 (number, chamber) | part | `(arrival_date IS NOT NULL)` | dup | 0.9931/0.939 | 0.9871/1.0 | 0.9908/0.7059 |
| voyages-2 (number, chamber) | part | `(arrival_date IS NOT NULL)` | mixed | 0.9895/0.622 | 0.9789/0.6659 | 0.975/0.2571 |
| proteins-0 (cross_reference_geneid, sequence_checksum) | pos | `(feature_strand IS NULL)` | dup | 0.9975/0.8561 | 0.9975/0.8697 | 0.9708/0.8333 |
| proteins-0 (cross_reference_geneid, sequence_checksum) | pos | `(feature_strand IS NULL)` | mixed | 0.9922/0.2879 | 0.9925/0.2984 | 0.9171/0.3006 |
| proteins-1 (cross_reference_geneid, sequence) | pos | `(feature_strand IS NULL)` | dup | 0.9975/0.8497 | 0.9976/0.8761 | 0.9707/0.8426 |
| proteins-1 (cross_reference_geneid, sequence) | pos | `(feature_strand IS NULL)` | mixed | 0.9924/0.2942 | 0.9926/0.3025 | 0.9164/0.2972 |
| proteins-2 (cross_reference_geneid, sequence_checksum, sequence) | pos | `(feature_strand IS NULL)` | dup | 0.9974/0.8333 | 0.9975/0.8604 | 0.9709/0.8241 |
| proteins-2 (cross_reference_geneid, sequence_checksum, sequence) | pos | `(feature_strand IS NULL)` | mixed | 0.9924/0.2925 | 0.9926/0.3015 | 0.9152/0.294 |
| voters-0 (last_name, first_name, middle_name, name_suffix_lbl, res_street_address) | pos | `(birth_state IS NULL)` | dup | 0.9722/0.0081 | 0.8414/0.0454 | 0.7098/0.9616 |
| voters-0 (last_name, first_name, middle_name, name_suffix_lbl, res_street_address) | pos | `(birth_state IS NULL)` | mixed | 0.9333/0.0032 | 0.6177/0.0139 | 0.452/0.3235 |
| voters-1 (middle_name, name_suffix_lbl, res_street_address) | pos | `(status_cd = 'I')` | dup | 0.9684/0.0085 | 0.7234/0.0438 | 0.2871/0.1713 |
| voters-1 (middle_name, name_suffix_lbl, res_street_address) | pos | `(status_cd = 'I')` | mixed | 0.8846/0.0022 | 0.4531/0.0141 | 0.1262/0.0642 |
| voters-2 (first_name, middle_name, name_suffix_lbl, res_street_address) | pos | `(status_cd = 'I')` | dup | 0.9665/0.008 | 0.8036/0.0478 | 0.8352/0.1618 |
| voters-2 (first_name, middle_name, name_suffix_lbl, res_street_address) | pos | `(status_cd = 'I')` | mixed | 0.9091/0.0028 | 0.5717/0.0156 | 0.6333/0.0552 |
