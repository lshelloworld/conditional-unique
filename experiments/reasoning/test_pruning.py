"""Stress test of compatibility pruning and dominance (implication.implies_pruned) against the
SAT baseline, which is exact (test_implication.py), on 8-column schemas whose premises use
mostly top atoms and constants, so that many columns are dominated."""
import random, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from implication import implies_pruned, implies_sat, open_positions, _relevant

rng = random.Random(3); sch = [f'c{i}' for i in range(8)]
CLS = ['pos', 'dom', 'part', 'cert', 'cand', 'nn']
def tmpl(syms):
    t = {A: '_' for A in sch}
    for A in rng.sample(sch, rng.randint(1, 3)): t[A] = rng.choice(syms)
    return t
agree = imp = 0; red = []
N = 3000
for _ in range(N):
    NN = {A for A in sch if rng.random() < .1}
    syms = rng.choice([('T', 0, 1), ('T', 'N', 0), ('N',), ('T', 'N', 0, 1)])
    Sig = [([tmpl(syms) for _ in range(rng.randint(1, 2))], rng.choice(CLS), frozenset(rng.sample(sch, rng.randint(1, 3))))
           for _ in range(rng.randint(2, 8))]
    phi = ([tmpl(('T', 'N', 0, 1, '_')) for _ in range(rng.randint(1, 2))], rng.choice(CLS), frozenset(rng.sample(sch, rng.randint(1, 3))))
    a, b = implies_pruned(sch, NN, Sig, phi), implies_sat(sch, NN, Sig, phi)
    if a != b: print('MISMATCH', Sig, phi, NN); break
    agree += 1; imp += a
    red.append((open_positions(sch, NN, Sig, phi, False), open_positions(sch, NN, Sig, phi, True)))
print(f'{agree}/{N} agree, {imp} implied; mean b {sum(x for x, _ in red) / N:.1f} -> {sum(y for _, y in red) / N:.1f}')
