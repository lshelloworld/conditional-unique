"""Re-check conditional keys mined on a sample against the full dataset.

Reads results/<ds>.json, takes the top-N conditional keys, streams the full CSV in batches of
keys (keeping only the key values of rows in each key's scope), and counts the records
involved in violations with the detector of experiments/cleaning/run_e7.py. Writes
results/<ds>-full-check.json and prints a summary."""
import csv, json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'experiments', 'cleaning'))
from run_csv import DATA, DATASETS
from run_e7 import violations
csv.field_size_limit(10 ** 9)

def parse(sql):
    """'(a = 'x' AND b IS NULL) OR (c IS NOT NULL)' -> list of templates [(col, kind, value)]"""
    temps = []
    for part in re.split(r'\) OR \(', sql.strip()[1:-1]):
        atoms = []
        for a in part.split(' AND '):
            a = a.strip()
            if a.endswith(' IS NOT NULL'): atoms.append((a[:-12], 'top', None))
            elif a.endswith(' IS NULL'): atoms.append((a[:-8], 'null', None))
            else:
                c, v = a.split(' = ', 1); atoms.append((c, 'const', v.strip("'")))
        temps.append(atoms)
    return temps

def qualifies(row, idx, temps):
    for atoms in temps:
        ok = True
        for c, kind, v in atoms:
            x = row[idx[c]]
            if (kind == 'top' and x is None) or (kind == 'null' and x is not None) or (kind == 'const' and x != v):
                ok = False; break
        if ok: return True
    return False

def main():
    ds, N = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40
    batch = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    R = json.load(open(os.path.join(HERE, 'results', f'{ds}.json')))['tables'][0]['conditional'][:N]
    path = os.path.join(DATA, DATASETS[ds]['file'])
    out = []
    for b in range(0, len(R), batch):
        keys = R[b:b + batch]
        t0 = time.time()
        store = [[] for _ in keys]
        with open(path, newline='', encoding='utf-8', errors='replace') as fh:
            r = csv.reader(line.replace('\0', '') for line in fh)
            cols = next(r); idx = {c: i for i, c in enumerate(cols)}
            parsed = [(parse(k['sql']), [idx[c] for c in k['K']]) for k in keys]
            total = 0
            for row in r:
                if len(row) != len(cols): continue
                total += 1
                row = [None if v.strip() == '' else v.strip() for v in row]
                for s, (temps, ki) in zip(store, parsed):
                    if qualifies(row, idx, temps): s.append(tuple(row[i] for i in ki))
        for k, s in zip(keys, store):
            Kc = list(range(len(k['K'])))
            flagged = violations(s, Kc, Kc, k['cls'], [True] * len(s))
            out.append(dict(K=k['K'], cls=k['cls'], condition=k['condition'], sql=k['sql'],
                            sample_support=k['support'], full_rows=total, full_scope=len(s),
                            full_support=round(len(s) / total, 3), violating_records=len(flagged),
                            holds_on_full=len(flagged) == 0))
            print(f"{'HOLDS ' if not flagged else 'FAILS '} {k['cls']:4s} {k['K']} | {k['condition'][:70]} | "
                  f"scope {len(s)}/{total} | violating records {len(flagged)}", flush=True)
        print(f'batch {b // batch + 1}: {time.time() - t0:.0f}s', flush=True)
    json.dump(out, open(os.path.join(HERE, 'results', f'{ds}-full-check.json'), 'w'), indent=1)
    print(f"holds on full data: {sum(o['holds_on_full'] for o in out)}/{len(out)}")

if __name__ == '__main__':
    main()
