"""The 99 TPC-DS queries through a semantic layer of current-attribute views (SF1).

BI layers restate history with current attributes: each history-keeping dimension d is offered
as a view of the same name in schema sl,
  CREATE VIEW sl.d AS SELECT h.*, c.a1 AS cur_a1, ... FROM public.d h
    LEFT JOIN public.d c ON c.<business key> = h.<business key> AND c.<rec_end_date> IS NULL
so every query can report a dimension member under its current name. The queries run unchanged
(search_path = sl, public) and never ask for cur_* columns, so the self-join is removable iff the
planner knows the business key unique among current versions: the catalog is the primary keys
plus the five partial unique indexes UNIQUE (business key) WHERE rec_end_date IS NULL (level
'scd' of plan_overhead.py; the mined indexes are dropped).
Per query, three configurations: base (search_path = public, no views), views with
enable_conditional_unique off, views with it on. Recorded: planning time (median of 5), execution
time (EXPLAIN ANALYZE, TIMING OFF; after fetching the result as warm-up, median of 3; statement_timeout 60 s), scans of the
five dimensions in the plan, and whether the three return the same multiset (floats rounded to 6
digits). Writes tpcds_views.json. Usage: python tpcds_views.py WORKDIR DSN
Environment, for larger scale factors: VIEWS_RUNS (measured executions, default 3), VIEWS_TIMEOUT
(seconds, default 60), VIEWS_DIMS_ONLY=1 (skip queries that read no history-keeping dimension),
VIEWS_OUT (output file name, default tpcds_views.json)."""
import json, os, statistics, sys
from collections import Counter
import duckdb, psycopg, sqlglot
from sqlglot.optimizer.qualify import qualify
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plan_overhead import SCD, PK, catalog
RUNS = int(os.environ.get('VIEWS_RUNS', 3))
TIMEOUT = int(os.environ.get('VIEWS_TIMEOUT', 60))
DIMS_ONLY = os.environ.get('VIEWS_DIMS_ONLY') == '1'
OUT = os.environ.get('VIEWS_OUT', 'tpcds_views.json')

CURRENT = {'item': ['i_current_price', 'i_brand', 'i_class', 'i_category'],
           'store': ['s_store_name', 's_manager', 's_market_desc'],
           'call_center': ['cc_name', 'cc_manager'],
           'web_page': ['wp_type', 'wp_char_count'],
           'web_site': ['web_name', 'web_manager']}


def views(cur):
    cur.execute('drop schema if exists sl cascade'); cur.execute('create schema sl')
    for d, (bk, end) in SCD.items():
        attrs = ', '.join(f'c.{a} as cur_{a}' for a in CURRENT[d])
        cur.execute(f'create view sl.{d} as select h.*, {attrs} from public.{d} h '
                    f'left join public.{d} c on c.{bk} = h.{bk} and c.{end} is null')


def setup(cur, cfg):
    cur.execute('set search_path = ' + ('public' if cfg == 'base' else 'sl, public'))
    cur.execute(f"set enable_conditional_unique = {'on' if cfg == 'on' else 'off'}")


def explain(cur, sql, analyze):
    cur.execute(f"explain ({'analyze, timing off' if analyze else 'summary'}, format json) " + sql)
    return cur.fetchone()[0][0]


def scans(plan):
    n = Counter()
    def walk(p):
        if p.get('Relation Name') in SCD: n[p['Relation Name']] += 1
        for c in p.get('Plans', []): walk(c)
    walk(plan['Plan'])
    return sum(n.values())


def rows(cur, sql):
    cur.execute(sql)
    return Counter(tuple(round(v, 6) if isinstance(v, float) else v for v in r) for r in cur.fetchall())


def main():
    work, dsn = sys.argv[1], sys.argv[2]
    con = duckdb.connect(os.path.join(work, 'tpcds_sf1.duckdb'), read_only=True)
    schema = {}
    for t, c, ty in con.execute("select table_name, column_name, data_type from duckdb_columns() "
                                "where schema_name='main' order by table_name, column_index").fetchall():
        if t in PK: schema.setdefault(t, {})[c] = ty
    Q = json.load(open(os.path.join(work, 'queries.json')))
    pg = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
    out = []
    with pg.cursor() as cur:
        cur.execute('set max_parallel_workers_per_gather = 0'); cur.execute(f"set statement_timeout = '{TIMEOUT}s'")
        print('catalog:', catalog(cur, 'scd'), flush=True)
        views(cur)
        for n, q in Q:
            try:
                sql = qualify(sqlglot.parse_one(q, read='duckdb'), schema=schema, dialect='duckdb').sql(dialect='postgres')
            except Exception:
                continue
            uses = [d for d in SCD if f'"{d}"' in sql or f' {d} ' in sql or f' {d}\n' in sql]
            if DIMS_ONLY and not uses: continue
            r = dict(query=n, dims=uses)
            try:
                for cfg in ('base', 'off', 'on'):
                    setup(cur, cfg)
                    p = [explain(cur, sql, False) for _ in range(6)]
                    r[f'{cfg}_plan_ms'] = statistics.median(x['Planning Time'] for x in p[1:])
                    r[f'{cfg}_scans'] = scans(p[0])
                    r[f'{cfg}_rows'] = rows(cur, sql)          # also the warm-up
                    r[f'{cfg}_exec_ms'] = statistics.median(explain(cur, sql, True)['Execution Time'] for _ in range(RUNS))
            except psycopg.Error as ex:
                r['error'] = f'{type(ex).__name__}: {str(ex)[:120]}'
                print(f"q{n}: {r['error']}", flush=True); out.append(r); continue
            r['same'] = r['base_rows'] == r['off_rows'] == r['on_rows']
            for cfg in ('base', 'off', 'on'): del r[f'{cfg}_rows']
            out.append(r)
            print(f"q{n}: dims {','.join(uses) or '-'}; scans base/off/on {r['base_scans']}/{r['off_scans']}/{r['on_scans']}; "
                  f"exec ms {r['base_exec_ms']:.0f}/{r['off_exec_ms']:.0f}/{r['on_exec_ms']:.0f}; same {r['same']}", flush=True)
        cur.execute('drop schema sl cascade')
    json.dump(out, open(os.path.join(HERE, OUT), 'w'), indent=1)
    ok = [r for r in out if 'error' not in r]
    aff = [r for r in ok if r['off_scans'] > r['base_scans']]
    print(f"{len(ok)} queries ran, {len(out) - len(ok)} failed; {len(aff)} read a history-keeping dimension; "
          f"self-joins kept off {sum(r['off_scans'] - r['base_scans'] for r in aff)}, on {sum(r['on_scans'] - r['base_scans'] for r in aff)}; "
          f"results differ {sum(not r['same'] for r in ok)}", flush=True)
    if aff:
        so = sorted(r['off_exec_ms'] / r['on_exec_ms'] for r in aff)
        sb = sorted(r['on_exec_ms'] / r['base_exec_ms'] for r in aff)
        tot = lambda k: sum(r[k] for r in aff)
        print(f"affected: speed-up off->on median {statistics.median(so):.2f}x (min {so[0]:.2f}, max {so[-1]:.2f}); "
              f"on/base median {statistics.median(sb):.2f}; total ms base {tot('base_exec_ms'):.0f}, off {tot('off_exec_ms'):.0f}, on {tot('on_exec_ms'):.0f}", flush=True)


if __name__ == '__main__':
    main()
