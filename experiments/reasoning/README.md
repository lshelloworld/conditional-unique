# E2: cost of implication

- `implication.py`: Algorithm 1 (canonical counterexamples) and a SAT baseline (Tseitin
  encoding of one- and two-record counterexamples, CaDiCaL via PySAT).
- `test_implication.py`: both agree with exhaustive search (`validation/ck.py`) on 1,500 random
  small instances.
- `e2.py`: benchmark (30 columns, random conditional keys; varies |Sigma|, b and |C|), writes
  `results_e2.json`; log in `log_e2.txt`.

```bash
pip install python-sat
```

```bash
python e2.py
```
