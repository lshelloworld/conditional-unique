"""Conditions over bottom and constants (CFD-style), fragments without both partial and certain keys.

Profiles: each column 'b' (null or a value outside the constants) or a constant; b < c.
Construction (as in the paper): for every profile p in the target's scope a derived single-record
constraint psi_p = {tau_p}:Y(L_p), Y in {nn, cand}, by restriction and union from the single-record
premises whose scope contains p; then (B1) {tau_p}:phi from the successor condition, psi_p and at most
two premises of Sigma, and (B2) {tau_p, tau_q}:phi from the two larger conditions, psi_p, psi_q and at
most two premises. Every instance is checked for soundness; the script reports whether the
construction succeeds exactly for implied targets and the largest number of premises used."""
import itertools, random, sys
sys.path.insert(0, sys.argv[1])
from ck import *

def implies(sch, NN, S, p): return canonical_counterexample(sch, NN, S, p) is None

def run(sch, NN, Sig, phi, consts, frag):
    cond, cls, K = phi
    vals = [['b'] + consts for A in sch]
    profs = [dict(zip(sch, c)) for c in itertools.product(*vals)]
    rec = lambda p: {A: (100 if v == 'b' else v) for A, v in p.items()}
    tmpl = lambda p: {A: ('_' if v == 'b' else v) for A, v in p.items()}
    scope = [p for p in profs if any(qualifies(rec(p), t) for t in cond)]
    leq = lambda p, q: all(p[A] == 'b' or p[A] == q[A] for A in sch)
    height = lambda p: sum(v != 'b' for v in p.values())
    succ = lambda p: [dict(p, **{A: c}) for A in sch if p[A] == 'b' for c in consts]
    Y = 'nn' if 'nn' in frag else 'cand' if 'cand' in frag else None
    psi = {}
    for p in scope:          # psi_p: union of the single-record premises that apply to p
        L = set()
        for c_, k_, L_ in Sig:
            if k_ in ('nn', 'cand') and any(leq(tmpl_p, p) for tmpl_p in
                                            [{A: ('b' if t[A] == '_' else t[A]) for A in sch} for t in c_]):
                L |= L_
        psi[tuple(p.values())] = ([tmpl(p)], Y, frozenset(L)) if (Y and L) else None
        if psi[tuple(p.values())] and not implies(sch, NN, Sig, psi[tuple(p.values())]):
            return 'PSI-NOT-IMPLIED', p
    def base(prem0, concl):
        """find at most two premises of Sigma completing prem0 to an instance implying concl"""
        if implies(sch, NN, prem0, concl): return prem0
        for s in Sig:
            if implies(sch, NN, prem0 + [s], concl): return prem0 + [s]
        for s, s2 in itertools.combinations(Sig, 2):
            if implies(sch, NN, prem0 + [s, s2], concl): return prem0 + [s, s2]
        return None
    maxar = 0
    for h in sorted({height(p) for p in scope}, reverse=True):
        for p in [p for p in scope if height(p) == h]:
            prem0 = [x for x in [([tmpl(q) for q in succ(p)], cls, K) if succ(p) else None,
                                 psi[tuple(p.values())]] if x]
            r = base(prem0, ([tmpl(p)], cls, K))
            if r is None: return False, maxar
            maxar = max(maxar, len(r))
        for p, q in itertools.combinations(scope, 2):
            if min(height(p), height(q)) != h: continue
            D1 = [p] + succ(q); D2 = [q] + succ(p)
            prem0 = [([tmpl(x) for x in D1], cls, K), ([tmpl(x) for x in D2], cls, K)]
            prem0 += [x for x in (psi[tuple(p.values())], psi[tuple(q.values())]) if x]
            r = base(prem0, ([tmpl(p), tmpl(q)], cls, K))
            if r is None: return False, maxar
            maxar = max(maxar, len(r))
    return True, maxar

if __name__ == '__main__':
    frag = sys.argv[3].split(',')
    rng = random.Random(int(sys.argv[4]) if len(sys.argv) > 4 else 1); sch = ['A', 'B', 'C', 'D'][:int(sys.argv[5]) if len(sys.argv) > 5 else 3]; consts = [0, 1]
    st = dict(implied=0, notimplied=0, wrong=0, maxar=0)
    for _ in range(int(sys.argv[2])):
        NN = set(A for A in sch if rng.random() < 0.15)
        Sig = [rand_key(sch, rng, sym=('_', '_', 0, 1), classes=frag) for _ in range(rng.randint(2, 6))]
        phi = rand_key(sch, rng, sym=('_', '_', 0, 1), classes=frag)
        imp = implies(sch, NN, Sig, phi)
        r = run(sch, NN, Sig, phi, consts, frag)
        if isinstance(r[0], str): print(r, Sig, phi); break
        ok, ma = r
        st['wrong'] += ok != imp; st['implied' if imp else 'notimplied'] += 1
        if ok: st['maxar'] = max(st['maxar'], ma)
    print(frag, st)
