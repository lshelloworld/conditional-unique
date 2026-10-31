"""Recompute the E6b implication decisions with compatibility pruning (implication.restrict):
same catalogs and queries as results_e6b.json, no database. Checks that every decision is
unchanged (pruning is exact) and records b and the time of the hybrid with and without pruning.
The original run was resumed at ncvoter.voters with a fresh random generator; the query stream is
reproduced accordingly and checked against the stored predicates. Writes results_e6b_pruned.json."""
import json, os, random, statistics, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run_e6b import TABLES, ROOT, BMAX, parse, Table, catalog, queries, violations, q
from implication import implies_canonical, implies_sat, implies_pruned, open_positions, Checker

def hybrid(T, S, chk, phi, prune):
    b = open_positions(T.cols, set(), S, phi, prune)
    t0 = time.perf_counter()
    if b > BMAX: r, how = implies_sat(T.cols, set(), S, phi), 'sat'
    elif prune: r, how = implies_pruned(T.cols, set(), S, phi), 'alg1'
    else: r, how = implies_canonical(T.cols, set(), S, phi, chk=chk), 'alg1'
    return r, b, how, (time.perf_counter() - t0) * 1e3

def main():
    old = json.load(open(os.path.join(HERE, 'results_e6b.json')))
    rng = random.Random(11); out = {}
    for ds, name in TABLES:
        if name == 'ncvoter.voters': rng = random.Random(11)        # the resumed run
        D = json.load(open(os.path.join(ROOT, 'discovery', 'results', f'{ds}.json')))
        raw = [r for t in D['tables'] if t['table'] == name for r in t['conditional'] if r.get('verified')][:40]
        keys = [dict(K=r['K'], cls=r['cls'], temps=parse(r['sql'], r['constants'])) for r in raw if r['cls'] != 'part']
        T = Table(ds, name, keys)
        T.keys = [k for k in keys if not violations(T.rows, T.cols, k['K'], k['cls'], T.scope_mask(k['temps']))]
        S = catalog(T); chk = Checker(T.cols, S)
        tn = q('e6b_' + name.replace('.', '_'))
        Q = queries(T, rng, ncontrol=len(T.keys))
        stored = old[name]['results']; res = []; i = 0
        for kind, temps, K in Q:
            C = [T.template(t) for t in temps]
            for tmpl, cls in (('DISTINCT', 'dom'), ('LEFTJOIN', 'pos')):
                o = stored[i]; i += 1
                assert o['P'] == T.sql(temps) and o['K'] == K and o['template'] == tmpl, (name, i)
                phi = (C, cls, frozenset(K))
                r1, b1, h1, t1 = hybrid(T, S, chk, phi, False)
                r2, b2, h2, t2 = hybrid(T, S, chk, phi, True)
                assert r1 == r2 == o['full'], (name, i, r1, r2, o['full'])
                res.append(dict(kind=kind, template=tmpl, implied=r2, b=b1, b_pruned=b2, solver=h1, solver_pruned=h2,
                                ms=t1, ms_pruned=t2))
        out[name] = res
        bs = [r['b_pruned'] for r in res]
        print(f"{name}: {len(res)} decisions unchanged; b {min(r['b'] for r in res)}-{max(r['b'] for r in res)} -> "
              f"{min(bs)}-{max(bs)} (median {statistics.median(bs)}); Algorithm 1 used "
              f"{sum(r['solver_pruned'] == 'alg1' for r in res)}/{len(res)}; median ms "
              f"{statistics.median(r['ms'] for r in res):.2f} -> {statistics.median(r['ms_pruned'] for r in res):.2f}", flush=True)
    json.dump(out, open(os.path.join(HERE, 'results_e6b_pruned.json'), 'w'), indent=1)
    allr = [r for v in out.values() for r in v]
    print('ALL', len(allr), 'alg1 share', round(sum(r['solver_pruned'] == 'alg1' for r in allr) / len(allr), 3),
          'median ms', round(statistics.median(r['ms_pruned'] for r in allr), 2), 'max', round(max(r['ms_pruned'] for r in allr), 1),
          'b<=10 share before', round(sum(r['b'] <= 10 for r in allr) / len(allr), 3))

if __name__ == '__main__':
    main()
