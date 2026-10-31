"""Time the SEDE queries whose plan changes (se_workload.json) with enable_conditional_unique off
and on, on the loaded stats.stackexchange.com data with the recommended keys declared.

Per query: EXPLAIN ANALYZE (TIMING OFF) medians of 10 rounds alternating the setting after a
warm-up round (alternating() of ../discourse/x11_timing.py), and the results compared as
multisets in one read-only transaction without a trailing LIMIT (same_result(), ties). Queries
that take over 30 s are skipped. 'needs_key' marks the changes that need a recommended filtered
key (the plan differs from se_workload_nokeys.json). Writes se_timing.json.
Usage: python se_timing.py DSN"""
import json, os, sys
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'discourse'))
from x11_timing import alternating, same_result


def main():
    k = lambda x: (x['id'], x['sql'])
    base = {k(x): x for x in json.load(open(os.path.join(HERE, 'se_workload_nokeys.json'))) if 'error' not in x}
    W = [x for x in json.load(open(os.path.join(HERE, 'se_workload.json'))) if 'error' not in x and x['changed']]
    con = psycopg.connect(sys.argv[1], autocommit=True, prepare_threshold=None)
    cur = con.cursor()
    cur.execute('set max_parallel_workers_per_gather = 0'); cur.execute("set statement_timeout = '30s'")
    cur.execute('set default_transaction_read_only = on')
    out = []
    for x in W:
        r = dict(id=x['id'], title=x['title'], sql=x['sql'],
                 needs_key=k(x) not in base or base[k(x)]['plan_on'] != x['plan_on'])
        try:
            r['off_ms'], r['on_ms'] = alternating(cur, x['sql'])
            r['speedup'] = r['off_ms'] / r['on_ms'] if r['on_ms'] else None
            r['same_result'], r['rows'] = same_result(cur, x['sql'])
        except psycopg.Error as ex:
            cur.execute('rollback') if con.info.transaction_status else None
            r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0][:120]}'
        out.append(r)
        if 'error' in r:
            print(f"{x['id']:7d} ERROR {r['error'][:80]}", flush=True)
        else:
            print(f"{x['id']:7d} {'key' if r['needs_key'] else 'pk '} off {r['off_ms']:9.1f} on {r['on_ms']:9.1f} "
                  f"{r['speedup']:5.2f}x same {r['same_result']} {x['title'][:50]}", flush=True)
    json.dump(out, open(os.path.join(HERE, os.environ.get('SE_OUT', 'se_timing.json')), 'w'), indent=1)


if __name__ == '__main__':
    main()
