import itertools, random, sys
sys.path.insert(0, sys.argv[1])
from ck import *

def implies(schema, NN, Sigma, phi):
    return brute_counterexample(schema, NN, Sigma, phi) is None

def equiv(schema, NN, S1, S2):
    return all(implies(schema, NN, S1, p) for p in S2) and all(implies(schema, NN, S2, p) for p in S1)

rng = random.Random(3)
schema = ['A', 'B', 'C']
ALL = {A: '_' for A in schema}

# 0. how often is implication true in the random test distribution?
cnt = [0, 0]
for _ in range(1500):
    NN = set(A for A in schema if rng.random() < 0.2)
    S = [rand_key(schema, rng) for _ in range(rng.randint(1, 4))]
    p = rand_key(schema, rng)
    cnt[implies(schema, NN, S, p)] += 1
print('random distribution: implied', cnt[1], 'not implied', cnt[0])

# 1. domain key == family of single-template conditional possible keys (filtered unique indexes)
ok = True
for NN in [set(), {'A'}]:
    for K in [frozenset('A'), frozenset('AB'), frozenset('ABC')]:
        NK = [A for A in K if A not in NN]
        fam = []
        for r in range(len(NK) + 1):
            for P in itertools.combinations(NK, r):
                tau = dict(ALL); tau.update({A: 'N' for A in P}); tau.update({A: 'T' for A in K - set(P)})
                fam.append(([tau], 'pos', frozenset(K - set(P))))
        ok &= equiv(schema, NN, [([ALL], 'dom', K)], fam)
print('domain = filtered possible family:', ok)

# 2. hierarchy within a condition (soundness) and collapse rules
order = ['cand', 'cert', 'part', 'dom', 'pos']
viol = 0
for _ in range(600):
    NN = set(A for A in schema if rng.random() < 0.2)
    cond = [rand_template(schema, rng) for _ in range(rng.randint(1, 2))]
    K = frozenset(A for A in schema if rng.random() < 0.6)
    for a, b in zip(order, order[1:]):
        if not implies(schema, NN, [(cond, a, K)], (cond, b, K)): viol += 1
    # C1 total collapse
    if all(A in NN or tau[A] == 'T' or isinstance(tau[A], int) for tau in cond for A in K):
        for c in order:
            if not equiv(schema, NN, [(cond, 'cert', K)], [(cond, c, K)]): viol += 1; print('C1', cond, K, c)
    # C2 one-open collapse
    opn = [A for A in K if A not in NN and any(tau[A] in ('_', 'N') for tau in cond)]
    if len(opn) <= 1:
        if not equiv(schema, NN, [(cond, 'part', K)], [(cond, 'cert', K)]): viol += 1; print('C2', cond, K)
    # C3 null-fixed attribute
    for A in K:
        if A not in NN and all(tau[A] == 'N' for tau in cond):
            if not implies(schema, NN, [], (cond, 'pos', K)): viol += 1; print('C3pos')
            for c in ['dom', 'part', 'cert']:
                if not equiv(schema, NN, [(cond, c, K)], [(cond, c, K - {A})]): viol += 1; print('C3', c)
    # C4 constant-fixed attribute
    for A in K:
        vals = {tau[A] for tau in cond}
        if len(vals) == 1 and isinstance(next(iter(vals)), int):
            for c in order:
                if not equiv(schema, NN, [(cond, c, K)], [(cond, c, K - {A})]): viol += 1; print('C4', c)
    # C5 distinct pairing
    if len(cond) == 2 and any(isinstance(cond[0][A], int) and isinstance(cond[1][A], int) and cond[0][A] != cond[1][A] for A in K):
        for c in order:
            if not equiv(schema, NN, [(cond, c, K)], [([cond[0]], c, K), ([cond[1]], c, K)]): viol += 1; print('C5', c)
    # C9 null split of a bottom
    for A in schema:
        if cond[0][A] == '_' and A not in NN:
            t1 = dict(cond[0]); t1[A] = 'T'; t2 = dict(cond[0]); t2[A] = 'N'
            for c in order:
                if not equiv(schema, NN, [(cond, c, K)], [([t1, t2] + cond[1:], c, K)]): viol += 1; print('C9', c)
            break
print('hierarchy/collapse violations:', viol)

# 3. strictness of the class hierarchy under a condition with two open key attributes
cond = [{'A': '_', 'B': '_', 'C': 0}]
K = frozenset('AB')
print('strict:', [not implies(schema, set(), [(cond, b, K)], (cond, a, K)) for a, b in zip(order, order[1:])])

# 4. multi-template scope is strictly more expressive than single-pattern tableaux (example)
t0 = {'A': 0, 'B': '_', 'C': '_'}; t1 = {'A': 1, 'B': '_', 'C': '_'}
multi = ([t0, t1], 'pos', frozenset('B'))
print('cross pairs matter:', not implies(schema, set(), [([t0], 'pos', frozenset('B')), ([t1], 'pos', frozenset('B'))], multi))

# 5. PTIME fragment: null-free conditions, possible-key premises; greedy canonical pairs
def greedy(schema, NN, Sigma, phi):
    cond, cls, K = phi
    if cls in ('cand', 'nn'):
        for tau in cond:
            if any(A not in NN and tau[A] in ('_', 'N') for A in K) and all(not (A in NN and tau[A] == 'N') for A in schema):
                return False  # single tuple with null in K; premises are possible keys
    def choices(x, y, A):
        # candidate (t null?, u null?) patterns on attribute A, maximal nulls subject to target class
        cn = lambda s: (s in ('_', 'N')) and A not in NN   # may be null
        cv = lambda s: s != 'N'                              # may be non-null
        pats = [(a, b) for a in (True, False) for b in (True, False)
                if (cn(x) if a else cv(x)) and (cn(y) if b else cv(y))]
        return pats
    for tau in cond:
        for tau2 in cond:
            if any(A in NN and (tau[A] == 'N' or tau2[A] == 'N') for A in schema): continue
            variants = ['any'] if cls != 'part' else ['novn', 'nonv']
            for var in variants:
                rho, rho2, okv = {}, {}, True
                for A in schema:
                    pats = choices(tau[A], tau2[A], A)
                    if A in K:
                        if cls == 'pos': pats = [p for p in pats if p == (False, False)]
                        if cls in ('dom', 'cand'): pats = [p for p in pats if p[0] == p[1]]
                        if var == 'novn': pats = [p for p in pats if p != (False, True)]
                        if var == 'nonv': pats = [p for p in pats if p != (True, False)]
                    if not pats: okv = False; break
                    p = max(pats, key=lambda p: (p[0] + p[1], p[0]))  # most nulls
                    rho[A] = 'N' if p[0] else (tau[A] if isinstance(tau[A], int) else 'T')
                    rho2[A] = 'N' if p[1] else (tau2[A] if isinstance(tau2[A], int) else 'T')
                if not okv: continue
                t, u = canonical_pair(rho, rho2, schema, K)
                if pair_violates(cls, K, t, u) and sat([t, u], Sigma):
                    return False
    return True

bad = 0
for _ in range(1500):
    NN = set(A for A in schema if rng.random() < 0.2)
    S = [rand_key(schema, rng, classes=['pos'], sym=('_', '_', 'T', 0, 1)) for _ in range(rng.randint(1, 4))]
    p = rand_key(schema, rng, classes=['pos', 'dom', 'part', 'cert', 'cand'])
    if greedy(schema, NN, S, p) != implies(schema, NN, S, p): bad += 1
print('PTIME fragment mismatches:', bad)

# 6. hardness reductions on random 3-CNFs over few variables
def cnf_sat(n, cls_):
    return any(all(any((lit > 0) == v[abs(lit) - 1] for lit in c) for c in cls_)
               for v in itertools.product([False, True], repeat=n))

def red_cert(n, clauses):  # null-free single-template certain keys, target {bottom}:pos(Z)
    sch = ['Z'] + ['X%d' % i for i in range(1, n + 1)]
    S = []
    for c in clauses:
        tau = {A: '_' for A in sch}
        for lit in c:
            if lit < 0: tau['X%d' % -lit] = 'T'
        L = frozenset(['Z'] + ['X%d' % lit for lit in c if lit > 0])
        S.append(([tau], 'cert', L))
    return sch, {'Z'}, S, ([{A: '_' for A in sch}], 'pos', frozenset(['Z']))

def red_dom(n, clauses):   # single-template domain keys using the null marker, target {bottom}:dom(R)
    sch = ['X%d' % i for i in range(1, n + 1)]
    S = []
    for c in clauses:
        tau = {A: '_' for A in sch}
        for lit in c:
            tau['X%d' % abs(lit)] = 'N' if lit > 0 else 'T'
        S.append(([tau], 'dom', frozenset(sch)))
    return sch, set(), S, ([{A: '_' for A in sch}], 'dom', frozenset(sch))

bad = 0
for _ in range(60):
    n = 3
    clauses = [tuple(rng.choice([1, -1]) * v for v in rng.sample(range(1, n + 1), rng.randint(1, 3)))
               for _ in range(rng.randint(2, 7))]
    s = cnf_sat(n, clauses)
    for red in (red_cert, red_dom):
        sch, NN, S, p = red(n, clauses)
        if canonical_counterexample(sch, NN, S, p) is None == s: pass
        if (canonical_counterexample(sch, NN, S, p) is None) != (not s): bad += 1
print('reduction mismatches:', bad)
