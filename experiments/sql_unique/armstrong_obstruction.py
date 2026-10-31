"""Armstrong tables need not exist. Two witnesses, each a set Sigma and two constraints phi1,
phi2 that Sigma does not imply, such that no table satisfying Sigma violates both:
(1) with constants: at most one row with A='a' and at most one with A='d';
(2) with nulls only: at most one row with A IS NULL and at most one with B IS NULL.
Checks non-implication with cunique.implies and brute force, and searches all tables of up to
four rows over a small domain for one satisfying Sigma and violating phi1 and phi2."""
import itertools, sys
from cunique import implies, brute, violates

ANY = ('any',)


def sat(rows, con):
    return not any(violates(rows[i], rows[j], con) for i in range(len(rows)) for j in range(len(rows)) if i != j)


def search(schema, dom, Sigma, phis, maxrows=4):
    recs = [dict(zip(schema, v)) for v in itertools.product(*[dom[A] for A in schema])]
    for n in range(2, maxrows + 1):
        for rows in itertools.combinations_with_replacement(recs, n):
            if all(sat(rows, s) for s in Sigma) and not any(sat(rows, f) for f in phis):
                return rows
    return None


def T(schema, **kw): return {A: kw.get(A, ANY) for A in schema}


def main():
    I = lambda *c: ('in', frozenset(c))
    S = ['A', 'B']
    Sigma = [([T(S, A=I('a'))], 'U', frozenset()), ([T(S, A=I('d'))], 'U', frozenset())]
    phi1 = ([T(S, A=I('a'), B=I('b')), T(S, A=I('d'))], 'U', frozenset())
    phi2 = ([T(S, A=I('a'), B=I('c')), T(S, A=I('d'))], 'U', frozenset())
    report('constants', S, Sigma, phi1, phi2, {'A': ['a', 'd', 'x'], 'B': ['b', 'c', 'y']})
    S = ['A', 'B', 'C']
    N, V = ('null',), ('notin', frozenset())
    Sigma = [([T(S, A=N)], 'U', frozenset()), ([T(S, B=N)], 'U', frozenset())]
    phi1 = ([T(S, A=N, C=N), T(S, B=N)], 'U', frozenset())
    phi2 = ([T(S, A=N, C=V), T(S, B=N)], 'U', frozenset())
    report('nulls only', S, Sigma, phi1, phi2, {A: [None, 1] for A in S})


def report(name, S, Sigma, phi1, phi2, dom):
    nn = set()
    print(f'{name}: Sigma implies phi1: {implies(S, nn, Sigma, phi1)} (brute {brute(S, nn, Sigma, phi1)}), '
          f'phi2: {implies(S, nn, Sigma, phi2)} (brute {brute(S, nn, Sigma, phi2)}); '
          f'table satisfying Sigma and violating both (<= 4 rows): {search(S, dom, Sigma, [phi1, phi2])}')


if __name__ == '__main__':
    main()
