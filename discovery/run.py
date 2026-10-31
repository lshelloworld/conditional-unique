"""Run the conditional key miner on the Hockey and VOC exports and write results + report."""
import glob, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ckminer import *

DATA = os.environ.get('CU_EXPORTS', 'data/exports')
P = dict(kmax=3, minsup_rows=20, minsup_frac=0.03, max_const_card=12, max_const_card_narrow=30, narrow_cols=10, max_key_null=0.9,
         pair_cap=200000, max_involved=0.3, approx_pairs=3, time_budget=600)

def run(dataset, pattern, only=None):
    out = []
    for path in sorted(glob.glob(os.path.join(DATA, dataset, pattern))):
        if '-full' not in path: continue                       # Scoring, TeamVsTeam are samples
        name, cols, rows = load_export(path)
        if only and name.split('.')[-1] not in only: continue
        t0 = time.time()
        T = Table(name, cols, rows, P)
        uncond, found, approx = mine_table(T)
        res = postprocess(T, uncond, found)
        recs = []
        res.sort(key=lambda f: -score(T, f, uncond)[0])
        for rank_, f in enumerate(res):
            ok = verify(T, f) if rank_ < 40 else None      # independent check of the top results
            sc, sup, gain, nis = score(T, f, uncond)
            recs.append(dict(table=name, K=list(f['K']), cls=f['C'], condition=describe_cond(T, f['cond']),
                             sql=sql_pred(T, f['cond']), support=round(sup, 3), rows=bin(f['bits']).count('1'),
                             uncond=uncond.get(f['K']), gain=gain, nulls_in_scope=round(nis, 3),
                             score=round(sc, 3), tags=tags(T, f, uncond), verified=ok,
                             constants={f'{T.atoms[a][0]}=v{T.atoms[a][3]}': str(T.atoms[a][2])
                                        for at in f['cond'] for a in at if T.atoms[a][1] == 'const'}))
        arecs = []
        approx = [f for f in approx if all(id_like(T, c) for c in f['K'])]
        for f in approx:
            sup = bin(f['bits']).count('1') / T.n
            rows_bad = sorted({i for p in f['violations'] for i in p})
            arecs.append(dict(table=name, K=list(f['K']), cls=f['C'], condition=describe_cond(T, f['cond']),
                              sql=sql_pred(T, f['cond']), support=round(sup, 3), violating_pairs=len(f['violations']),
                              violating_rows=rows_bad, uncond=uncond.get(f['K'])))
        nkeys = sum(1 for v in uncond.values() if v)
        print(f'{name:28s} rows={T.n:6d} cols={len(cols):3d} atoms={len(T.atoms):3d} '
              f'uncond-keys={nkeys:4d} conditional={len(recs):4d} approx={len(arecs):4d} '
              f'failed-verification={sum(r["verified"] is False for r in recs)} {time.time() - t0:6.1f}s', flush=True)
        nrec, nap = len(recs), len(arecs)
        arecs.sort(key=lambda r: (r['violating_pairs'], -r['support']))
        out.append(dict(table=name, rows=T.n, cols=cols, n_conditional=nrec, n_approximate=nap,
                        conditional=recs[:300], approximate=arecs[:300],
                        unconditional={','.join(k): v for k, v in uncond.items() if v}))
    return out

if __name__ == '__main__':
    ds = sys.argv[1]; only = sys.argv[2].split(',') if len(sys.argv) > 2 else None
    pat = 'Hockey.*.json' if ds == 'hockey' else 'voc.*.json'
    res = run(ds, pat, only)
    os.makedirs('results', exist_ok=True)
    json.dump(dict(params=P, tables=res), open(f'results/{ds}{"-" + "-".join(only) if only else ""}.json', 'w'), indent=1)
