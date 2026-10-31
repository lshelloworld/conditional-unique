"""Odd cycles under conditions over bottom and null: the mirror image of the 4-ary derivation of
ck_cycle.py, with (A_i: null) in place of (A_i: top)."""
import sys; sys.path.insert(0, sys.argv[1])
from ck import *
from ck_cycle import cycle
def implies(sch, NN, S, p): return canonical_counterexample(sch, NN, S, p) is None
def nul(V, *cols):
    t = {A: '_' for A in V}; t.update({c: 'N' for c in cols}); return t
for n in (5, 7):
    V, Sig, one = cycle(n); pk = lambda i: Sig[i % n]; full = frozenset(V); ok = True
    for j in range(n):
        ok &= implies(V, set(), [pk(j - 1), pk(j)], ([nul(V, V[j])], 'cert', full))
    for i in range(n):
        for j in range(n):
            prem = [pk(i - 1), pk(i), pk(i + 1), ([nul(V, V[(i + 2) % n]), nul(V, V[j])], 'cert', full)]
            ok &= implies(V, set(), prem, ([nul(V, V[i]), nul(V, V[j])], 'cert', full))
    ok &= implies(V, set(), [([nul(V, A) for A in V], 'cert', full), pk(0)], ([one], 'cert', full))
    print('n =', n, 'null-condition cycle derivation sound:', ok)
