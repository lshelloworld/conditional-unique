"""Complexity of the extended language for nulls-distinct goals over one-template premises.
(a) Sufficient condition for one maximal state per column (polynomial case): on every column on
which the goal forces both records to carry a value (key column, NOT NULL, or a goal entry
top / in / notin), no premise has a notin entry and the goal has no IN-list of two or more
constants. Checked: under the condition, no column ever has two maximal states.
(b) Hardness: CNF -> (i) <> entries in premises on key columns; (ii) a two-constant IN-list in
the goal on key columns with = entries in premises. Both compared with a SAT solver.
Usage: python cunique_complexity.py REPO N"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(sys.argv[1], 'experiments', 'reasoning'))
from cunique import implies
from cunique_test import rand_entry
from pysat.solvers import Cadical153


def forced(A, NN, K, tau):
    return A in K or A in NN or tau[A][0] in ('top', 'in', 'notin')


def condition(schema, NN, Sigma, phi):
    (tau,), _, K = phi
    for A in schema:
        if not forced(A, NN, K, tau): continue
        if any(r[A][0] == 'notin' for temps, _, _ in Sigma for r in temps): return False
        if tau[A][0] == 'in' and len(tau[A][1]) > 1: return False
    return True


def main():
    rng = random.Random(9); n = int(sys.argv[2]); held = viol = 0
    for _ in range(n):
        m = rng.randint(2, 5); schema = [f'A{j}' for j in range(m)]
        NN = {A for A in schema if rng.random() < 0.3}
        Sigma = [([{A: rand_entry(rng, 0.35) for A in schema}], rng.choice(['U', 'Ueq']),
                  frozenset(rng.sample(schema, rng.randint(0, min(2, m))))) for _ in range(rng.randint(1, 5))]
        phi = ([{A: rand_entry(rng, 0.3) for A in schema}], 'U', frozenset(rng.sample(schema, rng.randint(0, min(2, m)))))
        if not condition(schema, NN, Sigma, phi): continue
        held += 1; st = {}
        implies(schema, NN, Sigma, phi, st)
        viol += st.get('open', 0) > 0
    print(f'(a) {held} instances meet the condition; {viol} have a column with two maximal states')
    for variant in ('notin-premises', 'in-goal'):
        ok = 0
        for _ in range(200):
            nv = rng.randint(3, 7)
            cls = [[v + 1 if rng.random() < .5 else -(v + 1) for v in rng.sample(range(nv), 3)] for _ in range(rng.randint(2, 4 * nv))]
            schema = [f'A{i}' for i in range(nv)] + ['B']; NN = set(schema)
            Sigma = []
            for c in cls:
                r = {A: ('any',) for A in schema}
                for l in c:     # literal true kills the clause constraint
                    A = f'A{abs(l) - 1}'
                    if variant == 'notin-premises': r[A] = ('notin', frozenset([1 if l > 0 else 0]))
                    else: r[A] = ('in', frozenset([0 if l > 0 else 1]))
                Sigma.append(([r], 'U', frozenset(['B'])))
            goal = {A: ('any',) for A in schema}
            if variant == 'in-goal':
                for i in range(nv): goal[f'A{i}'] = ('in', frozenset([0, 1]))
            phi = ([goal], 'U', frozenset(schema))
            s = Cadical153(bootstrap_with=cls); sat = s.solve(); s.delete()
            ok += implies(schema, NN, Sigma, phi) == (not sat)
        print(f'(b) {variant}: implied iff CNF unsatisfiable on {ok} of 200')


if __name__ == '__main__':
    main()
