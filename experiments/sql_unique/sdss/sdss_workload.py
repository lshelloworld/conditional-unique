"""Plan the SkyServer queries (sdss_log.json) on the SDSS schema of sdss_schema.py with
enable_conditional_unique off, on, and on with enable_conditional_unique_costing.

Preparation as for SEDE (../stackexchange/se_workload.py: one read-only SELECT, parameters and
variables substituted, T-SQL translated by sqlglot), then quoted identifiers are lower-cased (T-SQL
names are case-insensitive) and dbo. is dropped before anything but a function call. Per query:
whether each plan differs from the stock plan, joins removed, GROUP BY keys shortened, DISTINCT or
aggregation removed, Inner Unique added, and whether the query names PhotoObjAll's documented
conditional key (thingID among primary objects). Hexadecimal constants (flag masks) become
integers before translation, and unqualified function names resolve in dbo. Writes OUT (default sdss_workload.json).
Usage: python sdss_workload.py DSN [OUT]"""
import json, os, re, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'stackexchange'))
from se_workload import prepare, joins, gkeys, aggs


def fix(sql):
    sql = re.sub(r'"([^"]+)"', lambda m: '"' + m.group(1).lower() + '"', sql)
    return re.sub(r'\bdbo\.(?!\w+\s*\()', '', sql, flags=re.I)


def plan(cur, sql, on, costing, verbose=False):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute(f"set enable_conditional_unique_costing = {'on' if costing else 'off'}")
    cur.execute(f"explain ({'verbose, ' if verbose else ''}costs off) " + sql)
    return [r[0] for r in cur.fetchall()]


def main():
    dsn = sys.argv[1]
    out_name = sys.argv[2] if len(sys.argv) > 2 else 'sdss_workload.json'
    con = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
    cur = con.cursor()
    cur.execute('set statement_timeout = 10000')
    cur.execute('set search_path = public, dbo')
    seen, res, st = set(), [], Counter()
    for q in json.load(open(os.path.join(HERE, 'sdss_log.json'))):
        st['statements'] += 1
        sql = prepare(re.sub(r'\b0x([0-9a-f]+)\b', lambda m: str(int(m.group(1), 16)), q['sql'], flags=re.I))
        if sql is None: st['not one read-only SELECT, or untranslatable'] += 1; continue
        sql = fix(sql)
        key = re.sub(r'\s+', ' ', sql.lower())
        if key in seen: st['duplicate after preparation'] += 1; continue
        seen.add(key)
        r = dict(sql=sql, runs=q['runs'], thingid_primary=bool(re.search(r'thingid', sql, re.I)) and
                 bool(re.search(r'photoprimary|galaxy|star\b|mode\s*=\s*1', sql, re.I)))
        try:
            cur.execute('begin read only')
            off, on, oc = plan(cur, sql, False, False), plan(cur, sql, True, False), plan(cur, sql, True, True)
            voff, voc = plan(cur, sql, False, False, True), plan(cur, sql, True, True, True)
            cur.execute('commit')
        except psycopg.Error as ex:
            cur.execute('rollback')
            r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0][:140]}'
            st['does not plan'] += 1; res.append(r); continue
        st['planned'] += 1
        r.update(changed=off != on, changed_costing=off != oc, removed=joins(on) < joins(off),
                 groupby=gkeys(on) != gkeys(off), distinct=aggs(on) < aggs(off),
                 unique=sum('Inner Unique: true' in l for l in voc) > sum('Inner Unique: true' in l for l in voff),
                 plan_off=off, plan_on=on, plan_costing=oc)
        for k in ('changed', 'changed_costing', 'removed', 'groupby', 'distinct', 'unique', 'thingid_primary'):
            if r[k]: st[k] += 1
        if re.search(r'\bdistinct\b|\bgroup by\b|\bleft join\b', sql, re.I): st['has DISTINCT, GROUP BY or LEFT JOIN'] += 1
        res.append(r)
    print(json.dumps(st, indent=1))
    json.dump(res, open(os.path.join(HERE, out_name), 'w'), indent=1)


if __name__ == '__main__':
    main()
