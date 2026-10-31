"""E7: data cleaning with discovered conditional keys.

For each discovered conditional key C:K(K) (exact on the real data), errors are injected into
its scope, and detectors flag records:
  CK-<class>   the key K of that class under the discovered condition C,
  UK-<class>   the key K of that class without condition,
  CFD          the CFD (K u C_const -> R, t_p) of Fan et al. with the SQL detection semantics
               of their query Q^V (GROUP BY on the left-hand side, nulls grouped together; a group
               is a violation if some other attribute has two distinct non-null values); C_const
               are the constant atoms of the condition -- presence/absence atoms cannot be
               expressed by CFD patterns, so for such conditions the CFD is the plain FD K -> R.
Error types (each record copy keeps the condition columns, so it stays in the scope):
  dup        copy of an in-scope record with one non-key, non-condition value changed;
  partial    copy of an in-scope record with one nullable key value set to null
             (and one payload value changed): an incomplete duplicate;
  missing    an in-scope record whose nullable key value is erased (missing identifier);
  mixed      all three at once.
Errors are the injected copies and the modified records. Recall is the share of errors that a
detector flags. Precision is the share of flagged records that are errors or the source records
of injected copies (a duplicate is a conflict between both, so flagging the source is correct).
Real records outside the scope that conflict with each other are legitimate (the condition is
why the key fails unconditionally), so flagging them is a false positive. Averaged over seeds.
"""
import argparse, glob, json, os, random, statistics, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'discovery'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'discovery'))
from ckminer import load_export

DATA = os.environ.get('CU_EXPORTS', 'data/exports')
CLASSES = ['pos', 'dom', 'part', 'cert', 'cand']

def const(ds, table, label):
    D = json.load(open(os.path.join(HERE, '..', '..', 'discovery', 'results', f'{ds}.json')))
    for t in D['tables']:
        if t['table'].split('.')[-1] != table: continue
        for r in t['conditional']:
            if label in r['constants']: return int(r['constants'][label])
    raise KeyError(label)

def cases():
    nhl = const('hockey', 'SeriesPost', 'lgIDWinner=v1')
    hof = const('hockey', 'HOF', 'category=v2')
    ch1 = const('voc', 'invoices', 'chamber=v1')
    C = lambda **k: k
    return [
        C(id='SP', ds='hockey', table='SeriesPost', cls='cand', K=['year', 'tmIDLoser'], cond=[('const', 'lgIDWinner', nhl)]),
        C(id='GO', ds='hockey', table='Goalies', cls='cand', K=['playerID', 'year', 'tmID'], cond=[('const', 'lgID', nhl)]),
        C(id='CO', ds='hockey', table='Coaches', cls='cand', K=['coachID', 'year'], cond=[('top', 'postg')]),
        C(id='GO2', ds='hockey', table='Goalies', cls='cand', K=['playerID', 'year'], cond=[('top', 'PostGP')]),
        C(id='HOF', ds='hockey', table='HOF', cls='cand', K=['name'], cond=[('const', 'category', hof)]),
        C(id='MA1', ds='hockey', table='Master', cls='part', K=['playerID', 'firstName', 'hrefID'], cond=[('top', 'pos')]),
        C(id='MA2', ds='hockey', table='Master', cls='cert', K=['firstName', 'lastName', 'hrefID'], cond=[('top', 'weight')]),
        C(id='SO', ds='voc', table='soldiers', cls='cand', K=['number'], cond=[('top', 'onboard_at_arrival')]),
        C(id='SE', ds='voc', table='seafarers', cls='cand', K=['number'], cond=[('top', 'onboard_at_arrival')]),
        C(id='VO1', ds='voc', table='voyages', cls='cert', K=['number', 'arrival_date'], cond=[('null', 'type_of_boat')]),
        C(id='VO2', ds='voc', table='voyages', cls='cand', K=['number', 'departure_date'], cond=[('null', 'type_of_boat')]),
        C(id='VO3', ds='voc', table='voyages', cls='dom', K=['boatname', 'departure_date'], cond=[('top', 'master')]),
        C(id='VO4', ds='voc', table='voyages', cls='cert', K=['number', 'chamber'], cond=[('top', 'arrival_harbour')]),
        C(id='IN', ds='voc', table='invoices', cls='cand', K=['number', 'invoice'], cond=[('const', 'chamber', ch1)]),
        C(id='TR1', ds='voc', table='voyages', cls='pos', K=['master', 'departure_date'], cond=[('top', 'yard')]),
        C(id='TR2', ds='voc', table='voyages', cls='pos', K=['master', 'departure_date'], cond=[('top', 'cape_arrival')]),
        # plaintext datasets at real scale
        C(id='NV1', ds='ncvoter', table='voters', cls='cert',
          K=['last_name', 'first_name', 'middle_name', 'birth_age', 'res_street_address'],
          cond=[('const', 'status_cd', 'A'), ('const', 'drivers_lic', 'Y')]),
        C(id='NV2', ds='ncvoter', table='voters', cls='cand',
          K=['last_name', 'first_name', 'birth_age', 'res_street_address'],
          cond=[('const', 'status_cd', 'I'), ('const', 'drivers_lic', 'Y')]),
        C(id='NV3', ds='ncvoter', table='voters', cls='dom',
          K=['first_name', 'middle_name', 'birth_age', 'birth_state', 'res_street_address'],
          cond=[('const', 'status_cd', 'A'), ('const', 'drivers_lic', 'Y')]),
        C(id='NVT', ds='ncvoter', table='voters', cls='pos',
          K=['first_name', 'middle_name', 'birth_age', 'res_street_address'],
          cond=[('const', 'status_cd', 'A'), ('const', 'drivers_lic', 'Y')]),
        C(id='UP1', ds='uniprot', table='proteins', cls='cert', K=['cross_reference_geneid', 'sequence_checksum'],
          cond=[('top', 'cross_reference_oma')]),
        C(id='UP2', ds='uniprot', table='proteins', cls='cert', K=['sequence_checksum', 'feature_chain'],
          cond=[('null', 'feature_modified_residue')]),
    ]

# columns loaded for the plaintext datasets (payload columns for perturbation included)
CSV_COLS = {
    'ncvoter': ['ncid', 'last_name', 'first_name', 'middle_name', 'birth_age', 'birth_state', 'res_street_address',
                'status_cd', 'drivers_lic', 'party_cd', 'gender_code', 'race_code', 'zip_code', 'full_phone_number'],
    'uniprot': ['accession', 'name', 'cross_reference_geneid', 'sequence_checksum', 'feature_chain',
                'cross_reference_oma', 'feature_modified_residue', 'sequence_length', 'gene_primary'],
}

def in_scope(row, cols, cond):
    for kind, c, *v in cond:
        x = row[cols.index(c)]
        if kind == 'const' and x != v[0]: return False
        if kind == 'top' and x is None: return False
        if kind == 'null' and x is not None: return False
    return True

# ----------------------------------------------------------------------------- detectors
def violations(rows, cols, K, cls, scope):
    """records involved in violations of cls(K) among the rows with scope[i] true"""
    ki = [cols.index(c) for c in K]
    idx = [i for i in range(len(rows)) if scope[i]]
    flagged = set()
    if cls in ('pos', 'dom', 'cand'):
        g = defaultdict(list)
        for i in idx:
            v = tuple(rows[i][k] for k in ki)
            if cls == 'pos' and None in v: continue
            g[v].append(i)
        for grp in g.values():
            if len(grp) > 1: flagged.update(grp)
        if cls == 'cand':
            flagged.update(i for i in idx if any(rows[i][k] is None for k in ki))
        return flagged
    # part / cert: compatible pairs by null pattern
    pat = defaultdict(list)
    for i in idx: pat[tuple(rows[i][k] is None for k in ki)].append(i)
    pats = list(pat)
    for a in range(len(pats)):
        for b in range(a, len(pats)):
            on = [k for t, k in enumerate(ki) if not pats[a][t] and not pats[b][t]]
            h = defaultdict(list)
            for j in pat[pats[b]]: h[tuple(rows[j][k] for k in on)].append(j)
            for i in pat[pats[a]]:
                for j in h.get(tuple(rows[i][k] for k in on), ()):
                    if j == i or (a == b and j < i): continue
                    vi = [rows[i][k] for k in ki]; vj = [rows[j][k] for k in ki]
                    if cls == 'part':
                        sub = all(x is None or x == y for x, y in zip(vi, vj)) or all(y is None or x == y for x, y in zip(vi, vj))
                        if not sub: continue
                    flagged.add(i); flagged.add(j)
    return flagged

def cfd_violations(rows, cols, K, cond):
    consts = [(cols.index(c), v[0]) for kind, c, *v in cond if kind == 'const']
    lhs = [cols.index(c) for c in K] + [k for k, _ in consts]
    other = [k for k in range(len(cols)) if k not in lhs]
    g = defaultdict(list)
    for i, r in enumerate(rows):
        if all(r[k] == v for k, v in consts):
            g[tuple(r[k] for k in lhs)].append(i)
    flagged = set()
    for grp in g.values():
        if len(grp) < 2: continue
        if any(len({rows[i][k] for i in grp if rows[i][k] is not None}) > 1 for k in other):
            flagged.update(grp)
    return flagged

# ----------------------------------------------------------------------------- injection
def inject(rows, cols, case, kind, rate, rng, domains, nullable, anywhere=False):
    rows = [list(r) for r in rows]
    ki = [cols.index(c) for c in case['K']]
    condcols = {cols.index(c) for _, c, *_ in case['cond']}
    payload = [k for k in range(len(cols)) if k not in ki and k not in condcols and len(domains[k]) > 1]
    scope = [i for i, r in enumerate(rows) if in_scope(r, cols, case['cond'])]
    n = max(10, int(rate * len(scope)))
    if anywhere:   # sources anywhere in the table: copies keep their source's condition values
        scope = list(range(len(rows)))
    truth, sources = set(), set()
    missing_pool = None
    kinds = ['dup', 'partial', 'missing'] if kind == 'mixed' else [kind]
    made = 0
    for t in range(n):
        k = kinds[t % len(kinds)]
        if k in ('dup', 'partial'):
            src = rng.choice(scope)
            new = list(rows[src])
            if k == 'partial':
                cand = [x for x in ki if x in nullable and new[x] is not None]
                if not cand: continue
                new[rng.choice(cand)] = None
            if payload:
                p = rng.choice(payload)
                choices = [v for v in domains[p] if v != new[p]]
                if choices: new[p] = rng.choice(choices)
            rows.append(new); truth.add(len(rows) - 1); sources.add(src); made += 1
        else:
            if missing_pool is None:    # built once: in-scope records with a nullable key value
                missing_pool = [i for i in scope if any(rows[i][x] is not None for x in ki if x in nullable)]
                rng.shuffle(missing_pool)
            while missing_pool and (missing_pool[-1] in truth or missing_pool[-1] in sources):
                missing_pool.pop()
            if not missing_pool: continue
            i = missing_pool.pop()
            x = rng.choice([x for x in ki if x in nullable and rows[i][x] is not None])
            rows[i][x] = None; truth.add(i); made += 1
    return [tuple(r) for r in rows], (truth, sources - truth), made

def prf(flagged, gt):
    """counts: correctly flagged, flagged, errors found, errors"""
    errors, sources = gt
    return (len(flagged & (errors | sources)), len(flagged), len(flagged & errors), len(errors))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=int, default=5)
    ap.add_argument('--rate', type=float, default=0.02)
    ap.add_argument('--out', default=os.path.join(HERE, 'results_e7.json'))
    ap.add_argument('--only', default='')
    ap.add_argument('--anywhere', action='store_true',
                    help='inject errors into the whole table, not only into the scope')
    a = ap.parse_args()
    tables = {}
    out = []
    for case in [c for c in cases() if not a.only or c['ds'] in a.only.split(',')]:
        key = (case['ds'], case['table'])
        if key not in tables:
            if case['ds'] in CSV_COLS:
                from run_csv import load_csv, DATA as CSVDATA, DATASETS
                cols, rows = load_csv(os.path.join(CSVDATA, DATASETS[case['ds']]['file']), 0, 7, CSV_COLS[case['ds']])
            else:
                prefix = 'Hockey' if case['ds'] == 'hockey' else 'voc'
                path = glob.glob(os.path.join(DATA, case['ds'], f'{prefix}.{case["table"]}-*-full.json'))[0]
                _, cols, rows = load_export(path)
            tables[key] = (cols, rows)
        cols, rows = tables[key]
        if case['ds'] in CSV_COLS:      # plaintext columns: sample replacement values, do not sort millions
            dsample = random.Random(1)
            domains = [list({r[k] for r in dsample.sample(rows, min(5000, len(rows))) if r[k] is not None}) for k in range(len(cols))]
            domains = [sorted(d) for d in domains]
        else:
            domains = [sorted({r[k] for r in rows if r[k] is not None}) for k in range(len(cols))]
        nullable = {k for k in range(len(cols)) if any(r[k] is None for r in rows)}
        # sanity: the discovered key holds on the clean data
        sc = [in_scope(r, cols, case['cond']) for r in rows]
        assert not violations(rows, cols, case['K'], case['cls'], sc), case['id']
        for kind in ['dup', 'partial', 'missing', 'mixed']:
            acc = defaultdict(list)
            made_total = 0
            for seed in range(a.seeds):
                rng = random.Random(1000 * seed + sum(map(ord, case['id'])))
                R, truth, made = inject(rows, cols, case, kind, a.rate, rng, domains, nullable, a.anywhere)
                made_total += made
                if not made: continue
                scope = [in_scope(r, cols, case['cond']) for r in R]
                every = [True] * len(R)
                for cls in CLASSES:
                    acc[f'CK-{cls}'].append(prf(violations(R, cols, case['K'], cls, scope), truth))
                    acc[f'UK-{cls}'].append(prf(violations(R, cols, case['K'], cls, every), truth))
                acc['CFD'].append(prf(cfd_violations(R, cols, case['K'], case['cond']), truth))
            if not made_total:
                continue
            res = {}
            for d, v in acc.items():
                ok, fl, hit, ne = (sum(x[i] for x in v) for i in range(4))
                res[d] = dict(ok=ok, flagged=fl, hit=hit, errors=ne,
                              P=round(ok / fl, 4) if fl else None, R=round(hit / ne, 4) if ne else None)
            out.append(dict(case=case['id'], table=case['table'], cls=case['cls'], K=case['K'],
                            cond=[(k, c) for k, c, *_ in case['cond']], kind=kind,
                            errors_per_run=made_total / a.seeds, results=res))
            fmt = lambda x: '  -' if x is None else f'{x:.2f}'
            print(f"{case['id']:4s} {case['cls']:4s} {kind:8s} n={made_total / a.seeds:5.1f} "
                  + ' '.join(f"{d}={fmt(res[d]['P'])}/{fmt(res[d]['R'])}" for d in
                             ['CK-' + case['cls'], 'UK-' + case['cls'], 'CK-pos', 'CK-cand', 'CFD']), flush=True)
    json.dump(out, open(a.out, 'w'), indent=1)
    print('wrote', a.out)

if __name__ == '__main__':
    main()
