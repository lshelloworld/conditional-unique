"""The 3-ary derivation for conditions over bottom, top and constants (no null symbol), checked
against exhaustive search with ck.py. A record profile assigns each column null, 'F' (a value that is
no constant) or a constant; profiles are ordered null < F < c, and the template of a profile p is
bottom/top/c where p is null/F/c, whose scope is the up-set of p."""
import itertools, random, sys
sys.path.insert(0, sys.argv[1])
from ck import *

def implies(sch, NN, S, p): return brute_counterexample(sch, NN, S, p) is None

MODE = sys.argv[3] if len(sys.argv) > 3 else 'top'
FRAG = sys.argv[4].split(',') if len(sys.argv) > 4 else CLASSES
# 'top':  profiles null < F < c, templates bottom/top/c
# 'null': profiles F < null and F < c (null acts as one more constant), templates bottom/null/c
# 'full': top and null; targets are first null-split, profiles F < c with null isolated,
#         templates null/top/c
def tmpl(p):
    if MODE == 'top': return {A: ('_' if v is None else 'T' if v == 'F' else v) for A, v in p.items()}
    if MODE == 'full': return {A: ('N' if v is None else 'T' if v == 'F' else v) for A, v in p.items()}
    return {A: ('_' if v == 'F' else 'N' if v is None else v) for A, v in p.items()}
def leq(p, q):
    if MODE == 'top':
        return all(p[A] is None or (p[A] == 'F' and q[A] is not None) or p[A] == q[A] for A in p)
    if MODE == 'full':
        return all(p[A] == q[A] or (p[A] == 'F' and q[A] not in (None, 'F')) for A in p)
    return all(p[A] == 'F' or p[A] == q[A] for A in p)

def run(sch, NN, Sig, phi, consts, check):
    cond, cls, K = phi
    vals = lambda A: ([] if A in NN else [None]) + ['F'] + consts
    profs = [dict(zip(sch, c)) for c in itertools.product(*[vals(A) for A in sch])]
    scope = [p for p in profs if any(qualifies({A: (100 if v == 'F' else v) for A, v in p.items()}, t) for t in cond)]
    key = lambda p: tuple(str(p[A]) for A in sch)
    height = (lambda p: sum(0 if v is None else 1 if v == 'F' else 2 for v in p.values())) if MODE == 'top' \
        else (lambda p: sum(v not in (None, 'F') for v in p.values())) if MODE == 'full' \
        else (lambda p: sum(0 if v == 'F' else 1 for v in p.values()))
    def canon(p, q):
        t, u = {}, {}; f = iter(range(300, 10**6))
        for A in sch:
            x, y = p[A], q[A]
            if x == 'F' and y == 'F':
                if A in K: t[A] = u[A] = next(f)
                else: t[A], u[A] = next(f), next(f)
            else:
                t[A] = next(f) if x == 'F' else x
                u[A] = next(f) if y == 'F' else y
        return [t, u]
    def crec(p): return [canon(p, p)[0]]
    vio = lambda inst: not sat_key(inst, ([{A: '_' for A in sch}], cls, K))
    def need(inst):
        for s in Sig:
            if not sat_key(inst, s): return s
        return None
    if MODE == 'full':
        succ = lambda p: [dict(p, **{A: c}) for A in sch if p[A] == 'F' for c in consts]
    elif MODE == 'top':
        succ = lambda p: [dict(p, **{A: 'F'}) for A in sch if p[A] is None] + \
                         [dict(p, **{A: c}) for A in sch if p[A] == 'F' for c in consts]
    else:
        succ = lambda p: [dict(p, **{A: v}) for A in sch if p[A] == 'F'
                          for v in ([] if A in NN else [None]) + consts]
    steps, nsteps, maxar = 0, 0, 0
    lv = sorted({height(p) for p in scope}, reverse=True)
    for h in lv:
        for p in [p for p in scope if height(p) == h]:                       # B1
            prem = []
            D = succ(p)
            if D: prem.append(([tmpl(q) for q in D], cls, K))
            s2 = None
            if vio(crec(p)):                                   # sigma': canonical record
                s2 = need(crec(p))
                if s2 is None: return False, nsteps, maxar
            if MODE == 'top' and 'dom' not in FRAG:   # p* = p: the least complete cell
                pstar = p
            elif MODE == 'top':   # p* raises nulls: the most complete cell (no nn, cand in F)
                pstar = {A: ('F' if p[A] is None and not (cls in ('dom', 'cand') and A in K) else p[A])
                         for A in sch}
            elif MODE == 'full':
                pstar = p
            else:
                pstar = None
            # block cells whose pair (not a single record) violates phi
            pblock = [q for q in scope if leq(p, q) and pair_violates(cls, K, *canon(p, q))]
            if pstar is None:   # general side condition: one premise covers the block (with sigma')
                s = None
                if pblock:
                    for cand_s in Sig:
                        if all(not sat_key(canon(p, q), cand_s) or (s2 is not None and not sat_key(canon(p, q), s2))
                               for q in pblock):
                            s = cand_s; break
                    if s is None: return False, nsteps, maxar
                    prem.append(s)
            elif vio(canon(p, pstar)):
                s = need(canon(p, pstar))
                if s is None: return False, nsteps, maxar
                prem.append(s)
            else:
                s = None
            for q in pblock:   # the proof: sigma or sigma' covers every violating block pair
                inst = canon(p, q)
                if not ((s is not None and not sat_key(inst, s)) or (s2 is not None and not sat_key(inst, s2))):
                    return ('BLOCK-NOT-COVERED', p, 'phi', phi, 'q', q, 'sigma', s, 'sigma2', s2)
            if s2 is not None and s2 not in prem: prem.append(s2)
            maxar = max(maxar, len(prem)); nsteps += 1
            if check and not implies(sch, NN, prem, ([tmpl(p)], cls, K)): return 'UNSOUND-B1', p, prem
        pairs = [(p, q) for p, q in itertools.combinations([x for x in scope], 2)
                 if min(height(p), height(q)) == h]
        for p, q in pairs:                                                  # B2
            D1 = [p] + succ(q); D2 = [q] + succ(p)
            prem = [([tmpl(x) for x in D1], cls, K), ([tmpl(x) for x in D2], cls, K)]
            if vio(canon(p, q)):
                s = need(canon(p, q))
                if s is None: return False, nsteps, maxar
                prem.append(s)
            maxar = max(maxar, len(prem)); nsteps += 1
            if check and not implies(sch, NN, prem, ([tmpl(p), tmpl(q)], cls, K)): return 'UNSOUND-B2', p, q
    return True, nsteps, maxar

if __name__ == '__main__':
    rng = random.Random(8); sch = ['A', 'B', 'C']; consts = [0, 1]
    st = dict(implied=0, notimplied=0, wrong=0, steps=0, maxar=0)
    for trial in range(int(sys.argv[2]) if len(sys.argv) > 2 else 150):
        NN = set(A for A in sch if rng.random() < 0.15)
        sym = {'top': ('_', '_', 'T', 0, 1), 'null': ('_', '_', 'N', 0, 1),
               'full': ('_', '_', 'T', 'N', 0, 1)}[MODE]
        Sig = [rand_key(sch, rng, sym=sym, classes=FRAG) for _ in range(rng.randint(2, 6))]
        phi = rand_key(sch, rng, sym=sym, classes=FRAG)
        imp = implies(sch, NN, Sig, phi)
        r = run(sch, NN, Sig, phi, consts, check=True)
        if isinstance(r[0], str): print(r); break
        ok, ns, ma = r
        st['wrong'] += ok != imp; st['implied' if imp else 'notimplied'] += 1
        if ok: st['steps'] += ns; st['maxar'] = max(st['maxar'], ma)
    print(st)
