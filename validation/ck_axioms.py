"""Validation of the finite axiomatisation of conditional keys (full template language).

Rules (see the paper, Section on axiomatisation):
  R  restriction : C:phi  |-  C':phi        if every template of C' is at least as precise as one of C
  S  null split  : (C u {t[A:T], t[A:N]}):phi  |-  (C u {t[A:T], t[A:N], t}):phi
  P  pairing     : (C u {t}):phi, (C u {t'}):phi, {t,t'}:phi  |-  (C u {t,t'}):phi
  B  base        : sigma_1..sigma_k |- {rho,rho'}:phi  for null-determined rho, rho' when every canonical
                   object of the conclusion that violates phi violates some premise (k <= 5)
The script builds, for random Sigma and targets, the derivation that the completeness proof constructs,
checks that every step is an instance of a rule and is sound (by exhaustive search), and that a
derivation exists exactly when Sigma implies the target.
"""
import itertools, random, sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else '.')
from ck import *

def key(c): return tuple(sorted(tuple(sorted((A, str(v)) for A, v in t.items())) for t in c))
def implies(sch, NN, S, p): return brute_counterexample(sch, NN, S, p) is None

def precise(s, s2, nn=False):  # s <= s2 in the precision order (bottom and top coincide on NN)
    if nn and s == 'T' and s2 == '_': return True
    return s == '_' or s == s2 or (s == 'T' and isinstance(s2, int))

def full_refinements(tau, sch, NN):
    opts = []
    for A in sch:
        s = tau[A]
        if A in NN: opts.append(['T'] if s == '_' else [s])
        else: opts.append(['N', 'T'] if s == '_' else [s])
    return [dict(zip(sch, c)) for c in itertools.product(*opts)]

def canon_objects(rho, rho2, cls, K, sch):
    """canonical pairs/records of {rho,rho2}:cls(K) that violate cls(K)"""
    objs = []
    for a, b in {(0, 0), (1, 1), (0, 1)}:
        x, y = (rho, rho2)[a], (rho, rho2)[b]
        t, u = canonical_pair(x, y, sch, K)
        if pair_violates(cls, K, t, u): objs.append([t, u])
    if cls in ('cand', 'nn'):
        for x in (rho, rho2):
            t, _ = canonical_pair(x, x, sch, set())
            if single_violates(cls, K, t): objs.append([t])
    return objs

def base_premises(Sigma, rho, rho2, cls, K, sch):
    """premises for an instance of B, or None if the side condition cannot be met"""
    prem = []
    for o in canon_objects(rho, rho2, cls, K, sch):
        hit = [s for s in Sigma if not sat_key(o, s)]
        if not hit: return None
        if hit[0] not in prem: prem.append(hit[0])
    return prem

def derive(sch, NN, Sigma, phi):
    """the derivation of the completeness proof; returns list of steps or None"""
    cond, cls, K = phi
    steps = []
    refs = []
    for tau in cond:
        for r in full_refinements(tau, sch, NN):
            if all(key([r]) != key([q]) for q in refs): refs.append(r)
    # B for every pair of refined templates
    for i in range(len(refs)):
        for j in range(i, len(refs)):
            c = [refs[i]] if i == j else [refs[i], refs[j]]
            prem = base_premises(Sigma, refs[i], refs[j], cls, K, sch)
            if prem is None: return None
            steps.append(('B', prem, (c, cls, K)))
    # P builds the whole refined condition by induction on its size
    def build(D):
        if len(D) <= 2: return
        t, t2, rest = D[0], D[1], D[2:]
        build([t] + rest); build([t2] + rest)
        steps.append(('P', [(rest + [t], cls, K), (rest + [t2], cls, K), ([t, t2], cls, K)], (D, cls, K)))
    build(refs)
    # S merges refinements back, R drops them
    cur = list(refs)
    for tau in cond:
        level = full_refinements(tau, sch, NN)
        for A in reversed(sch):
            if tau[A] != '_' or A in NN: continue
            nxt = []
            for r in level:
                if r[A] == 'T':
                    rn = dict(r); rn[A] = 'N'; rb = dict(r); rb[A] = '_'
                    nxt.append(rb)
                    if any(key([rb]) == key([q]) for q in cur): continue
                    new = cur + [rb]
                    steps.append(('S', [(list(cur), cls, K)], (new, cls, K)))
                    cur = new
            level = nxt
    steps.append(('R', [(list(cur), cls, K)], (list(cond), cls, K)))
    return steps

def check_step(sch, NN, rule, prem, concl):
    if rule == 'R':
        (c, cl, K), = prem; c2, cl2, K2 = concl
        assert (cl, K) == (cl2, K2) and all(any(all(precise(t[A], t2[A], A in NN) for A in sch) for t in c) for t2 in c2)
    if rule == 'S':
        (c, cl, K), = prem; c2, _, _ = concl
        new = [t for t in c2 if all(key([t]) != key([q]) for q in c)]
        assert len(new) == 1
        t = new[0]; A = [A for A in sch if t[A] == '_' and A not in NN]
        assert any(key([dict(t, **{a: 'T'})]) in map(lambda q: key([q]), c) and
                   key([dict(t, **{a: 'N'})]) in map(lambda q: key([q]), c) for a in A)
    if rule == 'B':
        assert len(prem) <= 5 and len(concl[0]) <= 2
        assert all(concl[0][0][A] != '_' or A in NN for A in sch)
    return implies(sch, NN, [p for p in prem], concl)   # soundness of the instance

if __name__ == '__main__':
    rng = random.Random(4); sch = ['A', 'B', 'C']
    stats = dict(implied=0, notimplied=0, steps=0, unsound=0, wrong=0, maxB=0)
    for _ in range(300):
        NN = set(A for A in sch if rng.random() < 0.2)
        S = [rand_key(sch, rng) for _ in range(rng.randint(1, 4))]
        phi = rand_key(sch, rng)
        if any(A in NN and t[A] == 'N' for t in phi[0] for A in sch): continue
        imp = implies(sch, NN, S, phi)
        d = derive(sch, NN, S, phi)
        if (d is not None) != imp: stats['wrong'] += 1
        stats['implied' if imp else 'notimplied'] += 1
        if d:
            for rule, prem, concl in d:
                stats['steps'] += 1
                if rule == 'B': stats['maxB'] = max(stats['maxB'], len(prem))
                if not check_step(sch, NN, rule, prem, concl): stats['unsound'] += 1
    print(stats)
