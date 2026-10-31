"""Implication of conditional UNIQUE constraints with the extended template language.

A template maps each column to an entry:
  ('any',)            no restriction
  ('top',)            IS NOT NULL
  ('null',)           IS NULL
  ('in', S)           = c / IN (S), S a non-empty frozenset of constants
  ('notin', S)        <> c / NOT IN (S): a value outside S (never null)
A condition is a list of templates (a disjunction); a constraint is (condition, sem, K) with
sem 'U' (NULLS DISTINCT) or 'Ueq' (NULLS NOT DISTINCT).

implies(): by the pair lemma, Sigma does not imply phi iff some pair t1, t2 (t1 matching goal
template ti, t2 matching tj) violates phi and satisfies Sigma. Whether the pair satisfies a
constraint is a monotone Boolean function of per-column features (t1 fails entry e, t2 fails
entry e -- merged into 'a record fails e' for one-template constraints -- and the records
separate on the column), so per column only states with a maximal feature
set matter. The values that matter on a column are the constants mentioned there, two fresh
values, and null. The search enumerates the product of the maximal states; mu_A is their number
on column A, and the procedure is polynomial when every mu_A is 1.
brute(): all pairs over the same finite domain, for testing."""
import itertools

NULL = None
F1, F2 = ('fresh', 1), ('fresh', 2)


def fails(v, e):
    k = e[0]
    if k == 'any': return False
    if k == 'top': return v is NULL
    if k == 'null': return v is not NULL
    if k == 'in': return v is NULL or v not in e[1]
    return v is NULL or v in e[1]                                   # notin


def matches(t, tau):
    return not any(fails(t[A], e) for A, e in tau.items())


def agree(a, b, sem):
    if a is NULL or b is NULL: return sem == 'Ueq' and a is NULL and b is NULL
    return a == b


def violates(t1, t2, con):
    temps, sem, K = con
    return (any(matches(t1, r) for r in temps) and any(matches(t2, r) for r in temps)
            and all(agree(t1[A], t2[A], sem) for A in K))


def domain(A, Sigma, phi, NN):
    cs = set()
    for temps, _, _ in list(Sigma) + [phi]:
        for r in temps:
            e = r[A]
            if e[0] in ('in', 'notin'): cs |= e[1]
    return sorted(cs, key=repr) + [F1, F2] + ([] if A in NN else [NULL])


def features(A, v1, v2, Sigma):
    f = set()
    for i, (temps, sem, K) in enumerate(Sigma):
        one = len(temps) == 1                      # one template: only 'some record fails' matters
        for j, r in enumerate(temps):
            if fails(v1, r[A]): f.add((i, j, '*' if one else 1))
            if fails(v2, r[A]): f.add((i, j, '*' if one else 2))
        if A in K and not agree(v1, v2, sem): f.add((i, 'sep'))
    return frozenset(f)


def column_states(A, ti, tj, phi, Sigma, NN):
    _, sem, K = phi
    D = domain(A, Sigma, phi, NN)
    states = {}
    for v1 in D:
        if fails(v1, ti[A]): continue
        for v2 in D:
            if fails(v2, tj[A]): continue
            if A in K and not agree(v1, v2, sem): continue
            if A in K and v1 == v2 and v1 in (F2,): continue        # one shared fresh value is enough
            f = features(A, v1, v2, Sigma)
            states.setdefault(f, (v1, v2))
    fs = list(states)
    maximal = [f for f in fs if not any(g > f for g in fs)]
    return [states[f] for f in maximal]


def implies(schema, NN, Sigma, phi, stats=None):
    temps, sem, K = phi
    for ti, tj in itertools.product(temps, repeat=2):
        cols = [column_states(A, ti, tj, phi, Sigma, NN) for A in schema]
        if stats is not None:
            stats['mu'] = max(stats.get('mu', 1), max((len(c) for c in cols), default=1))
            stats['open'] = max(stats.get('open', 0), sum(len(c) > 1 for c in cols))
        if any(not c for c in cols): continue
        for combo in itertools.product(*cols):
            t1 = {A: s[0] for A, s in zip(schema, combo)}
            t2 = {A: s[1] for A, s in zip(schema, combo)}
            if not any(violates(t1, t2, s) for s in Sigma): return False
    return True


def brute(schema, NN, Sigma, phi):
    doms = [domain(A, Sigma, phi, NN) for A in schema]
    recs = [dict(zip(schema, vs)) for vs in itertools.product(*doms)]
    for t1 in recs:
        for t2 in recs:
            if violates(t1, t2, phi) and not any(violates(t1, t2, s) for s in Sigma): return False
    return True
