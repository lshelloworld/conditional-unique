"""Finite covers of the conditional UNIQUE constraints that hold on a table r.
Gamma_A = active domain of column A; profiles are Gamma-profiles. For key part kappa and profiles
p, q (p = q allowed) a key K is *clean* if no two rows of r (different positions) with profiles in
{p, q}, both in the scope {tau_p, tau_q}, agree on K under kappa. The cell cover
  Cov(r) = { {tau_p, tau_q} : kappa(K)  |  kappa in {U, Ueq}, K a minimal clean key }
holds on r. Claim: Cov(r) implies every constraint that holds on r, with any constants.
Test: random small tables and random constraints (constants from the table and outside it):
'phi holds on r' must equal 'Cov(r) |= phi' (cunique.implies). Usage: python cover_test.py N"""
import itertools, random, sys
from cunique import implies, violates, NULL


def holds(rows, con):
    return not any(violates(rows[i], rows[j], con) for i in range(len(rows)) for j in range(len(rows)) if i != j)


def cover(schema, rows):
    G = {A: sorted({r[A] for r in rows if r[A] is not NULL}) for A in schema}
    def tau(p):
        return {A: ('in', frozenset([v])) if v not in ('*', NULL) else ('null',) if v is NULL
                else ('notin', frozenset(G[A])) for A, v in zip(schema, p)}
    profs = list(itertools.product(*[G[A] + ['*', NULL] for A in schema]))
    out = []
    for i, p in enumerate(profs):
        for q in profs[i:]:
            C = [tau(p)] + ([tau(q)] if q != p else [])
            for sem in ('U', 'Ueq'):
                clean = [frozenset(K) for k in range(len(schema) + 1) for K in itertools.combinations(schema, k)
                         if holds(rows, (C, sem, frozenset(K)))]
                for K in clean:
                    if not any(L < K for L in clean): out.append((C, sem, K))
    return out


def main():
    rng = random.Random(17); n = int(sys.argv[1]); bad = 0; held = 0; sizes = []
    for _ in range(n):
        m = rng.randint(1, 3); schema = [f'A{j}' for j in range(m)]
        dom = [0, 1, NULL]
        rows = [{A: rng.choice(dom) for A in schema} for _ in range(rng.randint(1, 5))]
        Cov = cover(schema, rows); sizes.append(len(Cov))
        for _ in range(5):
            def ent():
                k = rng.choice(['any', 'any', 'null', 'in', 'notin'])
                if k in ('any', 'null'): return (k,)
                return (k, frozenset(rng.sample([0, 1, 2, 7], rng.randint(1 if k == 'in' else 0, 2))))
            phi = ([{A: ent() for A in schema} for _ in range(rng.randint(1, 2))], rng.choice(['U', 'Ueq']),
                   frozenset(rng.sample(schema, rng.randint(0, m))))
            h = holds(rows, phi); held += h
            bad += h != implies(schema, set(), Cov, phi)
    print(f'{n} tables x 5 constraints ({held} hold): {bad} mismatches; cover sizes median {sorted(sizes)[len(sizes)//2]}, max {max(sizes)}')


if __name__ == '__main__':
    main()
