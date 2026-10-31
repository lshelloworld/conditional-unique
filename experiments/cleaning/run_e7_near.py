"""E7 with near-holding keys: detectors that are not exact on the real data.

The keys are the near-holding conditional keys that discovery reports (discovery/results/*.json,
'approximate': violated by a few pairs within their scope on the real, uncleaned table), so the
real data already contains conflicts whose status is unknown; they count against precision.
Errors (duplicates and the mixed setting of run_e7.py) are injected with source records drawn
from the whole table. Detectors as in run_e7.py: the conditional key (CK), the same key without
its condition (UK), and CFD detection. Besides precision and recall we report the review cost,
flagged records per error found. Conditions whose constants were pseudonymised are skipped
(their values are not stored). Writes results_e7_near.json."""
import argparse, glob, json, os, random, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', '..', 'discovery'))
from run_e7 import DATA, CSV_COLS, inject, violations, cfd_violations, prf, in_scope
from ckminer import load_export

TABLES = [('hockey', 'Hockey.Coaches'), ('hockey', 'Hockey.Goalies'), ('hockey', 'Hockey.Master'),
          ('hockey', 'Hockey.SeriesPost'), ('voc', 'voc.seafarers'), ('voc', 'voc.soldiers'),
          ('voc', 'voc.voyages'), ('uniprot', 'uniprot.proteins'), ('ncvoter-full', 'ncvoter.voters')]


def parse(sql):
    if ':' in sql or ' OR ' in sql: return None
    out = []
    for a in sql.strip()[1:-1].split(' AND '):
        a = a.strip()
        if a.endswith(' IS NOT NULL'): out.append(('top', a[:-12]))
        elif a.endswith(' IS NULL'): out.append(('null', a[:-8]))
        else:
            c, v = a.split(' = ', 1); out.append(('const', c, v.strip("'")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-table', type=int, default=3)
    ap.add_argument('--seeds', type=int, default=3)
    ap.add_argument('--rate', type=float, default=0.02)
    a = ap.parse_args()
    out = []
    for ds, name in TABLES:
        D = json.load(open(os.path.join(HERE, '..', '..', 'discovery', 'results', f'{ds}.json')))
        A = [r for t in D['tables'] if t['table'] == name for r in t['approximate']]
        cases, seen = [], set()
        for r in A:
            cond = parse(r['sql'])
            if cond is None or (tuple(r['K']), r['cls']) in seen: continue
            seen.add((tuple(r['K']), r['cls']))
            cases.append(dict(id=f"{name.split('.')[-1]}-{len(cases)}", K=r['K'], cls=r['cls'], cond=cond,
                              sql=r['sql'], real_violating_pairs=r['violating_pairs']))
            if len(cases) == a.per_table: break
        if not cases: continue
        if ds.startswith('ncvoter') or ds == 'uniprot':
            from run_csv import load_csv, DATA as CSVDATA, DATASETS
            d = 'ncvoter' if ds.startswith('ncvoter') else ds
            need = sorted({c for cs in cases for c in cs['K']} | {x[1] for cs in cases for x in cs['cond']} | set(CSV_COLS[d]))
            cols, rows = load_csv(os.path.join(CSVDATA, DATASETS[d]['file']), 0, 7, need)
            dsample = random.Random(1)
            domains = [sorted({r[k] for r in dsample.sample(rows, min(5000, len(rows))) if r[k] is not None}) for k in range(len(cols))]
        else:
            prefix = 'Hockey' if ds == 'hockey' else 'voc'
            path = glob.glob(os.path.join(DATA, ds, f'{name}-*-full.json'))[0]
            _, cols, rows = load_export(path)
            domains = [sorted({r[k] for r in rows if r[k] is not None}) for k in range(len(cols))]
        nullable = {k for k in range(len(cols)) if any(r[k] is None for r in rows)}
        for case in cases:
            sc = [in_scope(r, cols, case['cond']) for r in rows]
            real = violations(rows, cols, case['K'], case['cls'], sc)
            for kind in ('dup', 'mixed'):
                acc = defaultdict(lambda: [0, 0, 0, 0]); made = 0
                for seed in range(a.seeds):
                    rng = random.Random(1000 * seed + sum(map(ord, case['id'])))
                    R, truth, m = inject(rows, cols, case, kind, a.rate, rng, domains, nullable, True)
                    made += m
                    scope = [in_scope(r, cols, case['cond']) for r in R]
                    for det, fl in (('CK', violations(R, cols, case['K'], case['cls'], scope)),
                                    ('UK', violations(R, cols, case['K'], case['cls'], [True] * len(R))),
                                    ('CFD', cfd_violations(R, cols, case['K'], case['cond']))):
                        for i, v in enumerate(prf(fl, truth)): acc[det][i] += v
                res = {d: dict(ok=v[0], flagged=v[1], hit=v[2], errors=v[3],
                               P=round(v[0] / v[1], 4) if v[1] else None, R=round(v[2] / v[3], 4) if v[3] else None,
                               cost=round(v[1] / v[2], 2) if v[2] else None) for d, v in acc.items()}
                out.append(dict(case=case['id'], table=name, K=case['K'], cls=case['cls'], sql=case['sql'], kind=kind,
                                real_violating_records=len(real), errors_per_run=made / a.seeds, results=res))
                f = lambda x: '  -' if x is None else f'{x:.2f}'
                print(f"{case['id']:16s} {case['cls']:4s} {kind:5s} real={len(real):4d} " +
                      ' '.join(f"{d}={f(res[d]['P'])}/{f(res[d]['R'])} cost {f(res[d]['cost'])}" for d in ('CK', 'UK', 'CFD')), flush=True)
    json.dump(out, open(os.path.join(HERE, 'results_e7_near.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
