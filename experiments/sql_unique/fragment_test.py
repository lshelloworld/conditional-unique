"""Single-template (conjunctive) conditions, classes pos and dom. Claim: for a pos goal one
canonical pair decides implication (every free column takes the state that kills most); for a
dom goal the only choices are null/value on nullable key columns the goal's template leaves open.
Compared with implies_sat on random instances. Usage: python fragment_test.py REPO N"""
import itertools, os, random, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'experiments', 'reasoning'))
from implication import implies_sat

NULL = None


def matches(rec, tau):
    for A, s in tau.items():
        v = rec[A]
        if s == '_': continue
        if s == 'T' and v is NULL: return False
        if s == 'N' and v is not NULL: return False
        if isinstance(s, int) and v != s: return False
    return True


def violates(t1, t2, sigma):
    (tau,), cls, K = sigma
    if not (matches(t1, tau) and matches(t2, tau)): return False
    if cls == 'pos': return all(t1[A] is not NULL and t1[A] == t2[A] for A in K)
    return all(t1[A] == t2[A] for A in K)                        # dom: null equals null


def implies_fragment(schema, NN, Sigma, phi):
    (tau,), cls, K = phi
    if any(tau[A] == 'N' for A in NN): return True              # empty scope
    if cls == 'pos' and any(tau[A] == 'N' for A in K): return True
    fresh = itertools.count(1000)
    base1, base2, open_ = {}, {}, []
    for A in schema:
        s = tau[A]
        if A in K:
            if isinstance(s, int): base1[A] = base2[A] = s
            elif s == 'N': base1[A] = base2[A] = NULL
            elif s == 'T' or A in NN or cls == 'pos': base1[A] = base2[A] = next(fresh)
            else: open_.append(A)                                 # dom goal: null or value
        else:
            if isinstance(s, int): base1[A] = base2[A] = s
            elif s == 'N': base1[A] = base2[A] = NULL
            elif s == 'T' or A in NN: base1[A], base2[A] = next(fresh), next(fresh)
            else: base1[A], base2[A] = NULL, next(fresh)           # the mixed state
    for choice in itertools.product((NULL, 'v'), repeat=len(open_)):
        t1, t2 = dict(base1), dict(base2)
        for A, c in zip(open_, choice):
            t1[A] = t2[A] = NULL if c is NULL else next(fresh)
        if not any(violates(t1, t2, s) for s in Sigma): return False
    return True


def rand_tpl(schema, rng, p):
    return {A: (rng.choice(['T', 'N', 1, 2]) if rng.random() < p else '_') for A in schema}


def main():
    rng = random.Random(7); n = int(sys.argv[2]); bad = 0; stats = {'pos': [0, 0], 'dom': [0, 0]}
    for i in range(n):
        m = rng.randint(2, 6); schema = [f'A{j}' for j in range(m)]
        NN = {A for A in schema if rng.random() < 0.3}
        Sigma = [([rand_tpl(schema, rng, 0.3)], rng.choice(['pos', 'dom']), frozenset(rng.sample(schema, rng.randint(0, min(3, m)))))
                 for _ in range(rng.randint(1, 6))]
        cls = rng.choice(['pos', 'dom'])
        phi = ([rand_tpl(schema, rng, 0.25)], cls, frozenset(rng.sample(schema, rng.randint(0, min(3, m)))))
        a, b = implies_fragment(schema, NN, Sigma, phi), implies_sat(schema, NN, Sigma, phi)
        stats[cls][0] += 1; stats[cls][1] += b
        if a != b:
            bad += 1
            if bad <= 5: print('MISMATCH', schema, NN, Sigma, phi, a, b)
    print(f'{n} instances, {bad} mismatches; goals (n, implied): {stats}')


if __name__ == '__main__':
    main()
