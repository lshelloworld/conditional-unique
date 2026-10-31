"""X6: conditional key discovery with a fixed condition is UCC discovery on the encoded scope;
how do FixC and state-of-the-art UCC algorithms compare on it?

Scope and encoding as in fixc.py: the rows matching the condition; for U each null becomes a
value of its own, for U= all nulls one value (agreement is then plain equality). The encoded
scope is written to CSV (every value prefixed, so no field is empty) and given to HyUCC and
HPIValid of Desbordante 2.4.1 (C++, one thread) -- not Metanome's Java HyUCC. Timed: CSV load
and execute separately; FixC (Python) without a size bound, with a time budget, and with keys
of at most 3 columns. Correctness: the HyUCC, HPIValid and unbounded FixC key sets agree; when
FixC runs out of time, HyUCC's keys of at most 3 columns agree with FixC's.

Suites:
  conditions  the 7 tables and 21 conditions x 2 semantics of bench_fixc.py
  rows        the 30-column UniProt exports with 16k, 32k, 128k, 256k and 512k rows (all rows; the
              empty condition and the first 4 conditions), both semantics
  cols        UniProt 20k rows, first 10, 25, 50, 100 columns, empty condition, both semantics
  ds2         the 9 tables of the second data folder (datasets2.py), all rows, 21 conditions x 2
              semantics as in 'conditions'
  lb          40 sampled LakeBench OpenData tables with mined keys (results_lb/subset40.txt), on the
              at most 18 key columns the miner uses (run_csv.pick_keys) and up to 12 columns with 2-20
              values for conditions (some tables have 100+ columns, where unbounded FixC exhausts
              memory), same conditions and semantics as 'ds2'
The 100-column export uniprot_539166r_100c.csv is truncated in this copy (44 MiB, 24,173
complete rows), so 'conditions' and 'cols' sample 20k of those rows.
Writes x6_hyucc_<suite>.json. Usage: python x6_hyucc.py SUITE BUDGET_SECONDS"""
import csv, glob, json, os, re, signal, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', '..', 'discovery'))
import desbordante
from fixc import fixc, encode
from cunique import matches
from ckminer import load_export
from run_csv import load_csv, pick_keys
from bench_fixc import ONE, CSV, TABLES, conditions
from datasets2 import DATASETS2, load2

TMP = tempfile.mkdtemp(prefix='x6_')


class Budget(Exception): pass


def _alarm(*_): raise Budget()


def write_scope(rows, cols, C, sem):
    idx = [i for i, r in enumerate(rows) if any(matches(r, t) for t in C)]
    enc = encode(rows, idx, cols, sem)
    path = os.path.join(TMP, 'scope.csv')
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([f'c{j}' for j in range(len(cols))])
        for i in idx: w.writerow(['v' + repr(x) for x in enc[i]])
    return path, len(idx)


def ucc(name, path):
    a = getattr(desbordante.ucc.algorithms, name)()
    t0 = time.perf_counter()
    a.load_data(table=(path, ',', True), is_null_equal_null=True)   # nulls already encoded
    t1 = time.perf_counter()
    if name == 'HyUCC': a.execute(threads=1)
    else: a.execute()
    t2 = time.perf_counter()
    keys = sorted(tuple(sorted(int(x) for x in re.findall(r'\d+', str(u)))) for u in a.get_uccs())
    return keys, (t1 - t0) * 1e3, (t2 - t1) * 1e3


def run_fixc(rows, cols, C, sem, kmax, budget):
    signal.signal(signal.SIGALRM, _alarm); signal.alarm(budget)
    t0 = time.perf_counter()
    try:
        ks, _ = fixc(rows, cols, C, sem, kmax)
        ms = (time.perf_counter() - t0) * 1e3
    except Budget:
        return None, None
    finally:
        signal.alarm(0)
    pos = {c: j for j, c in enumerate(cols)}
    return sorted(tuple(sorted(pos[c] for c in K)) for K in ks), ms


def case(rows, cols, name, C, sem, budget):
    path, n = write_scope(rows, cols, C, sem)
    r = dict(cond=name, sem=sem, scope=n, cols=len(cols))
    if n < 2:
        r['trivial'] = True; return r
    for alg in ('HyUCC', 'HPIValid'):
        k, load, ex = ucc(alg, path)
        r[alg] = dict(keys=len(k), load_ms=load, exec_ms=ex); r[f'_{alg}'] = k
    full, ms = run_fixc(rows, cols, C, sem, None, budget)
    r['fixc'] = dict(keys=len(full) if full is not None else None, ms=ms, timeout=full is None)
    k3, ms3 = run_fixc(rows, cols, C, sem, 3, budget)
    r['fixc3'] = dict(keys=len(k3) if k3 is not None else None, ms=ms3, timeout=k3 is None)
    h = r['_HyUCC']
    r['agree_hpivalid'] = h == r['_HPIValid']
    r['agree_fixc'] = (h == full) if full is not None else None
    r['agree_fixc3'] = ([k for k in h if len(k) <= 3] == k3) if k3 is not None else None
    del r['_HyUCC'], r['_HPIValid']
    return r


def tables(suite):
    if suite == 'conditions':
        for ds, name in TABLES:
            _, cols, rows = load_export(glob.glob(os.path.join(ONE, ds, f'{name}-*-full.json'))[0])
            yield name, cols, rows, None
        cols, rows = load_csv(os.path.join(CSV, 'uniprot_539166r_100c.csv'), 20000, 7)
        yield 'uniprot(20k)', cols, rows, None
    elif suite == 'rows':
        for n in (16001, 32001, 128001, 256001, 512001):
            cols, rows = load_csv(os.path.join(CSV, f'uniprot_{n}r_30c.csv'), 0, 7)
            yield f'uniprot({len(rows)})', cols, rows, 4
    elif suite == 'ds2':
        for name in [n for n in DATASETS2 if not DATASETS2[n].get('lakebench')]:
            cols, rows = load2(name)
            yield DATASETS2[name]['table'], cols, rows, None
    elif suite == 'lb':
        sub = open(os.path.join(HERE, '..', '..', 'discovery', 'results_lb', 'subset40.txt')).read()
        for name in [x.split(':')[0] for x in sub.split(',')]:
            cols, rows = load2(name)
            keep = pick_keys(cols, rows, 18)
            keep += [c for i, c in enumerate(cols) if c not in keep
                     and 2 <= len({r[i] for r in rows if r[i] is not None}) <= 20][:12]
            keep = [c for c in cols if c in keep]
            cols, rows = load2(name, keep)
            yield DATASETS2[name]['table'], cols, rows, None
    elif suite == 'cols':
        cols, rows = load_csv(os.path.join(CSV, 'uniprot_539166r_100c.csv'), 20000, 7)
        for m in (10, 25, 50, 100):
            yield f'uniprot(20k, {m} cols)', cols[:m], [r[:m] for r in rows], 0


def main():
    suite, budget = sys.argv[1], int(sys.argv[2])
    out = []
    for name, cols, rows, ncond in tables(suite):
        rows = [dict(zip(cols, r)) for r in rows]
        full = {A: ('any',) for A in cols}
        conds = [(('none',), {})] + conditions(rows, cols)
        if ncond is not None: conds = conds[:1 + ncond]
        for cname, atom in conds:
            for sem in ('U', 'Ueq'):
                r = case(rows, cols, '/'.join(map(str, cname)), [dict(full, **atom)], sem, budget)
                r['table'] = name; r['rows'] = len(rows); out.append(r)
                if r.get('trivial'): continue
                fms = lambda d: 'timeout' if d['timeout'] else '%9.1f ms' % d['ms']
                print('%-24s %-28s %-3s scope %6d  HyUCC %9.1f ms (load %7.1f)  HPIValid %9.1f ms  FixC %s  FixC<=3 %s  keys %d  agree %s/%s/%s' % (
                    name, r['cond'][:28], sem, r['scope'], r['HyUCC']['exec_ms'], r['HyUCC']['load_ms'], r['HPIValid']['exec_ms'],
                    fms(r['fixc']), fms(r['fixc3']), r['HyUCC']['keys'], r['agree_hpivalid'], r['agree_fixc'], r['agree_fixc3']), flush=True)
        json.dump(out, open(os.path.join(HERE, f'x6_hyucc_{suite}.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
