"""Do the plan changes that need a filtered key on real workloads need several indexes together?
Replans them on inst-one, an experiment-only build whose prover tries each premise index alone
(cu_decide calls cu_implies once per premise, plus once with none; restrictions, NOT NULL and
CHECK constraints still combine). Settings as in the workload runs: prover and costing hint on.
Each plan is compared with the stored plans and, as a control, with the full build in the same
statistics state (one_index_control.json): equal plans mean one index at a time suffices.
Queries: SEDE changes that need a recommended key (se_needs_key.json), Discourse changes that
need a filtered index (x11_workload.json changed, x11_workload_nopartial.json not), and the
changed application queries (x5_workload_gate.json). Writes ONE_OUT (default one_index.json);
run on the full build as well, as a control.
Usage: python one_index.py 'port=5444 user=ck' 'port=5477 user=ck'"""
import json, os, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
X = os.path.join(HERE, '..')


def plan(cur, sql):
    cur.execute('begin read only')
    cur.execute('set local enable_conditional_unique = on')
    cur.execute('set local enable_conditional_unique_costing = on')
    cur.execute('set local statement_timeout = 10000')
    cur.execute('explain (costs off) ' + sql)
    p = [r[0] for r in cur.fetchall()]
    cur.execute('commit')
    return p


def jobs():
    ids = set(json.load(open(os.path.join(X, 'stackexchange', 'se_needs_key.json'))))
    for q in json.load(open(os.path.join(X, 'stackexchange', 'se_workload.json'))):
        if q['id'] in ids: yield 'SEDE', 0, 'se', q['id'], q['sql'], q
    a = json.load(open(os.path.join(X, 'discourse', 'x11_workload.json')))
    b = json.load(open(os.path.join(X, 'discourse', 'x11_workload_nopartial.json')))
    nop = {r['sql_planned'] for r in b if r.get('changed')}
    for i, r in enumerate(a):
        if r.get('changed') and r['sql_planned'] not in nop:
            yield 'Discourse', 1, 'x11_discourse', i, r['sql_planned'], r
    for i, r in enumerate(json.load(open(os.path.join(X, 'apps', 'x5_workload_gate.json')))):
        if r.get('changed'): yield 'apps', 1, 'x5_' + r['app'], i, r['sql_planned'], r


def main():
    dsns = sys.argv[1:3]
    conns, st, out = {}, Counter(), []
    for wl, d, db, qid, sql, r in jobs():
        if (d, db) not in conns:
            conns[d, db] = psycopg.connect(f'{dsns[d]} dbname={db}', autocommit=True, prepare_threshold=None)
        p = plan(conns[d, db].cursor(), sql)
        k = 'as full prover' if p == r['plan_on'] else 'as stock' if p == r['plan_off'] else 'third plan'
        st[wl, k] += 1
        out.append(dict(workload=wl, id=qid, plan=k, plan_one=p))
    for k, v in sorted(st.items()): print(k, v)
    json.dump(out, open(os.path.join(HERE, os.environ.get('ONE_OUT', 'one_index.json')), 'w'), indent=1)


if __name__ == '__main__':
    main()
