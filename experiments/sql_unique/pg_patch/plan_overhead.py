"""Planning overhead and plan changes of the condunique patch on the 99 TPC-DS queries (SF1).

Catalogs of unique indexes added on top of the primary keys:
  scd    the business keys of the five history-keeping dimensions, unique among current
         versions: UNIQUE (i_item_id) WHERE i_rec_end_date IS NULL, etc.
  mined  scd + every key mined on the dimension tables that holds at SF1 and SF10
         (experiments/tpcds/mined.json, 'stable'), as a unique index with the key's condition
         as predicate (NULLS NOT DISTINCT for domain keys; possible, certain and candidate keys
         all imply nulls-distinct uniqueness; partial keys are skipped). A stress test: up to
         1,770 indexes on one table.
Per catalog and query: planning time with enable_conditional_unique off and on (3 warm-ups,
then 15 alternating pairs, medians), whether the plan changes, and for changed plans whether
both settings return the same multiset. Writes plan_overhead.json.
Usage: python plan_overhead.py WORKDIR DSN"""
import json, os, statistics, sys, time
from collections import Counter
import duckdb, psycopg, sqlglot
from sqlglot.optimizer.qualify import qualify
HERE = os.path.dirname(os.path.abspath(__file__))
TPCDS = os.path.join(HERE, '..', '..', 'tpcds')
sys.path.insert(0, TPCDS)
from load_tpcds import PK

SCD = {'item': ('i_item_id', 'i_rec_end_date'), 'store': ('s_store_id', 's_rec_end_date'),
       'call_center': ('cc_call_center_id', 'cc_rec_end_date'), 'web_page': ('wp_web_page_id', 'wp_rec_end_date'),
       'web_site': ('web_site_id', 'web_rec_end_date')}


def lit(v):
    return "'%s'" % str(v).replace("'", "''") if isinstance(v, str) else str(v)


def pred(temps):
    def atom(c, s):
        if s == 'T': return f'{c} IS NOT NULL'
        if s == 'N': return f'{c} IS NULL'
        return f'{c} = {lit(s[1])}'
    ds = [' AND '.join(atom(c, s) for c, s in tp.items()) for tp in temps if tp]
    return ' OR '.join(f'({d})' for d in ds) if ds else None


def catalog(cur, level):
    cur.execute("select indexname from pg_indexes where schemaname = 'public' and indexname like 'cu\\_%'")
    for (n,) in cur.fetchall(): cur.execute(f'drop index {n}')
    made = Counter()
    for t, (k, e) in SCD.items():
        cur.execute(f'create unique index cu_scd_{t} on {t} ({k}) where {e} is null'); made[t] += 1
    if level == 'mined':
        mined = json.load(open(os.path.join(TPCDS, 'mined.json')))
        for t, ms in mined.items():
            for i, m in enumerate(ms):
                if not m.get('stable') or m['cls'] == 'part': continue
                p = pred(m['temps'])
                nnd = ' nulls not distinct' if m['cls'] == 'dom' else ''
                sql = f"create unique index cu_{t}_{i} on {t} ({', '.join(m['K'])}){nnd}" + (f' where {p}' if p else '')
                try:
                    cur.execute(sql); made[t] += 1
                except psycopg.Error as ex:
                    print('  skipped', sql[:120], type(ex).__name__, flush=True)
    cur.execute('analyze')
    return dict(made)


def plan(cur, sql, on):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    t0 = time.perf_counter(); cur.execute('explain (format json, summary) ' + sql)
    j = cur.fetchone()[0][0]
    return j['Planning Time'], (time.perf_counter() - t0) * 1e3


def shape(cur, sql, on):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute('explain (costs off) ' + sql)
    return '\n'.join(r[0] if isinstance(r[0], str) else r[0].decode() for r in cur.fetchall())


def result(cur, sql, on):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute(sql)
    return Counter(map(tuple, cur.fetchall()))


def main():
    work, dsn = sys.argv[1], sys.argv[2]
    con = duckdb.connect(os.path.join(work, 'tpcds_sf1.duckdb'), read_only=True)
    schema = {}
    for t, c, ty in con.execute("select table_name, column_name, data_type from duckdb_columns() "
                                "where schema_name='main' order by table_name, column_index").fetchall():
        if t in PK: schema.setdefault(t, {})[c] = ty
    Q = json.load(open(os.path.join(work, 'queries.json')))
    pg = psycopg.connect(dsn, autocommit=True)
    out = {}
    with pg.cursor() as cur:
        cur.execute('set max_parallel_workers_per_gather = 0'); cur.execute("set statement_timeout = '300s'")
        sqls = []
        for n, q in Q:
            try:
                s = qualify(sqlglot.parse_one(q, read='duckdb'), schema=schema, dialect='duckdb').sql(dialect='postgres')
                cur.execute('explain ' + s); sqls.append((n, s))
            except Exception as ex:
                print(f'  q{n}: not plannable in PostgreSQL ({type(ex).__name__})', flush=True)
        for level in ('scd', 'mined'):
            t0 = time.time(); made = catalog(cur, level)
            print(f'{level}: {sum(made.values())} unique indexes added ({time.time() - t0:.0f}s): {made}', flush=True)
            rows = []
            for n, s in sqls:
                for _ in range(3): plan(cur, s, False); plan(cur, s, True)
                off, on = [], []
                for _ in range(15):
                    off.append(plan(cur, s, False)[0]); on.append(plan(cur, s, True)[0])
                r = dict(query=n, off_ms=statistics.median(off), on_ms=statistics.median(on))
                a, b = shape(cur, s, False), shape(cur, s, True)
                r['changed'] = a != b
                if r['changed']:
                    r['plan_off'], r['plan_on'] = a, b
                    try:
                        r['same_result'] = result(cur, s, False) == result(cur, s, True)
                    except psycopg.Error as ex:
                        r['same_result'] = None; print(f'  q{n}: {type(ex).__name__}', flush=True)
                rows.append(r)
            d = [r['on_ms'] - r['off_ms'] for r in rows]
            rel = sorted(r['on_ms'] / r['off_ms'] for r in rows)
            off = sorted(r['off_ms'] for r in rows)
            print(f"  {len(rows)} queries: planning off median {statistics.median(off):.2f} ms; "
                  f"overhead median {statistics.median(d):+.3f} ms, max {max(d):+.3f} ms; ratio median "
                  f"{statistics.median(rel):.3f}, p95 {rel[int(.95 * len(rel))]:.3f}; plans changed "
                  f"{sum(r['changed'] for r in rows)}, results differ "
                  f"{sum(r.get('same_result') is False for r in rows)}", flush=True)
            for r in rows:
                if r['changed']: print(f"  q{r['query']} changed, same result: {r.get('same_result')}", flush=True)
            out[level] = dict(indexes=made, queries=rows)
    json.dump(out, open(os.path.join(HERE, 'plan_overhead.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
