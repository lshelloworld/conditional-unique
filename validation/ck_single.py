import sys, random, itertools
sys.path.insert(0, sys.argv[1])
from ck import *
def implies(schema, NN, S, p): return brute_counterexample(schema, NN, S, p) is None

def types(x, y, nn):
    """realizable column types for t |= x, u |= y"""
    def vals(s):
        if s == 'N': return {'null'}
        if s == 'T': return {'v'}
        if s == '_': return {'v'} if nn else {'null', 'v'}
        return {('c', s)}
    T = set()
    for a in vals(x):
        for b in vals(y):
            if a == 'null' and b == 'null': T.add('bn')
            elif a == 'null': T.add('nv')
            elif b == 'null': T.add('vn')
            elif a == 'v' or b == 'v': T |= {'eq', 'dd'}
            else: T.add('eq' if a == b else 'dd')
    return T

def sat_types(cls, vec):
    if cls == 'pos': return any(x != 'eq' for x in vec)
    if cls in ('dom', 'cand'): return any(x in ('nv', 'vn', 'dd') for x in vec)
    if cls == 'part': return any(x in ('vn', 'dd') for x in vec) and any(x in ('nv', 'dd') for x in vec)
    if cls == 'cert': return any(x == 'dd' for x in vec)

def contained(c2, c1, schema, NN):  # scope(c2) subset scope(c1), brute force over generic tuples
    vals = {A: ([] if A in NN else [None]) + sorted({t[A] for t in c1 + c2 if isinstance(t[A], int)}) + [100] for A in schema}
    for combo in itertools.product(*[vals[A] for A in schema]):
        t = dict(zip(schema, combo))
        if in_scope(t, c2) and not in_scope(t, c1): return False
    return True

def restrictK(c, K, NN):
    out = []
    for tau in c:
        if any(tau[A] == 'N' for A in K): continue
        t = dict(tau); t.update({A: 'T' for A in K if tau[A] == '_'}); out.append(t)
    return out

def same_cond(c, k1, k2, K, schema, NN):
    """c:k1(K) |= c:k2(K) via realizable types"""
    if k2 in ('cand', 'nn'):
        # single-tuple part: some template allows null on K
        if any(tau[A] in ('_', 'N') and A not in NN for tau in c for A in K) and k1 not in ('cand', 'nn'):
            # unless no tuple qualifies (empty template)
            if any(not any(tau[A] == 'N' and A in NN for A in schema) for tau in c if any(tau[A] in ('_','N') and A not in NN for A in K)):
                return False
    if k2 == 'nn': return True
    for x in c:
        if any(x[A] == 'N' and A in NN for A in schema): continue
        for y in c:
            if any(y[A] == 'N' and A in NN for A in schema): continue
            Ts = [types(x[A], y[A], A in NN) for A in sorted(K)]
            for vec in itertools.product(*Ts):
                if k1 in ('cand',) and any(v in ('bn','nv','vn') for v in vec): continue
                s1 = sat_types('dom' if k1 == 'cand' else k1, vec) if k1 != 'nn' else True
                if s1 and not sat_types('dom' if k2 == 'cand' else k2, vec): return False
    return True

def single(c1, k1, c2, k2, K, schema, NN):
    if k2 == 'pos':
        if not contained(restrictK(c2, K, NN), c1, schema, NN): return False
    else:
        if not contained(c2, c1, schema, NN): return False
    return same_cond(c2, k1, k2, K, schema, NN)

rng = random.Random(5); schema = ['A', 'B', 'C']; bad = 0
for _ in range(2500):
    NN = set(A for A in schema if rng.random() < 0.2)
    K = frozenset(A for A in schema if rng.random() < 0.6)
    c1 = [rand_template(schema, rng) for _ in range(rng.randint(1, 2))]
    c2 = [rand_template(schema, rng) for _ in range(rng.randint(1, 2))] if rng.random() < .5 else [dict(t) for t in c1]
    k1, k2 = rng.choice(['pos','dom','part','cert','cand']), rng.choice(['pos','dom','part','cert','cand'])
    a = implies(schema, NN, [(c1, k1, K)], (c2, k2, K)); b = single(c1, k1, c2, k2, K, schema, NN)
    if a != b:
        bad += 1
        if bad < 4: print('MISMATCH', NN, K, c1, k1, c2, k2, a, b)
print('single-premise mismatches:', bad)
