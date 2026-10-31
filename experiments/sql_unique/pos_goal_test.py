"""Nulls-distinct goal with an arbitrary (multi-template) condition over premises with one template
each: implication is decided by one canonical pair per pair of goal templates (t1 matches tau_i,
t2 matches tau_j). Per column: on the key, a shared value (the constant if a template fixes
one); off the key, one record null and the other not if the templates allow it, else two
different values, else what the templates force. Compared with implies_sat. Usage: REPO N"""
import itertools, os, random, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'experiments', 'reasoning'))
from implication import implies_sat
from fragment_test import violates, rand_tpl

NULL = None


def opts(s, A, NN):
    if s == 'N': return [NULL] if A not in NN else []
    if isinstance(s, int): return [s]
    if s == 'T' or A in NN: return ['v']
    return [NULL, 'v']


def implies_pos_goal(schema, NN, Sigma, phi):
    temps, cls, K = phi
    assert cls == 'pos'
    fresh = itertools.count(1000)
    for ti, tj in itertools.product(temps, repeat=2):
        t1, t2, ok = {}, {}, True
        for A in schema:
            o1, o2 = opts(ti[A], A, NN), opts(tj[A], A, NN)
            if not o1 or not o2: ok = False; break
            if A in K:
                o1, o2 = [x for x in o1 if x is not NULL], [x for x in o2 if x is not NULL]
                c = {x for x in o1 + o2 if isinstance(x, int)}
                if not o1 or not o2 or len(c) > 1 or (c and (c.isdisjoint(o1) and 'v' not in o1 or c.isdisjoint(o2) and 'v' not in o2)):
                    ok = False; break
                t1[A] = t2[A] = c.pop() if c else next(fresh)
            elif NULL in o1 and any(x is not NULL for x in o2):
                t1[A] = NULL; x = [x for x in o2 if x is not NULL][0]; t2[A] = next(fresh) if x == 'v' else x
            elif NULL in o2 and any(x is not NULL for x in o1):
                t2[A] = NULL; x = [x for x in o1 if x is not NULL][0]; t1[A] = next(fresh) if x == 'v' else x
            else:
                x1, x2 = o1[-1], o2[-1]
                t1[A] = next(fresh) if x1 == 'v' else x1
                t2[A] = next(fresh) if x2 == 'v' else x2
        if ok and not any(violates(t1, t2, s) for s in Sigma): return False
    return True


def main():
    rng = random.Random(11); n = int(sys.argv[2]); bad = imp = 0
    for _ in range(n):
        m = rng.randint(2, 6); schema = [f'A{j}' for j in range(m)]
        NN = {A for A in schema if rng.random() < 0.3}
        Sigma = [([rand_tpl(schema, rng, 0.3)], rng.choice(['pos', 'dom']), frozenset(rng.sample(schema, rng.randint(0, min(3, m)))))
                 for _ in range(rng.randint(1, 6))]
        phi = ([rand_tpl(schema, rng, 0.25) for _ in range(rng.randint(1, 3))], 'pos', frozenset(rng.sample(schema, rng.randint(0, min(3, m)))))
        a, b = implies_pos_goal(schema, NN, Sigma, phi), implies_sat(schema, NN, Sigma, phi)
        imp += b; bad += a != b
    print(f'{n} instances ({imp} implied), {bad} mismatches')


if __name__ == '__main__':
    main()
