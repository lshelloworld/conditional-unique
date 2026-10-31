"""Cell lemma behind a 3-ary axiomatisation of the extended language (IN, NOT IN, IS [NOT] NULL).
Let C be the constants of Sigma and phi. A profile assigns each column null, a constant of C, or
* (a value outside C); with NOT IN (C) every profile is the scope of one template. For profiles
p, q in the scope of phi = Cphi : U(K) / Ueq(K), the canonical pair c(p, q, K) agrees on K (a
shared fresh value where both have *) and has two different fresh values where both have * off
K. Lemma: Sigma |= phi iff for every pair p, q in phi's scope either no pair with profiles p, q
violates phi or some sigma in Sigma is violated by c(p, q, K). Compared with brute force.
Usage: python cell_lemma_test.py REPO N"""
import itertools, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from cunique import brute, matches, violates, NULL
from cunique_test import rand_inst


def consts(Sigma, phi):
    cs = set()
    for temps, _, _ in list(Sigma) + [phi]:
        for r in temps:
            for e in r.values():
                if e[0] in ('in', 'notin'): cs |= e[1]
    return sorted(cs)


def cell_implies(schema, NN, Sigma, phi):
    temps, sem, K = phi
    C = consts(Sigma, phi)
    opts = [C + ['*'] + ([] if A in NN else [NULL]) for A in schema]
    star = ('fresh', 'x')
    rep = lambda p: {A: (star if v == '*' else v) for A, v in zip(schema, p)}
    profiles = [p for p in itertools.product(*opts) if any(matches(rep(p), r) for r in temps)]
    for p in profiles:
        for q in profiles:
            t1, t2, vac = {}, {}, False
            for A, a, b in zip(schema, p, q):
                if A in K:
                    if a != b or (a is NULL and sem == 'U'): vac = True; break
                    t1[A] = t2[A] = ('fresh', 'k', A) if a == '*' else a
                else:
                    t1[A] = ('fresh', 1, A) if a == '*' else a
                    t2[A] = ('fresh', 2, A) if b == '*' else b
            if vac: continue
            if not any(violates(t1, t2, s) for s in Sigma): return False
    return True


def main():
    rng = random.Random(13); n = int(sys.argv[2]); bad = imp = 0
    for _ in range(n):
        schema, NN, Sigma, phi = rand_inst(rng)
        a, b = cell_implies(schema, NN, Sigma, phi), brute(schema, NN, Sigma, phi)
        imp += b; bad += a != b
    print(f'{n} instances ({imp} implied), {bad} mismatches between the cell lemma and brute force')


if __name__ == '__main__':
    main()
