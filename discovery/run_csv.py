"""Run the conditional key miner on plaintext CSV datasets (NCVoter, UniProt).

A random sample of rows is drawn (fixed seed); values are stripped and empty strings are NULL.
Key columns are preselected (identifier-like names or high distinctness, at most 90% nulls);
condition atoms come from all columns."""
import csv, json, os, random, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ckminer import *
from run import P as BASEP

DATA = os.environ.get('CU_DATA1', 'data/sets1')
# curated full-data run for NCVoter: person attributes as key columns, categorical columns as
# conditions; all rows, keys up to five columns
CURATED = {
    'ncvoter': dict(key_cols=['last_name', 'first_name', 'middle_name', 'name_suffix_lbl', 'birth_age',
                              'birth_state', 'res_street_address'],
                    cond_cols=['status_cd', 'reason_cd', 'party_cd', 'gender_code', 'race_code', 'ethnic_code',
                               'absent_ind', 'confidential_ind', 'drivers_lic'],
                    kmax=5, approx_pairs=500),
}
DATASETS = {
    'ncvoter': dict(file='ncvoter_Statewide_1024001r_71c.csv', table='ncvoter.voters'),
    'uniprot': dict(file='uniprot_539166r_100c.csv', table='uniprot.proteins'),
}
csv.field_size_limit(10 ** 9)

def load_csv(path, n, seed, keep=None):
    """n > 0: reservoir sample of n rows; n == 0: all rows. keep: only these columns."""
    rng = random.Random(seed)
    sample = []
    with open(path, newline='', encoding='utf-8', errors='replace') as fh:
        r = csv.reader(line.replace('\0', '') for line in fh)   # the export contains stray NUL bytes
        cols = next(r)
        ki = [cols.index(c) for c in keep] if keep else list(range(len(cols)))
        norm = lambda row: tuple(None if row[i].strip() == '' else row[i].strip() for i in ki)
        for i, row in enumerate(r):
            if len(row) != len(cols): continue
            if n == 0: sample.append(norm(row)); continue
            if len(sample) < n: sample.append(norm(row))     # reservoir sample
            else:
                j = rng.randrange(i + 1)
                if j < n: sample[j] = norm(row)
    return [cols[i] for i in ki], sample

ID = re.compile(r'(id$|_id|ID|num|name|accession|checksum|locus|orf|phone|lic|addr|street|dt$|date|gene_primary|sequence$)', re.I)

def pick_keys(cols, rows, k):
    n = len(rows)
    stats = []
    for i, c in enumerate(cols):
        vals = [r[i] for r in rows]
        nn = sum(v is None for v in vals) / n
        dist = len({v for v in vals if v is not None}) / max(1, n - sum(v is None for v in vals))
        if nn > 0.9 or dist < 0.01: continue
        stats.append((bool(ID.search(c)), dist, c))
    stats.sort(reverse=True)
    return [c for _, _, c in stats[:k]]

def main():
    ds = sys.argv[1]; n = int(sys.argv[2]); seed = 7
    cfg = DATASETS[ds]
    t0 = time.time()
    curated = CURATED.get(ds) if n == 0 else None
    keep = curated['key_cols'] + curated['cond_cols'] if curated else None
    cols, rows = load_csv(os.path.join(DATA, cfg['file']), n, seed, keep)
    P = dict(BASEP, max_const_card=15, max_const_card_narrow=15, kmax=3,
             key_cols=pick_keys(cols, rows, int(sys.argv[3]) if len(sys.argv) > 3 else 18),
             time_budget=float(sys.argv[4]) if len(sys.argv) > 4 else 3600)
    if curated:
        P.update(key_cols=curated['key_cols'], kmax=curated['kmax'], approx_pairs=curated['approx_pairs'])
    print(f'{ds}: {"all" if n == 0 else "sample"} {len(rows)} rows, {len(cols)} columns, loaded in {time.time() - t0:.0f}s; key columns {P["key_cols"]}', flush=True)
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
    approx = [f for f in approx if all(id_like(T, c) for c in f['K'])]
    arecs = [dict(table=cfg['table'], K=list(f['K']), cls=f['C'], condition=describe_cond(T, f['cond']),
                  sql=sql_pred(T, f['cond']), support=round(bin(f['bits']).count('1') / T.n, 3),
                  violating_pairs=len(f['violations']),
                  violating_rows=sorted({i for p in f['violations'] for i in p}), uncond=uncond.get(f['K']))
             for f in approx]
    arecs.sort(key=lambda r: (r['violating_pairs'], -r['support']))
    print(f'{cfg["table"]:20s} rows={T.n} atoms={len(T.atoms)} uncond-keys={sum(1 for v in uncond.values() if v)} '
          f'conditional={len(recs)} approx={len(arecs)} failed-verification={sum(r["verified"] is False for r in recs)} '
          f'{time.time() - t0:.0f}s', flush=True)
    os.makedirs('results', exist_ok=True)
    json.dump(dict(params={k: v for k, v in P.items()}, sample_rows=len(rows), seed=seed,
                   tables=[dict(table=cfg['table'], rows=T.n, cols=cols, n_conditional=len(recs), n_approximate=len(arecs),
                                conditional=recs[:300], approximate=arecs[:300],
                                unconditional={','.join(k): v for k, v in uncond.items() if v})]),
              open(f'results/{ds}{"-full" if curated else ""}.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
