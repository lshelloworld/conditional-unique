"""Mark the mined keys of mined.json that also hold on TPC-DS at a second scale factor ('stable'),
i.e. that are likely invariants of the generator rather than accidents of one instance. A key is
checked by counting violating pairs per class in DuckDB (pairs of distinct records are
identified by the table's surrogate key). Usage: python stable.py WORKDIR SF"""
import json, os, sys
import duckdb
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from load_tpcds import PK


def pred(temps):
    def atom(c, s):
        if s == 'T': return f'{c} IS NOT NULL'
        if s == 'N': return f'{c} IS NULL'
        v = s[1]
        return "%s = '%s'" % (c, v.replace("'", "''")) if isinstance(v, str) else f'{c} = {v}'
    ds = [' AND '.join(atom(c, s) for c, s in tp.items()) for tp in temps if tp]
    return ' OR '.join(f'({d})' for d in ds) if ds else 'TRUE'


def holds(con, t, K, cls, temps):
    P = pred(temps); Kc = ', '.join(K)
    if cls == 'nn': return con.execute(f"select count(*) from {t} where ({P}) and not ({' AND '.join(f'{k} IS NOT NULL' for k in K)})").fetchone()[0] == 0
    if cls in ('cand',) and con.execute(f"select count(*) from {t} where ({P}) and not ({' AND '.join(f'{k} IS NOT NULL' for k in K)})").fetchone()[0]:
        return False
    if cls in ('pos', 'dom', 'cand'):
        nn = '' if cls != 'pos' else ' AND ' + ' AND '.join(f'{k} IS NOT NULL' for k in K)
        return con.execute(f'select count(*) from (select 1 from {t} where ({P}){nn} group by {Kc} having count(*) > 1)').fetchone()[0] == 0
    # part / cert: pairs of distinct rows compatible (cert) or subsumed (part) on K
    a = ' AND '.join(f'(x.{k} = y.{k} OR x.{k} IS NULL OR y.{k} IS NULL)' for k in K) if cls == 'cert' else \
        '((' + ' AND '.join(f'(x.{k} IS NULL OR x.{k} = y.{k})' for k in K) + ') OR (' + ' AND '.join(f'(y.{k} IS NULL OR x.{k} = y.{k})' for k in K) + '))'
    pk = PK[t][0]                                         # the dimensions have a surrogate key
    q = (f'select count(*) from (select * from {t} where ({P})) x, '
         f'(select * from {t} where ({P})) y where x.{pk} < y.{pk} and {a}')
    return con.execute(q).fetchone()[0] == 0


def main():
    work, sf = sys.argv[1], sys.argv[2]
    con = duckdb.connect(os.path.join(work, f'tpcds_sf{sf}.duckdb'), read_only=True)
    M = json.load(open(os.path.join(HERE, 'mined.json')))
    for t, keys in M.items():
        n = con.execute(f'select count(*) from {t}').fetchone()[0]
        for k in keys:
            if n > 200000 and k['cls'] in ('part', 'cert'): k['stable'] = None; continue
            k['stable'] = holds(con, t, k['K'], k['cls'], k['temps'])
        print(t, n, 'rows:', sum(k['stable'] is True for k in keys), 'of', len(keys), 'hold at SF', sf, flush=True)
    json.dump(M, open(os.path.join(HERE, 'mined.json'), 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
