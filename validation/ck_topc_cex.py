"""Concrete check of (B1) on the counterexample for domain keys with completeness constraints
(conditions over bottom and top): R = {A, B}, Sigma = {1:dom(AB), {(B:T)}:nn(A), {(A:T)}:dom(A)},
target 1:dom(A). Sigma implies the target; no choice of the cell for sigma gives a sound (B1)."""
import sys
here = sys.argv[1]
for frag in ('dom,nn', 'pos,dom,part,cert,cand,nn'):
    sys.argv = ['ck_topc.py', here, '0', 'top', frag]
    for m in [k for k in list(sys.modules) if k == 'ck_topc']: del sys.modules[m]
    sys.path.insert(0, here)
    import ck_topc
    from ck import brute_counterexample
    sch = ['A', 'B']; bot = {'A': '_', 'B': '_'}
    Sig = [([bot], 'dom', frozenset('AB')), ([dict(bot, B='T')], 'nn', frozenset('A')),
           ([dict(bot, A='T')], 'dom', frozenset('A'))]
    phi = ([bot], 'dom', frozenset('A'))
    print(frag, 'implied:', brute_counterexample(sch, set(), Sig, phi) is None,
          '| (B1) with p* most complete:', ck_topc.run(sch, set(), Sig, phi, [0], check=True)[0])
    ck_topc.FRAG = ['pos']   # force the least-complete cell
    print(frag, '| (B1) with p* = p:', ck_topc.run(sch, set(), Sig, phi, [0], check=True)[0])
