# E7, real errors: duplicate registrations in NCVoter

The statewide NCVoter file contains 382 registrations with status reason DUPLICATE, i.e. removed
by the state as duplicates of another registration. `ncvoter_real.py` takes the 300 near-holding
conditional keys mined on the full, uncleaned file (`discovery/results/ncvoter-full.json`,
`approximate`), the same keys without conditions, and hand-picked unconditional name keys, and
reports flagged records, confirmed records (a removed duplicate or a record in a violating pair
with one) and the lift over the base rate. Output: `results_ncvoter_real.json`.

```bash
python ncvoter_real.py
```
