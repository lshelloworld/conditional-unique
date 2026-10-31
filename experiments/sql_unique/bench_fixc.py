"""Timing of FixC and DiscA on real tables (Hockey, VOC, UniProt sample).
Per table:
  (1) FixC for the empty condition and for 20 single-atom conditions (most frequent constants,
      IS NULL / IS NOT NULL of the sparsest columns), both semantics, keys of at most KMAX
      columns: time, validations, minimal keys; against a level-wise baseline that validates
      every candidate of size 1..KMAX whose subsets are not keys (Apriori-style);
  (2) DiscA over the single-atom templates of the 8 lowest-cardinality columns: with
      inheritance of disagreement sets from the parent template against FixC from scratch.
Writes bench_fixc.json. Usage: python bench_fixc.py KMAX"""
import glob, itertools, json, os, sys, time
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', '..', 'discovery'))
from fixc import fixc, encode, plis, validate
from cunique import matches
from ckminer import load_export
from run_csv import load_csv

ONE = os.environ.get('CU_EXPORTS', 'data/exports')
CSV = os.environ.get('CU_DATA1', 'data/sets1')
TABLES = [('hockey', 'Hockey.Master'), ('hockey', 'Hockey.Coaches'), ('hockey', 'Hockey.Teams'),
          ('hockey', 'Hockey.Goalies'), ('voc', 'voc.voyages'), ('voc', 'voc.seafarers')]


def levelwise(rows, cols, C, sem, kmax):
    idx = [i for i, r in enumerate(rows) if any(matches(r, t) for t in C)]
    if len(idx) < 2: return [frozenset()], 0
    enc = encode(rows, idx, cols, sem); P = plis(enc, idx, len(cols))
    keys, checks = [], 0
    for k in range(1, kmax + 1):
        for K in itertools.combinations(range(len(cols)), k):
            K = frozenset(K)
            if any(L <= K for L in keys): continue
            checks += 1
            if validate(enc, P, K) is None: keys.append(K)
    return keys, checks


def conditions(rows, cols, n=20):
    out = []
    nulls = sorted(cols, key=lambda A: -sum(r[A] is None for r in rows))
    for A in nulls[:5]:
        out += [((A, 'null'), {A: ('null',)}), ((A, 'notnull'), {A: ('notin', frozenset())})]
    freq = Counter((A, r[A]) for r in rows for A in cols if r[A] is not None)
    for (A, v), c in freq.most_common():
        if len(out) >= n: break
        if c < len(rows): out.append(((A, '=', str(v)), {A: ('in', frozenset([v]))}))
    return out[:n]


def run(rows, cols, kmax):
    rows = [dict(zip(cols, r)) for r in rows]
    full = {A: ('any',) for A in cols}
    res = {'rows': len(rows), 'cols': len(cols), 'fixc': [], 'disca': {}}
    for name, atom in [(('none',), {})] + conditions(rows, cols):
        C = [dict(full, **atom)]
        for sem in ('U', 'Ueq'):
            st = {}; t0 = time.perf_counter()
            ks, _ = fixc(rows, cols, C, sem, kmax, (), st); t1 = time.perf_counter()
            lk, lchecks = levelwise(rows, cols, C, sem, kmax); t2 = time.perf_counter()
            assert sorted(map(sorted, ks)) == sorted(sorted(cols[j] for j in K) for K in lk) or ks == [frozenset()], name
            res['fixc'].append(dict(cond=list(name), sem=sem, scope=sum(matches(r, C[0]) for r in rows), keys=len(ks),
                                    fixc_ms=(t1 - t0) * 1e3, fixc_checks=st.get('checks', 0),
                                    level_ms=(t2 - t1) * 1e3, level_checks=lchecks))
    low = sorted(cols, key=lambda A: len({r[A] for r in rows}))[:8]
    tpls = [{}]
    for A in low:
        vals = sorted({r[A] for r in rows if r[A] is not None}, key=repr)[:10]
        tpls += [{A: ('null',)}, {A: ('notin', frozenset())}] + [{A: ('in', frozenset([v]))} for v in vals]
    for sem in ('U', 'Ueq'):
        st = {}; t0 = time.perf_counter()
        _, root = fixc(rows, cols, [full], sem, kmax, (), st)
        for a in tpls[1:]: fixc(rows, cols, [dict(full, **a)], sem, kmax, root, st)
        t1 = time.perf_counter(); st2 = {}
        for a in tpls: fixc(rows, cols, [dict(full, **a)], sem, kmax, (), st2)
        t2 = time.perf_counter()
        res['disca'][sem] = dict(templates=len(tpls), inherit_ms=(t1 - t0) * 1e3, inherit_checks=st['checks'],
                                 scratch_ms=(t2 - t1) * 1e3, scratch_checks=st2['checks'])
    return res


def main():
    kmax = int(sys.argv[1]); out = {}
    for ds, name in TABLES:
        path = glob.glob(os.path.join(ONE, ds, f'{name}-*-full.json'))[0]
        _, cols, rows = load_export(path)
        out[name] = run(rows, cols, kmax); report(name, out[name])
    cols, rows = load_csv(os.path.join(CSV, 'uniprot_539166r_100c.csv'), 20000, 7)
    out['uniprot(20k)'] = run(rows, cols, kmax); report('uniprot(20k)', out['uniprot(20k)'])
    json.dump(out, open(os.path.join(HERE, f'bench_fixc_k{kmax}.json'), 'w'), indent=1)


def report(name, r):
    f = r['fixc']; med = lambda xs: sorted(xs)[len(xs) // 2]
    print(f"{name}: {r['rows']} rows x {r['cols']} cols; FixC median {med([x['fixc_ms'] for x in f]):.1f} ms "
          f"({med([x['fixc_checks'] for x in f])} validations), level-wise median {med([x['level_ms'] for x in f]):.1f} ms "
          f"({med([x['level_checks'] for x in f])} validations); keys median {med([x['keys'] for x in f])}; "
          + '; '.join(f"DiscA {s}: {d['templates']} templates, inherit {d['inherit_ms']:.0f} ms / {d['inherit_checks']} val., "
                      f"scratch {d['scratch_ms']:.0f} ms / {d['scratch_checks']} val." for s, d in r['disca'].items()), flush=True)


if __name__ == '__main__':
    main()
