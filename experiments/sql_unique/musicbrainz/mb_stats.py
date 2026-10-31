"""MusicBrainz on real data: what the 17 filtered unique indexes cover, and what the prover's plan
changes cost or gain.

Per filtered index (loaded tables only): rows in the table, rows in the index's scope, and a
check that its key is unique in the scope. Per constructed query of mb_plan.py whose plan
changes: execution time with enable_conditional_unique off and on (EXPLAIN ANALYZE, TIMING OFF;
medians of 10 rounds alternating the setting after one warm-up round) and both results compared
as multisets in one read-only transaction. Writes mb_stats.json. Usage: python mb_stats.py DSN"""
import json, os, statistics, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True, prepare_threshold=None)
    cur = con.cursor()
    cur.execute('set search_path = musicbrainz, public'); cur.execute('set max_parallel_workers_per_gather = 0')
    cur.execute("""select c.relname, i.relname, pg_get_indexdef(x.indexrelid), pg_get_expr(x.indpred, x.indrelid),
                          array(select a.attname from unnest(x.indkey) k join pg_attribute a on a.attrelid = c.oid and a.attnum = k)
                   from pg_index x join pg_class i on i.oid = x.indexrelid join pg_class c on c.oid = x.indrelid
                   join pg_namespace n on n.oid = c.relnamespace
                   where n.nspname = 'musicbrainz' and x.indisunique and x.indpred is not null order by 1, 2""")
    idx = []
    for t, name, ddl, pred, cols in cur.fetchall():
        cur.execute(f'select count(*) from {t}'); n = cur.fetchone()[0]
        cur.execute(f'select count(*) from {t} where {pred}'); s = cur.fetchone()[0]
        k = ', '.join(cols)
        cur.execute(f'select count(*) from (select {k} from {t} where {pred} group by {k} having count(*) > 1) d'); dup = cur.fetchone()[0]
        idx.append(dict(table=t, index=name, predicate=pred, key=cols, rows=n, scope=s, duplicate_keys=dup))
        print(f'{name:32s} rows {n:9d} scope {s:9d} ({100 * s / n if n else 0:5.1f}%) duplicates {dup}', flush=True)
    timed = []
    for q in json.load(open(os.path.join(HERE, 'mb_plan.json'))):
        if q['kind'] != 'cq' or not q.get('changed'):
            continue
        ms = {'off': [], 'on': []}
        cur.execute('begin read only')
        for rnd in range(11):
            for v in ('off', 'on'):
                cur.execute(f'set local enable_conditional_unique = {v}')
                cur.execute('explain (analyze, timing off, format json) ' + q['sql'])
                if rnd: ms[v].append(cur.fetchone()[0][0]['Execution Time'])
                else: cur.fetchone()
        res = {}
        for v in ('off', 'on'):
            cur.execute(f'set local enable_conditional_unique = {v}'); cur.execute(q['sql'])
            res[v] = Counter(map(tuple, cur.fetchall()))
        cur.execute('rollback')
        r = dict(origin=q['origin'], off_ms=statistics.median(ms['off']), on_ms=statistics.median(ms['on']),
                 rows=sum(res['off'].values()), same=res['off'] == res['on'])
        r['speedup'] = r['off_ms'] / r['on_ms']
        timed.append(r)
        print(f"{r['origin'][:60]:60s} rows {r['rows']:8d} off {r['off_ms']:9.1f} on {r['on_ms']:9.1f} {r['speedup']:5.2f}x same {r['same']}", flush=True)
    json.dump(dict(indexes=idx, timed=timed), open(os.path.join(HERE, 'mb_stats.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
