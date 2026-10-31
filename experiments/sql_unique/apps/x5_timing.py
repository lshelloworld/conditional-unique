"""X5 part A, run times: fill the tables that the affected workload queries read with generated
rows and time each query with enable_conditional_unique off and on.

Affected queries: those of x5_workload.json whose plan changed or that got a new uniqueness
proof. Every table they read gets N rows from one INSERT ... SELECT over generate_series,
ON CONFLICT DO NOTHING, so all declared unique indexes (partial ones included) hold and rows
outside an index's scope repeat its key freely. Column values by type: integer columns that
the query compares with a constant 1..3, other *_id columns 1..N/4 (so joins find partners),
other integers 1..50, smallint 0..3, boolean, text from 1,000 words, nullable timestamps null
half of the time; columns with a default (serial keys) are left to it. Foreign keys and CHECK
constraints of the scratch schemas are dropped first (GitLab): they do not take part in the
uniqueness reasoning, and random rows would violate them. Per query: plan, median of five
EXPLAIN ANALYZE runs after two warm-ups, and the results of both settings compared as
multisets. Queries over 1 ms are re-timed by alternating() of ../discourse/x11_timing.py (11
rounds alternating off and on, first dropped). Reads X5_IN (default x5_workload.json), writes
X5_TIMING_OUT (default x5_timing.json). Usage: python x5_timing.py DSNPREFIX N"""
import json, os, re, statistics, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))


def tables(cur, sql):
    cur.execute('explain (verbose, format json) ' + sql)
    out = set()
    def walk(p):
        if 'Relation Name' in p: out.add((p.get('Schema', 'public'), p['Relation Name']))
        for c in p.get('Plans', []): walk(c)
    walk(cur.fetchone()[0][0]['Plan'])
    return out


def expr(name, typ, nullable, enum_first, n, fixed):
    if typ in ('smallint',): v = '(random() * 3)::int'
    elif typ in ('integer', 'bigint', 'numeric'):
        d = 2 if name in fixed else n // 4 if name.endswith('_id') else 49
        v = f"(1 + random() * {d})::int"
    elif typ == 'boolean': v = 'random() < 0.5'
    elif typ in ('text', 'character varying', 'citext'): v = "'w' || (random() * 1000)::int"
    elif typ.startswith('timestamp') or typ == 'date':
        v = "now() - random() * interval '1000 days'"
        if nullable: v = f'CASE WHEN random() < 0.5 THEN NULL ELSE {v} END'
    elif typ == 'jsonb' or typ == 'json': v = "'{}'"
    elif typ == 'ARRAY': v = "'{}'"
    elif typ == 'bytea': v = "'\\x00'::bytea"
    elif typ == 'uuid': v = 'gen_random_uuid()'
    elif typ == 'USER-DEFINED' and enum_first: v = f"'{enum_first}'"
    elif nullable: return None
    else: v = "'0'"
    return v


def fill(cur, schema, table, n, fixed):
    cur.execute("""select c.column_name, c.data_type, c.is_nullable = 'YES', c.column_default is not null,
                          (select e.enumlabel from pg_enum e join pg_type t on t.oid = e.enumtypid
                           where t.typname = c.udt_name order by e.enumsortorder limit 1)
                   from information_schema.columns c where c.table_schema = %s and c.table_name = %s
                   order by c.ordinal_position""", (schema, table))
    cols, exprs = [], []
    for name, typ, nullable, has_default, enum_first in cur.fetchall():
        if has_default: continue
        e = expr(name, typ, nullable, enum_first, n, fixed)
        if e is None: continue
        cols.append(f'"{name}"'); exprs.append(e)
    cur.execute(f'truncate {schema}."{table}" cascade')
    cur.execute(f'insert into {schema}."{table}" ({", ".join(cols)}) select {", ".join(exprs)} '
                f'from generate_series(1, {n}) on conflict do nothing')
    cur.execute(f'analyze {schema}."{table}"')
    cur.execute(f'select count(*) from {schema}."{table}"')
    return cur.fetchone()[0]


def timed(cur, sql, on):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    for _ in range(2): cur.execute(sql); cur.fetchall()
    ts = []
    for _ in range(5):
        cur.execute('explain (analyze, format json) ' + sql); ts.append(cur.fetchone()[0][0]['Execution Time'])
    cur.execute('explain (costs off) ' + sql)
    plan = [r[0] if isinstance(r[0], str) else r[0].decode() for r in cur.fetchall()]
    cur.execute(sql)
    rows = [tuple(json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v for v in t) for t in cur.fetchall()]
    return statistics.median(ts), plan, Counter(rows)          # json columns are unhashable


def main():
    prefix, n = sys.argv[1], int(sys.argv[2])
    W = [x for x in json.load(open(os.path.join(HERE, os.environ.get('X5_IN', 'x5_workload.json'))))
         if 'error' not in x and (x.get('changed') or x.get('proofs'))]
    out = []
    for x in W:
        con = psycopg.connect(f"{prefix} dbname=x5_{x['app']}", autocommit=True, prepare_threshold=None)
        cur = con.cursor()
        cur.execute('set max_parallel_workers_per_gather = 0'); cur.execute("set statement_timeout = '120s'")
        sql = x['sql_planned']
        r = dict(app=x['app'], site=x['site'], index=x['index'], construct=x['construct'], sql=sql)
        fixed = {m.group(1) for m in re.finditer(r'"?(\w+)"?\s*(?:=|IN \()\s*(?:-?\d+|TRUE|FALSE)\b', sql)}
        try:
            for s, t in tables(cur, sql):
                cur.execute("""select conname from pg_constraint where conrelid = %s::regclass and contype in ('f', 'c')""", (f'{s}."{t}"',))
                for (c,) in cur.fetchall(): cur.execute(f'alter table {s}."{t}" drop constraint "{c}"')
                cur.execute("""select conrelid::regclass::text, conname from pg_constraint where confrelid = %s::regclass and contype = 'f'""", (f'{s}."{t}"',))
                for (rel, c) in cur.fetchall(): cur.execute(f'alter table {rel} drop constraint "{c}"')
            r['rows'] = {t: fill(cur, s, t, n, fixed) for s, t in tables(cur, sql)}
            r['off_ms'], r['plan_off'], a = timed(cur, sql, False)
            r['on_ms'], r['plan_on'], b = timed(cur, sql, True)
            r['same_result'] = a == b; r['result_rows'] = sum(a.values())
            r['plan_changed'] = r['plan_off'] != r['plan_on']
            r['speedup'] = r['off_ms'] / r['on_ms'] if r['on_ms'] else None
            if r['off_ms'] >= 1:
                sys.path.insert(0, os.path.join(HERE, '..', 'discourse'))
                from x11_timing import alternating
                r['off_alt_ms'], r['on_alt_ms'] = alternating(cur, sql)
                r['speedup_alt'] = r['off_alt_ms'] / r['on_alt_ms']
            print(f"{x['app']:8s} {x['site'][-55:]:55s} rows {r['result_rows']:7d}  off {r['off_ms']:8.1f} ms  on {r['on_ms']:8.1f} ms  "
                  f"{r['speedup']:5.2f}x  plan changed {r['plan_changed']}  same {r['same_result']}", flush=True)
        except psycopg.Error as ex:
            r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0]}'
            print(f"{x['app']:8s} {x['site'][-55:]:55s} ERROR {r['error'][:80]}", flush=True)
        out.append(r)
        con.close()
    json.dump(out, open(os.path.join(HERE, os.environ.get('X5_TIMING_OUT', 'x5_timing.json')), 'w'), indent=1)


if __name__ == '__main__':
    main()
