"""Tables of the second data folder (the HPI dependency-discovery benchmarks: UCI tables, flight,
plista, cd). The files differ in separator, header and null marker, so each has its own entry.
Values are stripped; the null markers (empty string, '?') become None. Rows with the wrong
number of fields are skipped; a trailing empty field (horse) is cut. Files without a header get
columns c0, c1, ... Usage as a library: cols, rows = load2(name, keep=None)."""
import csv, json, os

DATA2 = os.environ.get('CU_DATA2', 'data/sets2')
DATASETS2 = {
    'adult':    dict(file='adult.csv', table='uci.adult', sep=';', header=False),
    'chess':    dict(file='chess.csv', table='uci.chess', sep=',', header=False),
    'flight':   dict(file='flight_1k.csv', table='hpi.flight', sep=';', header=True),
    'plista':   dict(file='plista_20000r_40c.csv', table='hpi.plista', sep=';', header=False),
    'cd':       dict(file='cd.csv', table='hpi.cd', sep=';', header=True),
    'horse':    dict(file='horse.csv', table='uci.horse', sep=';', header=False, width=28),
    'hepatitis': dict(file='hepatitis.csv', table='uci.hepatitis', sep=',', header=False),
    'breast':   dict(file='breast-cancer-wisconsin.csv', table='uci.breast', sep=',', header=False),
    'bridges':  dict(file='bridges.csv', table='uci.bridges', sep=',', header=False),
}
NULLS = {'', '?'}
# Sampled LakeBench OpenData tables (lakebench_tables.json, built by the session's screening
# step): comma-separated with a header; NA-like strings are NULL too.
LB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lakebench_tables.json')
if os.path.exists(LB):
    DATASETS2.update(json.load(open(LB)))
LB_NULLS = {'na', 'n/a', 'null', 'none', 'nan', '-'}


def clean_cols(cols):
    out = []
    for i, c in enumerate(cols):
        c = c.replace('"', '').replace('\ufeff', '').strip()
        # PostgreSQL cuts identifiers at 63 bytes: cut at 56 so the suffix below stays unique
        c = c.encode('utf-8')[:56].decode('utf-8', 'ignore').strip() or f'c{i}'
        while c in out: c = f'{c}_{i}'
        out.append(c)
    return out
csv.field_size_limit(10 ** 9)


def load2(name, keep=None):
    cfg = DATASETS2[name]
    with open(os.path.join(DATA2, cfg['file']), newline='', encoding='utf-8', errors='replace') as fh:
        r = csv.reader((line.replace('\0', '') for line in fh), delimiter=cfg['sep'])
        first = next(r)
        width = cfg.get('width') or len(first)
        if cfg['header']:
            cols, pending = clean_cols(first[:width]), []
        else:
            cols, pending = [f'c{i}' for i in range(width)], [first]
        ki = [cols.index(c) for c in keep] if keep else list(range(width))
        rows = []
        for row in pending + list(r):
            if len(row) > width and all(v.strip() == '' for v in row[width:]): row = row[:width]
            if len(row) != width: continue
            nulls = NULLS | LB_NULLS if cfg.get('lakebench') else NULLS
            rows.append(tuple(None if row[i].strip() in nulls or row[i].strip().lower() in nulls else row[i].strip() for i in ki))
    return [cols[i] for i in ki], rows


if __name__ == '__main__':
    for n in DATASETS2:
        c, rs = load2(n)
        nulls = sum(v is None for r in rs for v in r)
        print(f'{n:10s} {len(rs):6d} rows {len(c):4d} cols {nulls / max(1, len(rs) * len(c)):6.1%} nulls')
