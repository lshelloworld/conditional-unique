"""Brute-force check of the E7 detectors on small random tables."""
import itertools, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', '..', 'validation'))
from run_e7 import violations, cfd_violations
import ck
rng = random.Random(5); bad = n = 0
cols = ['A', 'B', 'C', 'D']
for trial in range(400):
    rows = [tuple(rng.choice([None, 1, 2]) for _ in cols) for _ in range(rng.randint(2, 12))]
    K = rng.sample(cols, rng.randint(1, 3))
    scope = [rng.random() < .7 for _ in rows]
    recs = [dict(zip(cols, r)) for r in rows]
    for cls in ['pos', 'dom', 'part', 'cert', 'cand']:
        want = set()
        for i, j in itertools.combinations(range(len(rows)), 2):
            if scope[i] and scope[j] and ck.pair_violates('dom' if cls == 'cand' else cls, frozenset(K), recs[i], recs[j]):
                want |= {i, j}
        if cls == 'cand':
            want |= {i for i in range(len(rows)) if scope[i] and any(recs[i][c] is None for c in K)}
        n += 1
        if violations(rows, cols, K, cls, scope) != want: bad += 1
    # CFD: groups on K (nulls grouped) with conflicting non-null values elsewhere
    want = set()
    for i, j in itertools.combinations(range(len(rows)), 2):
        if all(recs[i][c] == recs[j][c] for c in K):
            others = [c for c in cols if c not in K]
            grp = [k for k in range(len(rows)) if all(recs[k][c] == recs[i][c] for c in K)]
            if any(len({recs[k][c] for k in grp if recs[k][c] is not None}) > 1 for c in others):
                want |= set(grp)
    n += 1
    if cfd_violations(rows, cols, K, []) != want: bad += 1
    # CFD with a condition: constant atoms join the left-hand side with their pattern value
    # (only matching records are compared); presence/absence atoms are not expressible and ignored
    rest = [c for c in cols if c not in K]
    cond = [(rng.choice(['const', 'const', 'top', 'null']), c, rng.choice([1, 2]))
            for c in rng.sample(rest, rng.randint(1, min(2, len(rest))))] if rest else []
    pat = {c: v for kind, c, v in cond if kind == 'const'}
    lhs = K + list(pat)
    match = [k for k in range(len(rows)) if all(recs[k][c] == v for c, v in pat.items())]
    want = set()
    for i in match:
        grp = [k for k in match if all(recs[k][c] == recs[i][c] for c in lhs)]
        if len(grp) > 1 and any(len({recs[k][c] for k in grp if recs[k][c] is not None}) > 1
                                for c in cols if c not in lhs):
            want |= set(grp)
    n += 1
    if cfd_violations(rows, cols, K, cond) != want: bad += 1
print('checked', n, 'detector runs; mismatches', bad)
