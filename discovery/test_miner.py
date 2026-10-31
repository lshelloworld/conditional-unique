"""Check the miner's condition search against brute force on small random tables.

For every key K (|K| <= 2), class C and template of at most two atoms, the template is valid
(the conditional key holds on the data) iff the miner reports it (exactly), and approximate
templates carry the right number of violating pairs. Also checks compatible_pairs and classify
against a direct pair scan."""
import itertools, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ckminer import *

def brute_holds(T, K, C, atoms):
    sch = T.cols
    recs = [dict(zip(sch, r)) for r in T.rows]
    temps = to_ck(T, [atoms], C, K)[0]
    q = lambda t, tau: all(s == '_' or (s == 'T' and t[c] is not None) or (s == 'N' and t[c] is None)
                           or (s not in ('_', 'T', 'N') and t[c] == s) for c, s in tau.items())
    scope = [t for t in recs if any(q(t, tau) for tau in temps)]
    bad = 0
    for x, y in itertools.combinations(scope, 2):
        if ck.pair_violates('cert' if C == 'cand' else C, frozenset(K), x, y): bad += 1
    return bad

P = dict(kmax=2, minsup_rows=2, minsup_frac=0.0, max_const_card=4, max_const_card_narrow=4, narrow_cols=10, max_key_null=1.0,
         pair_cap=10**6, max_involved=1.0, approx_pairs=2, time_budget=60)
rng = random.Random(3); errors = checked = 0
for trial in range(60):
    n = rng.randint(8, 25); cols = ['A', 'B', 'C', 'D']
    rows = [tuple(rng.choice([None, 1, 2, 3]) if c != 'D' else rng.choice([1, 2]) for c in cols) for _ in range(n)]
    T = Table('t', cols, rows, P)
    for K in [K for r in (1, 2) for K in itertools.combinations(cols, r)]:
        pairs = compatible_pairs(T, K, P['pair_cap'])
        direct = [(i, j) for i, j in itertools.combinations(range(n), 2)
                  if all(rows[i][cols.index(c)] is None or rows[j][cols.index(c)] is None
                         or rows[i][cols.index(c)] == rows[j][cols.index(c)] for c in K)]
        if sorted(pairs) != direct: errors += 1; print('pairs differ', K)
        labels = classify(T, K, pairs)
        for C in ['cert', 'part', 'dom', 'pos']:
            exact, approx, vio = condition_search(T, K, C, pairs, labels)
            got = {tuple(sorted(a)) for a, _ in exact}
            gotapprox = {tuple(sorted(a)): v for a, _, v in approx}
            Kset = set(K)
            usable = [a for a, (c, kind, *_) in enumerate(T.atoms) if not (c in Kset and kind in ('const', 'null'))]
            sup = lambda b: bin(b).count('1')
            for a in usable:
                if sup(T.abits[a]) < T.minsup: continue
                b = brute_holds(T, K, C, (a,)); checked += 1
                if (b == 0) != ((a,) in got): errors += 1; print('single', K, C, T.atoms[a], b)
                if 0 < b <= 2 and gotapprox.get((a,)) != b: errors += 1; print('approx', K, C, T.atoms[a], b, gotapprox.get((a,)))
            valid1 = {a for a in usable if (a,) in got}
            for a, b_ in itertools.combinations(usable, 2):
                if a in valid1 or b_ in valid1 or not consistent(T, (a, b_)): continue
                if sup(T.abits[a] & T.abits[b_]) < T.minsup: continue
                b = brute_holds(T, K, C, (a, b_)); checked += 1
                if (b == 0) != ((a, b_) in got): errors += 1; print('pair', K, C, b)
print('checked', checked, 'templates; errors', errors)
