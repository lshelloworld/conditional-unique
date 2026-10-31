"""Query-optimisation experiment for discovered conditional keys (PostgreSQL).

For every case (a conditional key C:K(K) with scope predicate P on table t) and every query
template below we run
  - the original query, and the rewrite an optimiser that knows C:K(K) may apply;
  - under three physical configurations: no index ('none'), a plain btree on K ('idx'),
    and the conditional key enforced as filtered unique index(es) ('uq');
and record: execution and planning time (EXPLAIN ANALYZE, median of repeated runs), whether
PostgreSQL's own plan for the original already avoids the redundant operator, and whether the
rewrite returns the same multiset of rows. As a control, the same rewrite is also checked
WITHOUT the predicate, where the key does not hold and the rewrite should be wrong.

Templates (X = a non-key payload column of t):
  DISTINCT   SELECT DISTINCT K FROM t WHERE P             ->  SELECT K FROM t WHERE P
  GROUPBY    SELECT K, count(*) FROM t WHERE P GROUP BY K  ->  SELECT K, 1 FROM t WHERE P
  LEFTJOIN   SELECT a.K, a.X FROM t a LEFT JOIN t b ON a.K = b.K AND P(b)
                                                         ->  SELECT a.K, a.X FROM t a
  SEMIJOIN   SELECT a.K, a.X FROM t a WHERE EXISTS (SELECT 1 FROM t b WHERE b.K = a.K AND P(b))
                                                         ->  SELECT a.K, a.X FROM t a JOIN t b ON ... AND P(b)
Licensed by the class (Table "Rewrites" of the paper): DISTINCT/GROUPBY need a domain key
(also implied by certain and candidate keys); LEFTJOIN/SEMIJOIN need a possible key.
For the GROUP BY trap cases (possible key only) the DISTINCT/GROUPBY rewrites are NOT licensed
and are run to show that they change the result.
"""
import argparse, json, os, statistics, sys, time
from collections import Counter
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'discovery'))
sys.path.insert(0, HERE)
from ckminer import load_export
from cases import cases, CSV_COLS
sys.path.insert(0, os.path.join(HERE, '..', '..', 'discovery'))

DATA = os.environ.get('CU_EXPORTS', 'data/exports')
RANK = {'pos': 0, 'dom': 1, 'part': 2, 'cert': 3, 'cand': 4}

def q(c): return f'"{c}"'

def load_tables(conn, needed, scale=1, keycols=None):
    """load each table `scale` times; replica r adds r*OFFSET to every non-null value of the
    key columns of the cases on that table, so keys, scopes and null patterns are preserved
    within each replica and replicas never collide"""
    import glob
    with conn.cursor() as cur:
        for ds, table in sorted(needed):
            if ds in CSV_COLS:          # plaintext datasets at their real scale, text columns
                from run_csv import load_csv, DATA as CSVDATA, DATASETS
                cols, rows = load_csv(os.path.join(CSVDATA, DATASETS[ds]['file']), 0, 7, CSV_COLS[ds])
                name, typ, rep = f'{ds}.{table}', 'text', 1
            else:
                prefix = 'Hockey' if ds == 'hockey' else 'voc'
                path = glob.glob(os.path.join(DATA, ds, f'{prefix}.{table}-*-full.json'))[0]
                name, cols, rows = load_export(path)
                typ, rep = 'bigint', scale
            tn = q(f'{ds}_{table}')
            cur.execute(f'DROP TABLE IF EXISTS {tn} CASCADE')
            cur.execute(f'CREATE TABLE {tn} (' + ', '.join(f'{q(c)} {typ}' for c in cols) + ')')
            with cur.copy(f'COPY {tn} ({", ".join(q(c) for c in cols)}) FROM STDIN') as cp:
                kc = keycols.get(table, set()) if keycols else set()
                ki = [i for i, c in enumerate(cols) if c in kc]
                OFF = 1000003
                for k_rep in range(rep):
                    for r in rows:
                        if k_rep and ki:
                            r = list(r)
                            for i in ki:
                                if r[i] is not None: r[i] = ((r[i] + k_rep * OFF + 2**63) % 2**64) - 2**63
                        cp.write_row(r)
            cur.execute(f'ANALYZE {tn}')
            print(f'loaded {name}: {len(rows) * rep} rows (x{rep})', flush=True)
    conn.commit()

def columns(conn, tn):
    with conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position", (tn,))
        return [r[0] for r in cur.fetchall()]

def templates(t, K, X, P):
    Kc = ', '.join(q(c) for c in K)
    aK = ', '.join(f'a.{q(c)}' for c in K)
    on = ' AND '.join(f'a.{q(c)} = b.{q(c)}' for c in K)
    Pb = ' '.join(('b.' + w if w.startswith('"') else w) for w in P.split(' '))
    return {
        'DISTINCT': (f'SELECT DISTINCT {Kc} FROM {t} WHERE {P}',
                     f'SELECT {Kc} FROM {t} WHERE {P}', 'dom'),
        'GROUPBY':  (f'SELECT {Kc}, count(*) AS n FROM {t} WHERE {P} GROUP BY {Kc}',
                     f'SELECT {Kc}, 1 AS n FROM {t} WHERE {P}', 'dom'),
        'LEFTJOIN': (f'SELECT {aK}, a.{q(X)} FROM {t} a LEFT JOIN {t} b ON {on} AND {Pb}',
                     f'SELECT {aK}, a.{q(X)} FROM {t} a', 'pos'),
        'SEMIJOIN': (f'SELECT {aK}, a.{q(X)} FROM {t} a WHERE EXISTS (SELECT 1 FROM {t} b WHERE {on} AND {Pb})',
                     f'SELECT {aK}, a.{q(X)} FROM {t} a JOIN {t} b ON {on} AND {Pb}', 'pos'),
    }

def unpredicated(sql, P, Pb):
    return sql.replace(f' AND {Pb}', '').replace(f' WHERE {P}', '')

def indexes(case, t, cur=None):
    K, P, cls = case['K'], case['P'], case['cls']
    Kc = ', '.join(q(c) for c in K)
    if cls in ('cand', 'pos'):
        return [f'CREATE UNIQUE INDEX ON {t} ({Kc}) WHERE {P}']
    if cls == 'dom':
        return [f'CREATE UNIQUE INDEX ON {t} ({Kc}) NULLS NOT DISTINCT WHERE {P}']
    if cls == 'cert':
        # one filtered unique index per null pattern of the key columns that are nullable in the
        # scope; the cross-pattern check would be a trigger (not needed here, the data satisfies
        # the key), so the planner sees the unique indexes only
        import itertools
        cur.execute(f'SELECT ' + ', '.join(f'count(*) FILTER (WHERE {q(c)} IS NULL)' for c in K) + f' FROM {t} WHERE {P}')
        counts = cur.fetchone()
        nullable = [c for c, n in zip(K, counts) if n]
        out = []
        for r in range(len(nullable) + 1):
            for S in itertools.combinations(nullable, r):
                rest = [c for c in K if c not in S]
                cols = ', '.join(q(c) for c in rest) if rest else '(1)'
                cond = ' AND '.join([P] + [f'{q(c)} IS NULL' for c in S] +
                                    [f'{q(c)} IS NOT NULL' for c in nullable if c not in S])
                out.append(f'CREATE UNIQUE INDEX ON {t} ({cols}) WHERE {cond}')
        return out

def explain(cur, sql, reps):
    plans = []
    for _ in range(reps):
        cur.execute('EXPLAIN (ANALYZE, FORMAT JSON) ' + sql)
        plans.append(cur.fetchone()[0][0])
    ex = statistics.median(p['Execution Time'] for p in plans)
    pl = statistics.median(p['Planning Time'] for p in plans)
    return ex, pl, plans[0]['Plan']

def node_types(plan):
    out = [plan['Node Type']]
    for p in plan.get('Plans', []): out += node_types(p)
    return out

def joins(plan):
    out = []
    if 'Join Type' in plan: out.append((plan['Join Type'], plan.get('Inner Unique', False)))
    for p in plan.get('Plans', []): out += joins(p)
    return out

def redundant_gone(tmpl, plan):
    """does PostgreSQL's plan for the ORIGINAL query already avoid the redundant work?"""
    nodes = node_types(plan)
    if tmpl in ('DISTINCT', 'GROUPBY'):
        return not any(n in ('Aggregate', 'Unique', 'HashAggregate', 'GroupAggregate') for n in nodes)
    if tmpl == 'LEFTJOIN':                      # join removal
        return not joins(plan)
    if tmpl == 'SEMIJOIN':                      # semi-join executed as a unique inner join
        return all(jt == 'Inner' or (jt == 'Semi' and uniq) for jt, uniq in joins(plan)) and bool(joins(plan))
    return None

def rows(cur, sql):
    cur.execute(sql); return Counter(cur.fetchall())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dsn', default='host=localhost port=5444 user=ck dbname=ckqo')
    ap.add_argument('--reps', type=int, default=9)
    ap.add_argument('--scale', type=int, default=1)
    ap.add_argument('--datasets', default='hockey,voc')
    ap.add_argument('--out', default=os.path.join(HERE, 'results_qo.json'))
    a = ap.parse_args()
    conn = psycopg.connect(a.dsn)
    C = [c for c in cases() if c['ds'] in a.datasets.split(',')]
    keycols = {}
    for c in C: keycols.setdefault(c['table'], set()).update(c['K'])
    for c in C:   # never offset a column that a scope predicate compares with a constant
        if '=' in c['P']: keycols[c['table']].discard(c['P'].split('"')[1])
    load_tables(conn, {(c['ds'], c['table']) for c in C}, a.scale, keycols)
    results = []
    with conn.cursor() as cur:
        for case in C:
            t = q(f"{case['ds']}_{case['table']}")
            cols = columns(conn, f"{case['ds']}_{case['table']}")
            X = next(c for c in cols if c not in case['K'] and c not in case['P'])
            P = case['P']
            T = templates(t, case['K'], X, P)
            Pb = ' '.join(('b.' + w if w.startswith('"') else w) for w in P.split(' '))
            for tmpl, (orig, rew, needs) in T.items():
                licensed = RANK[case['cls']] >= RANK[needs]
                same = rows(cur, orig) == rows(cur, rew)
                same_without_P = rows(cur, unpredicated(orig, P, Pb)) == rows(cur, unpredicated(rew, P, Pb))
                rec = dict(case=case['id'], list=case['list'], table=case['table'], cls=case['cls'], K=case['K'],
                           P=P, template=tmpl, licensed=licensed, rewrite_correct=same,
                           rewrite_correct_without_P=same_without_P, orig_sql=orig, rew_sql=rew, configs={})
                for cfg in ('none', 'idx', 'uq'):
                    cur.execute(f'DROP INDEX IF EXISTS ckqo_tmp_idx')
                    created = []
                    if cfg == 'idx':
                        cur.execute(f'CREATE INDEX ckqo_tmp_idx ON {t} (' + ', '.join(q(c) for c in case['K']) + ')')
                    if cfg == 'uq':
                        for k, sql in enumerate(indexes(case, t, cur)):
                            nm = f'ckqo_uq_{k}'
                            cur.execute(f'DROP INDEX IF EXISTS {nm}')
                            cur.execute(sql.replace('CREATE UNIQUE INDEX ON', f'CREATE UNIQUE INDEX {nm} ON'))
                            created.append(nm)
                    cur.execute(f'ANALYZE {t}')
                    explain(cur, orig, 2); explain(cur, rew, 2)            # warm-up
                    eo, po, plan_o = explain(cur, orig, a.reps)
                    er, pr, plan_r = explain(cur, rew, a.reps)
                    rec['configs'][cfg] = dict(orig_ms=round(eo, 4), rew_ms=round(er, 4),
                                               orig_plan_ms=round(po, 4), rew_plan_ms=round(pr, 4),
                                               pg_already_removes=redundant_gone(tmpl, plan_o),
                                               orig_nodes=node_types(plan_o))
                    for nm in created: cur.execute(f'DROP INDEX IF EXISTS {nm}')
                    cur.execute('DROP INDEX IF EXISTS ckqo_tmp_idx')
                conn.commit()
                results.append(rec)
                c = rec['configs']
                print(f"{case['id']:4s} {case['cls']:4s} {tmpl:8s} licensed={licensed!s:5} correct={same!s:5} "
                      f"correct-without-P={same_without_P!s:5} | none {c['none']['orig_ms']:.3f}->{c['none']['rew_ms']:.3f} "
                      f"uq {c['uq']['orig_ms']:.3f}->{c['uq']['rew_ms']:.3f} ms  pg-avoids none/idx/uq="
                      f"{c['none']['pg_already_removes']}/{c['idx']['pg_already_removes']}/{c['uq']['pg_already_removes']}",
                      flush=True)
    json.dump(results, open(a.out, 'w'), indent=1)
    print('wrote', a.out)

if __name__ == '__main__':
    main()
