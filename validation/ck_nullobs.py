"""Obstruction for conditions over bottom and null (no top): facts used in the proof.

Schema K = {a_1..a_k}, NN empty.
Sigma_k = { pos(K - X) : |X| <= 2 }  u  { {(a_i: null)} : nn(a_j) : i != j }
Targets cert(K) and part(K).  Test pairs Q_j: t total, t' null exactly on a_j, equal elsewhere.
Variants replace pos by dom and nn by cand (pass any second argument).
Checked: Sigma_k implies both targets; every unconditional key implied by Sigma_k forbids at most two
or all of the Q_j; every premise forbids at most two."""
import sys, itertools; sys.path.insert(0, sys.argv[1])
from ck import *
def implies(sch, NN, S, p): return canonical_counterexample(sch, NN, S, p) is None

VARIANTS = [(x, y) for x in ('pos', 'dom') for y in ('nn', 'cand')]
for (X1, Y1), k in itertools.product(VARIANTS if len(sys.argv) > 2 else [('pos', 'nn')],
                                     (4, 5, 6) if len(sys.argv) > 2 else (4, 5, 6, 7)):
    K = ['a%d' % i for i in range(k)]; NN = set(); one = {A: '_' for A in K}
    Sig = [([one], X1, frozenset(set(K) - set(X))) for r in range(3) for X in itertools.combinations(K, r)]
    Sig += [([dict(one, **{a: 'N'})], Y1, frozenset([b])) for a in K for b in K if a != b]
    Q = []
    for j, a in enumerate(K):
        t = {A: 10 + i for i, A in enumerate(K)}; u = dict(t); u[a] = None; Q.append([t, u])
    VQ = lambda key: {j for j, q in enumerate(Q) if not sat_key(q, key)}
    ok = implies(K, NN, Sig, ([one], 'cert', frozenset(K))) and implies(K, NN, Sig, ([one], 'part', frozenset(K)))
    ok &= all(len(VQ(s)) <= 2 for s in Sig)
    for cls in ('pos', 'dom', 'part', 'cert', 'cand', 'nn'):
        for r in range(k + 1):
            for L in itertools.combinations(K, r):
                key = ([one], cls, frozenset(L))
                if implies(K, NN, Sig, key):
                    v = len(VQ(key)); ok &= v <= 2 or v == k
    print(X1, Y1, 'k =', k, 'all facts hold:', ok)
