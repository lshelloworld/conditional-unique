"""Mine keys on the generated TPC-DS dimension tables (discovery/ckminer.py) for audit.py: keys the
specification does not declare, unconditional ('mined-unc') and conditional ('mined'), each
re-checked on the full table; keys of up to three columns (two on tables over 20,000 rows).
customer_demographics (1.9M rows, a cross product of its attributes) and time_dim are skipped. Writes mined.json: {table: [{K, cls, temps}]} where temps
is a list of templates {column: 'T' | 'N' | ['C', value]} ([{}] for unconditional keys).
Each table is written to mined/TABLE.json as soon as it is done; with no TABLE.json left to
write, the parts are merged into mined.json. date_dim (73,049 rows, 28 columns) is mined for keys
of one column only: with two it had not finished after three hours.
Usage: python mine_tpcds.py WORKDIR [TABLE ...]"""
import json, os, sys, time
import duckdb
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'discovery'))
from ckminer import Table, mine_table, postprocess, verify

DIMS = ['call_center', 'catalog_page', 'customer', 'customer_address', 'date_dim', 'household_demographics',
        'income_band', 'item', 'promotion', 'reason', 'ship_mode', 'store', 'warehouse', 'web_page', 'web_site']
P = dict(kmax=3, minsup_rows=20, minsup_frac=0.03, max_const_card=12, max_const_card_narrow=30, narrow_cols=10,
         max_key_null=0.9, pair_cap=200000, max_involved=0.3, approx_pairs=0, time_budget=300)


KMAX = {'date_dim': 1}


def main():
    work = sys.argv[1]
    os.makedirs(os.path.join(HERE, 'mined'), exist_ok=True)
    con = duckdb.connect(os.path.join(work, 'tpcds_sf1.duckdb'), read_only=True)
    for t in sys.argv[2:] or DIMS:
        t0 = time.time()
        cols = [r[0] for r in con.execute('select column_name from duckdb_columns() where table_name = ? order by column_index', [t]).fetchall()]
        rows = [tuple(v.isoformat() if hasattr(v, 'isoformat') else (float(v) if hasattr(v, 'as_tuple') else v) for v in r)
                for r in con.execute(f'select * from {t}').fetchall()]
        T = Table(t, cols, rows, dict(P, minsup_rows=min(20, max(2, len(rows) // 10)),
                                      kmax=KMAX.get(t, 2 if len(rows) > 20000 else 3)))
        uncond, found, _ = mine_table(T)
        res = postprocess(T, uncond, found)
        keys = []
        for K, cls in uncond.items():
            if cls: keys.append(dict(K=list(K), cls=cls, temps=[{}], kind='unconditional'))
        for f in res:
            if verify(T, f, limit=10 ** 9) is False: continue
            temps = []
            for atoms in f['cond']:
                tp = {}
                for a in atoms:
                    c, kind, v, _, _ = T.atoms[a]
                    tp[c] = 'T' if kind == 'top' else 'N' if kind == 'null' else ['C', v]
                temps.append(tp)
            keys.append(dict(K=list(f['K']), cls=f['C'], temps=temps, kind='conditional'))
        json.dump(keys, open(os.path.join(HERE, 'mined', t + '.json'), 'w'), indent=1, default=str)
        print(f'{t}: {len(rows)} rows, {sum(k["kind"] == "unconditional" for k in keys)} unconditional and '
              f'{sum(k["kind"] == "conditional" for k in keys)} conditional keys, {time.time() - t0:.0f}s', flush=True)
    parts = {t: os.path.join(HERE, 'mined', t + '.json') for t in DIMS}
    if all(map(os.path.exists, parts.values())):
        json.dump({t: json.load(open(f)) for t, f in parts.items()}, open(os.path.join(HERE, 'mined.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
