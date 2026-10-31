"""E7-real: real duplicates in NCVoter. The state removed 382 registrations of the file as
'DUPLICATE' (voter_status_reason_desc); they are confirmed errors. Detectors are the near-holding
keys mined on the full, uncleaned table (discovery/results/ncvoter-full.json, 'approximate':
conditional keys violated by at most a few pairs within their scope), compared with the same
keys without their conditions and with plain unconditional keys over the name columns.
A flagged record is confirmed if it is a removed duplicate or forms a violating pair with one.
Reported: flagged records, confirmed records, confirmed share, and its lift over the base rate."""
import csv, json, os, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'discovery'))
from run_csv import DATA, DATASETS
csv.field_size_limit(10 ** 9)

def load():
    rows = []
    with open(os.path.join(DATA, DATASETS['ncvoter']['file']), newline='', encoding='utf-8', errors='replace') as fh:
        r = csv.reader(l.replace('\0', '') for l in fh); cols = next(r)
        for row in r:
            if len(row) != len(cols): continue
            rows.append(tuple(None if v.strip() == '' else v.strip() for v in row))
    return cols, rows

def parse(sql):
    out = []
    for part in sql.strip()[1:-1].split(') OR ('):
        t = []
        for a in part.split(' AND '):
            a = a.strip()
            if a.endswith(' IS NOT NULL'): t.append((a[:-12], 'T', None))
            elif a.endswith(' IS NULL'): t.append((a[:-8], 'N', None))
            else:
                c, v = a.split(' = ', 1); t.append((c, 'C', v.strip("'")))
        out.append(t)
    return out

def pairs(rows, ix, K, cls, scope):
    """violating pairs of cls(K) among rows with scope true (pos, dom, cand via grouping;
    cert/part via null-pattern blocks, as in experiments/cleaning/run_e7.py)"""
    ki = [ix[c] for c in K]
    out = []
    if cls in ('pos', 'dom', 'cand'):
        g = defaultdict(list)
        for i, r in enumerate(rows):
            if not scope[i]: continue
            v = tuple(r[k] for k in ki)
            if cls == 'pos' and None in v: continue
            g[v].append(i)
        for grp in g.values():
            for a in range(len(grp)):
                for b in range(a + 1, len(grp)): out.append((grp[a], grp[b]))
        return out
    pat = defaultdict(list)
    for i, r in enumerate(rows):
        if scope[i]: pat[tuple(r[k] is None for k in ki)].append(i)
    P = list(pat)
    for a in range(len(P)):
        for b in range(a, len(P)):
            on = [k for t, k in enumerate(ki) if not P[a][t] and not P[b][t]]
            h = defaultdict(list)
            for j in pat[P[b]]: h[tuple(rows[j][k] for k in on)].append(j)
            for i in pat[P[a]]:
                for j in h.get(tuple(rows[i][k] for k in on), ()):
                    if j == i or (a == b and j < i): continue
                    vi = [rows[i][k] for k in ki]; vj = [rows[j][k] for k in ki]
                    if cls == 'part' and not (all(x is None or x == y for x, y in zip(vi, vj)) or
                                              all(y is None or x == y for x, y in zip(vi, vj))): continue
                    out.append((i, j))
    return out

def summarise(name, P, dup, n):
    flagged = {i for p in P for i in p}
    conf = {i for p in P for i in p if p[0] in dup or p[1] in dup}
    share = len(conf) / len(flagged) if flagged else 0
    return dict(detector=name, pairs=len(P), flagged=len(flagged), confirmed=len(conf),
                dups_found=len(flagged & dup), share=round(share, 4), lift=round(share / (len(dup) / n), 1))

def main():
    cols, rows = load(); n = len(rows); ix = {c: i for i, c in enumerate(cols)}
    dup = {i for i, r in enumerate(rows) if r[ix['voter_status_reason_desc']] == 'DUPLICATE'}
    A = json.load(open(os.path.join(ROOT, 'discovery', 'results', 'ncvoter-full.json')))['tables'][0]['approximate']
    every = [True] * n
    ck, uk, per = [], [], []
    seen_uk = {}
    for k in A:
        temps = parse(k['sql'])
        scope = [any(all((r[ix[c]] is not None) if s == 'T' else (r[ix[c]] is None) if s == 'N' else r[ix[c]] == v
                         for c, s, v in t) for t in temps) for r in rows]
        p = pairs(rows, ix, k['K'], k['cls'], scope)
        key = (tuple(k['K']), k['cls'])
        if key not in seen_uk: seen_uk[key] = pairs(rows, ix, k['K'], k['cls'], every)
        ck += p; per.append(dict(K=k['K'], cls=k['cls'], sql=k['sql'], **summarise('ck', p, dup, n)))
    for p in seen_uk.values(): uk += p
    res = dict(rows=n, removed_duplicates=len(dup), base_rate=len(dup) / n,
               ck=summarise('CK near-holding (conditional)', list(set(ck)), dup, n),
               uk=summarise('same keys without condition', list(set(uk)), dup, n),
               distinct_keys=len(seen_uk), keys=len(A))
    for K in (['last_name', 'first_name', 'birth_age'], ['last_name', 'first_name', 'middle_name', 'birth_age']):
        for cls in ('pos', 'cert'):
            res[f'name-{cls}-{len(K)}'] = summarise(f'{cls}({",".join(K)})', pairs(rows, ix, K, cls, every), dup, n)
    res['per_key'] = per
    json.dump(res, open(os.path.join(HERE, 'results_ncvoter_real.json'), 'w'), indent=1)
    for k, v in res.items():
        if isinstance(v, dict): print(v)
    print({k: v for k, v in res.items() if not isinstance(v, (dict, list))})

if __name__ == '__main__':
    main()
