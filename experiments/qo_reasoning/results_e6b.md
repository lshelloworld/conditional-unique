# E6b: rewrites decided by implication from a catalog of filtered indexes

| table | rows | catalog | queries | full | full wrong | single | UNIQUE | UNIQUE wrong | correct, not licensed | impl. ms (median/max) | speed-up DISTINCT / LEFT JOIN (median) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Hockey.Coaches | 1812 | 116 | 336 | 262 | 0 | 123 | 246 | 0 | 10 | 1.6 / 7.9 | 1.3x / 3.2x |
| Hockey.Goalies | 4278 | 71 | 320 | 247 | 0 | 171 | 250 | 2 | 7 | 1.1 / 11.0 | 1.6x / 3.4x |
| Hockey.SeriesPost | 832 | 166 | 332 | 256 | 0 | 122 | 244 | 0 | 7 | 2.3 / 9.7 | 1.7x / 3.2x |
| Hockey.Teams | 1519 | 195 | 334 | 248 | 0 | 138 | 240 | 5 | 13 | 2.9 / 9.1 | 2.2x / 3.5x |
| Hockey.TeamsPost | 927 | 168 | 342 | 264 | 0 | 130 | 242 | 0 | 13 | 2.6 / 10.3 | 1.4x / 3.1x |
| voc.voyages | 8131 | 180 | 288 | 230 | 0 | 129 | 230 | 0 | 16 | 2.5 / 9.5 | 2.5x / 3.7x |
| voc.seafarers | 4468 | 36 | 292 | 188 | 0 | 140 | 220 | 47 | 7 | 0.6 / 9.5 | 1.2x / 3.2x |
| ncvoter.voters | 1023993 | 72 | 344 | 139 | 0 | 121 | 242 | 114 | 2 | 1.3 / 20.4 | 1.9x / 13.2x |
| uniprot.proteins | 24173 | 154 | 320 | 261 | 0 | 131 | 262 | 0 | 26 | 1.8 / 7.7 | 2.8x / 4.5x |

Totals: queries 2908, full 2095, full_wrong 0, single 1205, unique 2176, unique_wrong 168, missed 101. Implication time over all queries: median 1.9 ms, max 20.4 ms. Median speed-up of licensed rewrites: DISTINCT 1.8x, LEFT JOIN 3.5x.

## By query kind

| kind | template | queries | correct | full | single | UNIQUE | UNIQUE wrong |
|---|---|---|---|---|---|---|---|
| exact | DISTINCT | 348 | 289 | 289 | 37 | 348 | 59 |
| exact | LEFTJOIN | 348 | 348 | 348 | 348 | 348 | 0 |
| random | DISTINCT | 348 | 71 | 39 | 1 | 43 | 2 |
| random | LEFTJOIN | 348 | 107 | 43 | 43 | 43 | 0 |
| refined | DISTINCT | 348 | 295 | 290 | 42 | 348 | 53 |
| refined | LEFTJOIN | 348 | 348 | 348 | 348 | 348 | 0 |
| superkey | DISTINCT | 348 | 294 | 294 | 37 | 348 | 54 |
| superkey | LEFTJOIN | 348 | 348 | 348 | 348 | 348 | 0 |
| union | DISTINCT | 62 | 34 | 34 | 0 | 1 | 0 |
| union | LEFTJOIN | 62 | 62 | 62 | 1 | 1 | 0 |
