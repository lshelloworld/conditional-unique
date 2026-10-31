"""Exact minimum arity for the obstruction Sigma_k of ck_topobs.py in the abstract framework of
ck_arity.py (templates over bottom and top, classes dom and nn (or cand)): the target 1:dom(a) is
reached by the m-ary closure only for m >= k+1."""
import sys
sys.path.insert(0, sys.argv[1])
from ck_arity import *

for k in (2, 3):
    n = k + 1                      # column 0 is a, columns 1..k are the u_i
    for v in ('nn', 'cand'):
        U, L = language(n, 'top', classes=('dom', v))
        inv = {}
        for m, key in L.items(): inv.setdefault(key, m)
        def E(S, cls, K):
            for m, key in L.items():
                if key == (S, cls, K): return m
            m = 0
            for i, (kind, x) in enumerate(U):
                if forbids(S, cls, K, kind, x): m |= 1 << i
            return m
        sets = [frozenset(X) for r in range(n + 1) for X in itertools.combinations(range(n), r)]
        up = lambda D: frozenset(s for s in sets if any(s >= X for X in D))
        uu = frozenset(range(1, n))
        Sig = [E(up([frozenset([0])]), 'dom', (0,))]
        Sig += [E(up([frozenset()]), 'dom', (0, i)) for i in range(1, n)]
        Sig += [E(up([frozenset([i]) for i in range(1, n)]), 'dom', (0,))]
        Sig += [E(up([uu]), v, (0,))]
        tgt = E(up([frozenset()]), 'dom', (0,))
        print(v, 'k =', k, 'minimum arity:', min_arity(L, Sig, tgt, mmax=k + 2))
