"""Cross-check: Algorithm 1 (plain and pruned) and the SAT baseline against exhaustive search (validation/ck.py)."""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'validation'))
from ck import brute_counterexample, rand_key
from implication import implies_canonical, implies_sat, implies_pruned

rng = random.Random(5); agree = imp = 0; T = 1500
for trial in range(T):
    sch = ['A', 'B', 'C', 'D'][:rng.choice([3, 4])]
    NN = {A for A in sch if rng.random() < .15}
    Sig = [rand_key(sch, rng) for _ in range(rng.randint(1, 6))]
    phi = rand_key(sch, rng)
    b = brute_counterexample(sch, NN, Sig, phi) is None
    c = implies_canonical(sch, NN, Sig, phi); s = implies_sat(sch, NN, Sig, phi); p = implies_pruned(sch, NN, Sig, phi)
    if b == c == s == p: agree += 1
    else: print('MISMATCH', b, c, s, p, Sig, phi); break
    imp += b
print(f'{agree}/{T} agree, {imp} implied')
