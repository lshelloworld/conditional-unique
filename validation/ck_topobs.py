"""Obstruction for conditions over bottom and top (no null) with domain keys and completeness (or
candidate) constraints: the facts used in the proof, checked by exhaustive search.

Columns a, u_1..u_k, all nullable. Sigma_k:
  P0  = {(a:T)}:dom(a)
  P_i = 1:dom(a, u_i)                          i = 1..k
  Y   = {(u_1:T), ..., (u_k:T)}:dom(a)
  H   = {(u_1:T, ..., u_k:T)}:nn(a)   (variant: cand(a))
Target 1:dom(a). Test pairs Q_S, S a subset of {u_i}: an all-null record and a record that has
values exactly on S (null on a).
Checked: (1) Sigma_k implies the target; (2) every unconditional key or completeness constraint
implied by Sigma_k forbids no Q_S, or exactly {Q_S : S disjoint from X} for a nonempty X, or all
Q_S (only dom(a)); (3) a constraint over a single template with top on T (single-record classes)
that is implied forbids at most Q_U (every u present); (4) each premise forbids no Q_S, Q_S with
u_i not in S, or only Q_U."""
import itertools, sys
sys.path.insert(0, sys.argv[1])
from ck import *

def implies(sch, S, p): return canonical_counterexample(sch, set(), S, p) is None

for variant in ('nn', 'cand'):
    for k in (2, 3, 4):
        U = ['u%d' % i for i in range(1, k + 1)]; sch = ['a'] + U
        bot = {c: '_' for c in sch}
        T = lambda *cs: dict(bot, **{c: 'T' for c in cs})
        Sig = [([T('a')], 'dom', frozenset('a'))]
        Sig += [([bot], 'dom', frozenset(['a', u])) for u in U]
        Sig += [([T(u) for u in U], 'dom', frozenset('a'))]
        Sig += [([T(*U)], variant, frozenset('a'))]
        phi = ([bot], 'dom', frozenset('a'))
        ok = implies(sch, Sig, phi)
        Q = {}
        for r in range(k + 1):
            for S in itertools.combinations(U, r):
                t = {c: None for c in sch}; u = {c: (10 + i if c in S else None) for i, c in enumerate(sch)}
                Q[frozenset(S)] = [t, u]
        V = lambda key: {S for S, q in Q.items() if not sat_key(q, key)}
        allS = set(Q)
        down = lambda X: {S for S in Q if not (S & X)}
        # (4) premises
        ok &= V(Sig[0]) == set()
        ok &= all(V(Sig[1 + i]) == down({U[i]}) for i in range(k))
        ok &= V(Sig[1 + k]) == set() and V(Sig[2 + k]) == {frozenset(U)}
        # (2) unconditional constraints
        for cls in ('pos', 'dom', 'part', 'cert', 'cand', 'nn'):
            for r in range(len(sch) + 1):
                for L in itertools.combinations(sch, r):
                    key = ([bot], cls, frozenset(L))
                    if not implies(sch, Sig, key): continue
                    v = V(key)
                    good = v == set() or v == allS or any(v == down(set(X)) for rr in range(1, k + 1)
                                                         for X in itertools.combinations(U, rr))
                    if v == allS: good &= (cls, frozenset(L)) == ('dom', frozenset('a'))
                    if not good: ok = False; print('BAD uncond', cls, L, v)
        # (3) single-template conditions with top entries, single-record classes
        for r in range(1, len(sch) + 1):
            for Tc in itertools.combinations(sch, r):
                for cls in ('nn', 'cand'):
                    for rl in range(1, len(sch) + 1):
                        for L in itertools.combinations(sch, rl):
                            key = ([T(*Tc)], cls, frozenset(L))
                            if implies(sch, Sig, key) and not V(key) <= {frozenset(U)}:
                                ok = False; print('BAD single', Tc, cls, L, V(key))
        print(variant, 'k =', k, 'all facts hold:', ok)
