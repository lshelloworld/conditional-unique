"""Replan the SEDE queries whose plan the prover changes on a build that keeps the prover's logical
rewrites (join removal, semi-join reduction, DISTINCT and GROUP BY removal) but does not let a proof
over a partial index mark a join Inner Unique for costing (inst-norc: innerrel_is_unique as called
from add_paths_to_joinrel skips the prover). Each plan is compared with the stock plan (setting off)
and the plan with the full prover (se_workload.json). Writes se_norc.json. Usage: python se_norc.py DSN"""
import json, os, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from se_workload import plan


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True, prepare_threshold=None)
    cur = con.cursor()
    cur.execute('set statement_timeout = 10000')
    st, out = Counter(), []
    for q in json.load(open(os.path.join(HERE, 'se_workload.json'))):
        if not q.get('changed'): continue
        cur.execute('begin read only')
        p = plan(cur, q['sql'], True)
        cur.execute('commit')
        k = 'as stock' if p == q['plan_off'] else 'as full prover' if p == q['plan_on'] else 'third plan'
        st[k] += 1
        out.append(dict(id=q['id'], plan=k, plan_norc=p))
    print(dict(st))
    json.dump(out, open(os.path.join(HERE, 'se_norc.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
