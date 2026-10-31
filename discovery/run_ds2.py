"""Run the conditional key miner on the tables of the second data folder (datasets2.py), as
run_csv.py does for NCVoter and UniProt: all rows, key columns preselected by pick_keys (at most
18), condition atoms from all columns, keys of at most three columns. Writes results/<name>.json
in run_csv.py's format, so run_e6b.Table and x4_decisions.py read it.
Usage: python run_ds2.py NAME [BUDGET_SECONDS]"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ckminer import *
from run import P as BASEP
from run_csv import pick_keys
from datasets2 import DATASETS2, load2


def main():
    ds = sys.argv[1]; budget = float(sys.argv[2]) if len(sys.argv) > 2 else 1800
    cfg = DATASETS2[ds]
    t0 = time.time()
    cols, rows = load2(ds)
    P = dict(BASEP, max_const_card=15, max_const_card_narrow=15, kmax=3,
             key_cols=pick_keys(cols, rows, 18), time_budget=budget)
    print(f'{ds}: {len(rows)} rows, {len(cols)} columns; key columns {P["key_cols"]}', flush=True)
    T = Table(cfg['table'], cols, rows, P)
    uncond, found, approx = mine_table(T)
    res = postprocess(T, uncond, found)
    res.sort(key=lambda f: -score(T, f, uncond)[0])
    recs = []
    for rank_, f in enumerate(res):
        ok = verify(T, f) if rank_ < 40 else None
        sc, sup, gain, nis = score(T, f, uncond)
        recs.append(dict(table=cfg['table'], K=list(f['K']), cls=f['C'], condition=describe_cond(T, f['cond']),
                         sql=sql_pred(T, f['cond']), support=round(sup, 3), rows=bin(f['bits']).count('1'),
                         uncond=uncond.get(f['K']), gain=gain, nulls_in_scope=round(nis, 3), score=round(sc, 3),
                         tags=tags(T, f, uncond), verified=ok,
                         constants={f'{T.atoms[a][0]}=v{T.atoms[a][3]}': str(T.atoms[a][2])
                                    for at in f['cond'] for a in at if T.atoms[a][1] == 'const'}))
    print(f'{cfg["table"]:16s} rows={T.n} atoms={len(T.atoms)} uncond-keys={sum(1 for v in uncond.values() if v)} '
          f'conditional={len(recs)} failed-verification={sum(r["verified"] is False for r in recs)} '
          f'{time.time() - t0:.0f}s', flush=True)
    os.makedirs('results', exist_ok=True)
    json.dump(dict(params={k: v for k, v in P.items()}, sample_rows=len(rows), seed=None,
                   tables=[dict(table=cfg['table'], rows=T.n, cols=cols, n_conditional=len(recs),
                                conditional=recs[:300],
                                unconditional={','.join(k): v for k, v in uncond.items() if v})]),
              open(f'results/{ds}.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
