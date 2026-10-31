"""X5 part A: what the declared filtered unique indexes do for the code-derived workload.

Input: sites_*.json (query sites with the SQL ActiveRecord generates, extracted from the
application sources) and the application schemas loaded on the patched server as databases
x5_<app> (x5_schema.py; GitLab from db/structure.sql). For every site with SQL:
  plan with enable_conditional_unique off and on (EXPLAIN, no data needed for the decision);
  changed   the plans differ;
  removed   a join of the original plan is gone;
  unique    a remaining join is newly marked Inner Unique (EXPLAIN VERBOSE);
  groupby   the GROUP BY key got shorter;
  proofs    uniqueness facts the prover established that the stock rules lack (its DEBUG1
            'implied' messages while planning with the setting on), whether or not the
            chosen plan uses them.
Elisions the extraction left in the SQL ('...', '<expr>') are replaced by neutral SQL listed in
x5_sql_fixes.json (counted); SQL that still does not plan is reported.
Writes x5_workload.json. Usage: python x5_workload.py DSNPREFIX   (e.g. 'host=localhost port=5444 user=ck')"""
import glob, json, os, re, sys
from collections import Counter, defaultdict
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))


NOTICES = []


def plan(cur, sql, on, verbose=False):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute(f"explain ({'verbose, ' if verbose else ''}costs off) " + sql)
    return [r[0] if isinstance(r[0], str) else r[0].decode() for r in cur.fetchall()]


def joins(p):
    return sum(bool(re.search(r'\b(Join|Nested Loop)\b', l)) for l in p)


def group_keys(p):
    return [l.split('Key:', 1)[1].strip() for l in p if re.search(r'(Group|Sort) Key:', l) and 'Group' in l]


def main():
    prefix = sys.argv[1]
    sites = []
    for f in sorted(glob.glob(os.path.join(HERE, 'sites_*.json'))):
        sites += json.load(open(f))
    fixes = json.load(open(os.path.join(HERE, 'x5_sql_fixes.json')))
    conns = {}
    res, st = [], Counter()
    for s in sites:
        st[f"sites {s['construct']}"] += 1
        sql = (s.get('sql') or '').strip().rstrip(';')
        if not sql or s['construct'] in ('lookup', 'none'): continue
        edits = [f for f in fixes if s['site'].startswith(f['site']) and f['old'] in sql]
        for f in edits: sql = sql.replace(f['old'], f['new'])
        if edits: st['sql repaired by hand (elisions)'] += 1
        app = s['app']
        if app not in conns:
            conns[app] = psycopg.connect(f'{prefix} dbname=x5_{app}', autocommit=True, prepare_threshold=None)
            conns[app].add_notice_handler(lambda d: NOTICES.append(d.message_primary))
        cur = conns[app].cursor()
        r = dict(s, sql_planned=sql, hand_edits=len(edits))
        try:
            off, on = plan(cur, sql, False), plan(cur, sql, True)
            voff = plan(cur, sql, False, True)
            cur.execute('set client_min_messages = debug1'); NOTICES.clear()
            von = plan(cur, sql, True, True)
            cur.execute('reset client_min_messages')
            r['proofs'] = sum('conditional unique: implied' in m for m in NOTICES)
        except psycopg.Error as ex:
            r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0]}'
            st['sql does not plan'] += 1; res.append(r); continue
        st['planned'] += 1
        r['changed'] = off != on
        r['removed'] = joins(on) < joins(off)
        r['unique'] = sum('Inner Unique: true' in l for l in von) > sum('Inner Unique: true' in l for l in voff)
        r['groupby'] = group_keys(on) != group_keys(off)
        r['plan_off'], r['plan_on'] = off, on
        if r['proofs']: st['proofs'] += 1; st[f"proofs {app}"] += 1
        for k in ('changed', 'removed', 'unique', 'groupby'):
            if r[k]: st[k] += 1; st[f"{k} {app}"] += 1
        res.append(r)
    print(json.dumps(st, indent=1, sort_keys=True))
    json.dump(res, open(os.path.join(HERE, os.environ.get('X5_OUT', 'x5_workload.json')), 'w'), indent=1)


if __name__ == '__main__':
    main()
