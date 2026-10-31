"""Plan the STATS-CEB workload (Han et al., PVLDB 15(4), 2021; github.com/Nathaniel-Han/
End-to-End-CardEst-Benchmark, workloads/stats_CEB/stats_CEB.sql: 146 hand-picked join queries
over stats.stackexchange.com, read as data) on the Stack Exchange database of se_load.py with the
56 recommended filtered unique indexes, with enable_conditional_unique off, on, and on with
enable_conditional_unique_costing. Writes se_statsceb.json. Usage: python se_statsceb.py FILE DSN"""
import json, os, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))


def plan(cur, sql, on, costing):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute(f"set enable_conditional_unique_costing = {'on' if costing else 'off'}")
    cur.execute('explain (costs off) ' + sql)
    return [r[0] for r in cur.fetchall()]


def main():
    con = psycopg.connect(sys.argv[2], autocommit=True)
    cur = con.cursor()
    st, out = Counter(), []
    for line in open(sys.argv[1]):
        if '||' not in line: continue
        card, sql = line.split('||', 1)
        sql = sql.strip().rstrip(';')
        st['queries'] += 1
        try:
            cur.execute('begin read only')
            off, on, oc = plan(cur, sql, False, False), plan(cur, sql, True, False), plan(cur, sql, True, True)
            cur.execute('commit')
        except psycopg.Error as ex:
            cur.execute('rollback'); st['does not plan'] += 1
            out.append(dict(sql=sql, error=str(ex).splitlines()[0])); continue
        st['planned'] += 1
        if on != off: st['changed (default)'] += 1
        if oc != off: st['changed (with costing hint)'] += 1
        out.append(dict(sql=sql, changed=on != off, changed_costing=oc != off, plan_off=off, plan_on=on, plan_costing=oc))
    print(dict(st))
    json.dump(dict(stats=dict(st), queries=out), open(os.path.join(HERE, 'se_statsceb.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
