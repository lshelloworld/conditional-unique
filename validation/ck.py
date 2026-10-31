"""Brute-force validation of the conditional-key theory (prototype for the ICDE draft).

Template symbols: '_' = no requirement (bottom), 'T' = not null (top), 'N' = null, int = constant.
Tuples: dict attr -> value, None is null. Fresh values are ints >= 100.
"""
import itertools, random

CLASSES = ['pos', 'dom', 'part', 'cert', 'cand', 'nn']

def qualifies(t, tau):
    for A, s in tau.items():
        v = t[A]
        if s == '_':
            continue
        if s == 'T' and v is None: return False
        if s == 'N' and v is not None: return False
        if isinstance(s, int) and v != s: return False
    return True

def in_scope(t, cond):
    return any(qualifies(t, tau) for tau in cond)

def pair_violates(cls, K, t, u):
    """Does the pair {t,u} (distinct records) violate the unconditional key cls(K)?"""
    if cls == 'pos':
        return all(t[A] is not None and t[A] == u[A] for A in K)
    if cls in ('dom', 'cand'):
        return all(t[A] == u[A] for A in K)
    if cls == 'part':
        sub = lambda a, b: all(a[A] is None or a[A] == b[A] for A in K)
        return sub(t, u) or sub(u, t)
    if cls == 'cert':
        return all(t[A] is None or u[A] is None or t[A] == u[A] for A in K)
    if cls == 'nn':
        return False
    raise ValueError(cls)

def single_violates(cls, K, t):
    return cls in ('cand', 'nn') and any(t[A] is None for A in K)

def sat_key(inst, key):
    cond, cls, K = key
    scope = [t for t in inst if in_scope(t, cond)]
    for t in scope:
        if single_violates(cls, K, t): return False
    for i in range(len(scope)):
        for j in range(i + 1, len(scope)):
            if pair_violates(cls, K, scope[i], scope[j]): return False
    return True

def sat(inst, Sigma):
    return all(sat_key(inst, k) for k in Sigma)

# ---------------------------------------------------------------- brute force
def consts(keys, A):
    cs = set()
    for cond, _, _ in keys:
        for tau in cond:
            if isinstance(tau[A], int): cs.add(tau[A])
    return sorted(cs)

def brute_counterexample(schema, NN, Sigma, phi):
    keys = list(Sigma) + [phi]
    vals = {}
    for A in schema:
        vs = ([] if A in NN else [None]) + consts(keys, A) + [100, 101]
        vals[A] = vs
    rows = [dict(zip(schema, combo)) for combo in itertools.product(*[vals[A] for A in schema])]
    for t in rows:
        if sat([t], Sigma) and not sat_key([t], phi):
            return [t]
    for i, t in enumerate(rows):
        for u in rows[i:]:
            inst = [t, u]
            if not sat_key(inst, phi) and sat(inst, Sigma):
                return inst
    return None

# ---------------------------------------------------------------- canonical algorithm
def relevant(schema, Sigma, K):
    rel = set(K)
    for cond, _, _ in Sigma:
        for tau in cond:
            for A in schema:
                if tau[A] in ('T', 'N'): rel.add(A)
    return rel

def refinements(tau, schema, NN, rel):
    """Null-determined refinements of tau: each '_' becomes 'N' or 'T' (only on relevant attrs)."""
    opts = []
    for A in schema:
        s = tau[A]
        if A in NN:
            if s == 'N': return  # empty scope
            opts.append(['T'] if s == '_' else [s])
        elif s == '_':
            opts.append(['N', 'T'] if A in rel else ['T'])
        else:
            opts.append([s])
    for combo in itertools.product(*opts):
        yield dict(zip(schema, combo))

def canonical_pair(rho, rho2, schema, K):
    t, u = {}, {}
    fresh = iter(range(200, 10**6))
    for A in schema:
        x, y = rho[A], rho2[A]
        tn, un = x == 'N', y == 'N'
        if tn: t[A] = None
        if un: u[A] = None
        if tn and un: continue
        if tn: u[A] = y if isinstance(y, int) else next(fresh); continue
        if un: t[A] = x if isinstance(x, int) else next(fresh); continue
        if A in K:  # make equal if possible
            if isinstance(x, int) and isinstance(y, int):
                t[A], u[A] = x, y
            elif isinstance(x, int): t[A] = u[A] = x
            elif isinstance(y, int): t[A] = u[A] = y
            else: t[A] = u[A] = next(fresh)
        else:       # make distinct if possible
            t[A] = x if isinstance(x, int) else next(fresh)
            u[A] = y if isinstance(y, int) else next(fresh)
    return t, u

def canonical_counterexample(schema, NN, Sigma, phi):
    cond, cls, K = phi
    rel = relevant(schema, Sigma, K)
    refs = [list(refinements(tau, schema, NN, rel)) for tau in cond]
    # single-tuple counterexamples
    if cls in ('cand', 'nn'):
        for R in refs:
            for rho in R:
                t, _ = canonical_pair(rho, rho, schema, set())
                if single_violates(cls, K, t) and sat([t], Sigma):
                    return [t]
    for i in range(len(cond)):
        for j in range(i, len(cond)):
            for rho in refs[i]:
                for rho2 in refs[j]:
                    t, u = canonical_pair(rho, rho2, schema, K)
                    inst = [t, u]
                    if pair_violates(cls, K, t, u) and sat(inst, Sigma):
                        return inst
    return None

# ---------------------------------------------------------------- random tests
def rand_template(schema, rng, sym=('_', '_', 'T', 'N', 0, 1)):
    return {A: rng.choice(sym) for A in schema}

def rand_key(schema, rng, classes=CLASSES, sym=('_', '_', 'T', 'N', 0, 1), maxc=2):
    cond = [rand_template(schema, rng, sym) for _ in range(rng.randint(1, maxc))]
    K = frozenset(A for A in schema if rng.random() < 0.5)
    return (cond, rng.choice(classes), K)

def test_implication(trials=3000, seed=1, n=3, **kw):
    rng = random.Random(seed)
    schema = [chr(ord('A') + i) for i in range(n)]
    bad = 0
    for _ in range(trials):
        NN = set(A for A in schema if rng.random() < 0.2)
        Sigma = [rand_key(schema, rng, **kw) for _ in range(rng.randint(1, 4))]
        phi = rand_key(schema, rng, **kw)
        b = brute_counterexample(schema, NN, Sigma, phi) is None
        c = canonical_counterexample(schema, NN, Sigma, phi) is None
        if b != c:
            bad += 1
            if bad <= 3: print('MISMATCH', NN, Sigma, phi, b, c)
    return bad

if __name__ == '__main__':
    print('implication mismatches:', test_implication())
    print('implication mismatches (4 attrs):', test_implication(trials=400, seed=7, n=4))
