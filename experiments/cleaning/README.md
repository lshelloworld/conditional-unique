# E7: data cleaning with discovered conditional keys

- `run_e7.py`: 22 discovered conditional keys (the 19 query-optimisation cases of Hockey, VOC,
  NCVoter and UniProt plus three partial/certain keys with missing key values); injects 2% errors (at least 10) into each
  key's scope (duplicates, incomplete copies, missing identifiers, mixed); runs the detectors
  CK-<class> (conditional key), UK-<class> (unconditional key) and CFD (Fan et al., Q^V
  semantics); 5 seeds; writes `results_e7.json` with raw counts.
- `summarize_e7.py [results_e7|results_e7_anywhere]`: summarises the counts into the matching
  `.md` file. The paper's table uses its first section: precision averaged over the keys on which
  CK, UK and CFD all flag something, recall over all keys.
- `test_detectors.py`: brute-force check of the detectors (2,400 small random instances).

Metrics: recall = share of erroneous records (injected copies, modified records) flagged;
precision = share of flagged records that are erroneous or the source of an injected copy.
Conflicts among real records outside the scope are legitimate and count against precision.

Reproduce (pure Python, no database needed, about 35 seconds):

```bash
python run_e7.py && python summarize_e7.py
```

## Errors anywhere in the table

`python run_e7.py --anywhere --seeds 3 --out results_e7_anywhere.json` draws the source records
of the injected errors from the whole table instead of the scope (copies keep their source's
condition values, so errors outside the scope stay outside); `python summarize_e7.py
results_e7_anywhere` writes `results_e7_anywhere.md`.

## Near-holding keys

`run_e7_near.py` uses up to three near-holding conditional keys per table from discovery (keys
violated by a few pairs in their scope on the real data; those conflicts count against
precision), injects errors anywhere (3 seeds) and reports precision, recall and review cost;
`summarize_e7_near.py` writes `results_e7_near.md` (precision over keys on which all detectors
flag something, recall over all keys, false positives per error found pooled over keys).
