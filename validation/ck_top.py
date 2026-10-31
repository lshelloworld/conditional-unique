"""3-ary axiomatisation for conditions over bottom and top (no null symbol, no constants).

Works in the abstract framework of ck_arity.py: a template with top exactly on X is identified with X,
a condition with the up-closure of its templates. The script builds the derivation of the
completeness proof (rules P, B1, B2) for random Sigma |= target and checks every step exactly:
each conclusion's forbidden set is covered by the premises' forbidden sets, and no rule has more than
three premises. It also checks that a derivation exists only for implied targets."""
import itertools, random, sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else '.')
from ck_arity import *
CLS = ['pos', 'dom', 'part', 'cert', 'cand', 'nn']
FRAG = sys.argv[2].split(',') if len(sys.argv) > 2 else CLS

def setup(n):
    U = universe(n); idx = {u: i for i, u in enumerate(U)}
    V = frozenset(range(n))
    def upc(D):
        return frozenset(frozenset(W) for r in range(n + 1) for W in itertools.combinations(range(n), r)
                         if any(frozenset(W) >= X for X in D))
    def E(D, cls, K):
        S = upc(D); m = 0
        for i, (kind, x) in enumerate(U):
            if forbids(S, cls, K, kind, x): m |= 1 << i
        return m
    def canon_pair(X, Y, K):
        ty = tuple('eq' if (a in X and a in Y and a in K) else 'dd' if (a in X and a in Y)
                   else 'vn' if a in X else 'nv' if a in Y else 'bn' for a in range(n))
        sw = tuple(SWAP[x] for x in ty)
        return 1 << idx[('p', ty)] if ('p', ty) in idx else 1 << idx[('p', sw)]
    def canon_rec(X): return 1 << idx[('s', frozenset(X))]
    return U, V, upc, E, canon_pair, canon_rec

def derive_top(n, Sig, target, tools):
    """Sig: list of (bitmask); target: (D, cls, K). Returns (ok, steps)."""
    U, V, upc, E, cp, cr = tools
    D0, cls, K = target
    S = upc(D0); steps = []; derived = set()
    def uses(D):  # the key on D comes from already derived one- and two-template keys by pairing
        for X in D: assert frozenset([X]) in derived, ('missing single', X)
        for X, Y in itertools.combinations(set(D), 2): assert frozenset([X, Y]) in derived, ('missing pair', X, Y)
        assert assembled(list(set(D)), cls, K, E)
    def need(bit):  # a premise of Sigma that forbids this canonical object
        for s in Sig:
            if s & bit: return s
        return None
    phiE = lambda D: E(D, cls, K)
    def viol_bit(b): return phiE([frozenset()]) & b  # object violates phi (unconditionally)
    order = sorted(S, key=len, reverse=True)
    singles = {}
    pairs = list(itertools.combinations(order, 2))
    levels = sorted({len(X) for X in S}, reverse=True)
    for m in levels:
        for X in [X for X in S if len(X) == m]:                       # rule B1
            prem = []
            DX = [X | {a} for a in V - X]
            if DX: uses(DX); prem.append(phiE(DX))
            block = [W for W in S if W >= X and viol_bit(cp(X, W, K))]
            if block:
                if 'dom' in FRAG:   # no nn, cand: the most complete violating cell
                    top = max(block, key=len)
                    assert all(W <= top for W in block), 'block has no unique top'
                else:               # no dom: the least complete cell, X itself
                    assert X in block, 'block misses its least cell'
                    top = X
                s = need(cp(X, top, K))
                if s is None: return False, steps
                prem.append(s)
            if viol_bit(cr(X)):
                s = need(cr(X))
                if s is None: return False, steps
                prem.append(s)
            steps.append(('B1', prem, phiE([X]))); derived.add(frozenset([X]))
        lvl = [(X, Y) for X, Y in pairs if min(len(X), len(Y)) == m]
        for X, Y in sorted(lvl, key=lambda p: -max(len(p[0]), len(p[1]))):  # rule B2
            D1 = [X] + [Y | {b} for b in V - Y]; D2 = [Y] + [X | {a} for a in V - X]
            uses(D1); uses(D2); prem = [phiE(D1), phiE(D2)]
            if viol_bit(cp(X, Y, K)):
                s = need(cp(X, Y, K))
                if s is None: return False, steps
                prem.append(s)
            steps.append(('B2', prem, phiE([X, Y]))); derived.add(frozenset([X, Y]))
    uses([X for X in D0])
    return True, steps

def assembled(D, cls, K, E):
    """pairing: the key on D is covered by its one- and two-template keys"""
    u = 0
    for X in D: u |= E([X], cls, K)
    for X, Y in itertools.combinations(D, 2): u |= E([X, Y], cls, K)
    return E(D, cls, K) | u == u

if __name__ == '__main__':
    for n, trials in ((3, 3000), (4, 400)):
        tools = setup(n); U, V, upc, E, cp, cr = tools
        sets = [frozenset(X) for r in range(n + 1) for X in itertools.combinations(range(n), r)]
        rng = random.Random(n); st = dict(implied=0, notimplied=0, steps=0, bad_step=0, bad_pairing=0,
                                         wrong=0, max_arity=0)
        for _ in range(trials):
            def rkey():
                D = rng.sample(sets, rng.randint(1, 3))
                K = tuple(a for a in range(n) if rng.random() < .5)
                return D, rng.choice(FRAG), K
            Sig = [E(*rkey()) for _ in range(rng.randint(2, 7))]
            tgt = rkey(); te = E(*tgt); u = 0
            for s in Sig: u |= s
            imp = te | u == u
            ok, steps = derive_top(n, Sig, tgt, tools)
            if ok != imp: st['wrong'] += 1
            st['implied' if imp else 'notimplied'] += 1
            if ok:
                for rule, prem, concl in steps:
                    st['steps'] += 1; st['max_arity'] = max(st['max_arity'], len(prem))
                    pu = 0
                    for p in prem: pu |= p
                    if concl | pu != pu: st['bad_step'] += 1
                if not assembled(tgt[0], tgt[1], tgt[2], E): st['bad_pairing'] += 1
        print(','.join(FRAG), n, st)
