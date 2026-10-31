"""Tests for cunique.py: (1) implies() against brute() on random instances of the extended
language (IN, NOT IN / <>, IS [NOT] NULL, both null semantics, one or several templates);
(2) on the old language, against implication.implies_sat. Usage: python cunique_test.py REPO N"""
import os, random, sys
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(sys.argv[1], 'experiments', 'reasoning'))
from cunique import implies, brute
from implication import implies_sat

CONSTS = [0, 1, 2]


def rand_entry(rng, p, ext=True):
    if rng.random() >= p: return ('any',)
    k = rng.choice(['top', 'null', 'in', 'notin'] if ext else ['top', 'null', 'in'])
    if k in ('top', 'null'): return (k,)
    n = rng.randint(1, 2) if ext else 1
    return (k, frozenset(rng.sample(CONSTS, n)))


def rand_inst(rng, ext=True, multi=True):
    m = rng.randint(2, 4); schema = [f'A{j}' for j in range(m)]
    NN = {A for A in schema if rng.random() < 0.3}
    def con(p, nt):
        return ([{A: rand_entry(rng, p, ext) for A in schema} for _ in range(nt)], rng.choice(['U', 'Ueq']),
                frozenset(rng.sample(schema, rng.randint(0, min(2, m)))))
    Sigma = [con(0.35, rng.randint(1, 2) if multi else 1) for _ in range(rng.randint(1, 4))]
    phi = con(0.3, rng.randint(1, 2) if multi else 1)
    return schema, NN, Sigma, phi


def to_old(schema, temps):
    out = []
    for r in temps:
        t = {}
        for A in schema:
            e = r[A]
            t[A] = '_' if e[0] == 'any' else 'T' if e[0] == 'top' else 'N' if e[0] == 'null' else next(iter(e[1])) + 1
        out.append(t)
    return out


def main():
    rng = random.Random(5); n = int(sys.argv[2])
    bad = 0; imp = 0; mu = Counter()
    for _ in range(n):
        schema, NN, Sigma, phi = rand_inst(rng)
        st = {}
        a = implies(schema, NN, Sigma, phi, st); b = brute(schema, NN, Sigma, phi)
        imp += b; bad += a != b; mu[st.get('open', 0)] += 1
    print(f'extended language: {n} instances ({imp} implied), {bad} mismatches with brute force; '
          f'columns with >1 maximal state: {dict(sorted(mu.items()))}')
    bad = 0
    for _ in range(n):
        schema, NN, Sigma, phi = rand_inst(rng, ext=False)
        old = lambda c: (to_old(schema, c[0]), 'pos' if c[1] == 'U' else 'dom', c[2])
        bad += implies(schema, NN, Sigma, phi) != implies_sat(schema, NN, [old(s) for s in Sigma], old(phi))
    print(f'old language: {n} instances, {bad} mismatches with implies_sat')


if __name__ == '__main__':
    main()
