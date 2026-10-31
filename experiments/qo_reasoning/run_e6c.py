"""E6c: rewrites that need partial or certain keys (Table "Rewrites" of the paper).

For a mined key C:K(K) with scope predicate P on table t (columns: the loaded columns R):
  SUBSUME   minimum-union style subsumption removal within the scope
            SELECT * FROM t r WHERE P AND NOT EXISTS (SELECT 1 FROM t s WHERE P(s)
                AND s.ctid <> r.ctid AND AND_{c in R} (s.c = r.c OR r.c IS NULL))
            -> SELECT * FROM t WHERE P
            correct iff no record of the scope is subsumed by another; a partial key on K
            (or a certain or candidate key) forbids subsumption on K, hence on R.
  WILDCARD  null-as-wildcard lookup into the scope, for probes complete on K
            SELECT a.K, a.X FROM t a LEFT JOIN (SELECT * FROM t WHERE P) b
                ON AND_{k in K} (a.k = b.k OR b.k IS NULL) WHERE a.K IS NOT NULL
            -> SELECT a.K, a.X FROM t a WHERE a.K IS NOT NULL
            correct iff every probe has at most one compatible partner in the scope; a certain
            key guarantees it (two partners compatible with a complete probe are compatible with
            each other), a partial key does not.
Keys: the verified mined keys of the tables below, of every class; a rewrite is licensed if the
class implies the one the template needs (part for SUBSUME, cert for WILDCARD). Ground truth
is computed exactly on the loaded rows: SUBSUME is wrong iff some record of the scope is
subsumed by another, WILDCARD iff some probe complete on K is compatible with two records of the
scope (which then are compatible with each other). Only licensed rewrites are timed in
PostgreSQL; original queries are quadratic and run under a statement timeout, timed-out
originals are reported as lower bounds."""
import argparse, json, os, statistics, sys, time
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run_e6b import ROOT, parse, Table, violations, q, load_pg
sys.path.insert(0, os.path.join(ROOT, 'experiments', 'cleaning_real'))
from ncvoter_real import pairs as violating_pairs


def subsume_ok(T, scope):
    return not violating_pairs(T.rows, {c: i for i, c in enumerate(T.cols)}, T.cols, 'part', scope)


def wildcard_ok(T, K, scope):
    ix = {c: i for i, c in enumerate(T.cols)}; ki = [ix[c] for c in K]
    probes = [tuple(r[k] for k in ki) for r in T.rows if all(r[k] is not None for k in ki)]
    cache = {}
    for i, j in violating_pairs(T.rows, ix, K, 'cert', scope):
        m = tuple(T.rows[i][k] if T.rows[i][k] is not None else T.rows[j][k] for k in ki)
        pos = tuple(p for p, v in enumerate(m) if v is not None)
        if pos not in cache: cache[pos] = {tuple(p[x] for x in pos) for p in probes}
        if tuple(m[x] for x in pos) in cache[pos]: return False
    return True

TABLES = [('hockey', 'Hockey.Master'), ('hockey', 'Hockey.Coaches'), ('hockey', 'Hockey.Goalies'),
          ('hockey', 'Hockey.SeriesPost'), ('hockey', 'Hockey.Teams'), ('hockey', 'Hockey.TeamsPost'),
          ('voc', 'voc.voyages'), ('voc', 'voc.seafarers'), ('uniprot', 'uniprot.proteins')]
RANK = {'pos': 0, 'dom': 1, 'part': 2, 'cert': 3, 'cand': 4}
NEEDS = {'SUBSUME': 'part', 'WILDCARD': 'cert'}


def run_sql(cur, sql, timeout_ms):
    cur.execute(f'SET statement_timeout = {timeout_ms}')
    t0 = time.perf_counter()
    try:
        cur.execute(f'SELECT count(*) FROM ({sql}) s'); n = cur.fetchone()[0]
    except psycopg.errors.QueryCanceled:
        n = None
    ms = (time.perf_counter() - t0) * 1e3
    cur.execute('SET statement_timeout = 0')
    return n, ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dsn', default='host=localhost port=5444 user=ck dbname=ckqo')
    ap.add_argument('--per-class', type=int, default=4)
    ap.add_argument('--timeout', type=int, default=60000)
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--out', default=os.path.join(HERE, 'results_e6c.json'))
    a = ap.parse_args()
    conn = psycopg.connect(a.dsn, autocommit=True)
    out = json.load(open(a.out)) if os.path.exists(a.out) else {}
    for ds, name in TABLES:
        if name in out: continue
        D = json.load(open(os.path.join(ROOT, 'discovery', 'results', f'{ds}.json')))
        raw = [r for t in D['tables'] if t['table'] == name for r in t['conditional']]
        keys = [dict(K=r['K'], cls=r['cls'], temps=parse(r['sql'], r['constants'])) for r in raw]
        T = Table(ds, name, keys)
        held = [k for k in keys if not violations(T.rows, T.cols, k['K'], k['cls'], T.scope_mask(k['temps']))]
        pick = []
        for cls in ('pos', 'dom', 'part', 'cert', 'cand'):
            pick += [k for k in held if k['cls'] == cls][:a.per_class]
        if not pick: continue
        tn = q('e6c_' + name.replace('.', '_'))
        res = []
        with conn.cursor() as cur:
            cur.execute('SET max_parallel_workers_per_gather = 0')
            load_pg(cur, T, tn)
            print(f'{name}: {len(T.rows)} rows, {len(pick)} keys', flush=True)
            for k in pick:
                P = T.sql(k['temps']); K = k['K']
                Ps = ' '.join(('s.' + w if w.startswith('"') else w) for w in P.split(' '))
                sub = ' AND '.join(f'(s.{q(c)} = r.{q(c)} OR r.{q(c)} IS NULL)' for c in T.cols)
                X = next((c for c in T.cols if c not in K), T.cols[0])
                aK = ', '.join(f'a.{q(c)}' for c in K)
                wild = ' AND '.join(f'(a.{q(c)} = b.{q(c)} OR b.{q(c)} IS NULL)' for c in K)
                full = ' AND '.join(f'a.{q(c)} IS NOT NULL' for c in K)
                for tmpl, orig, rew in (
                        ('SUBSUME', f'SELECT * FROM {tn} r WHERE ({P}) AND NOT EXISTS '
                                    f'(SELECT 1 FROM {tn} s WHERE ({Ps}) AND s.ctid <> r.ctid AND {sub})',
                         f'SELECT * FROM {tn} WHERE {P}'),
                        ('WILDCARD', f'SELECT {aK}, a.{q(X)} FROM {tn} a LEFT JOIN (SELECT * FROM {tn} WHERE {P}) b ON {wild} WHERE {full}',
                         f'SELECT {aK}, a.{q(X)} FROM {tn} a WHERE {full}')):
                    licensed = RANK[k['cls']] >= RANK[NEEDS[tmpl]]
                    scope = T.scope_mask(k['temps'])
                    correct = subsume_ok(T, scope) if tmpl == 'SUBSUME' else wildcard_ok(T, K, scope)
                    r = dict(K=K, cls=k['cls'], P=P, template=tmpl, licensed=licensed, correct=correct,
                             orig_sql=orig, rew_sql=rew)
                    if licensed:
                        n_orig, t_orig = run_sql(cur, orig, a.timeout)
                        n_rew, _ = run_sql(cur, rew, a.timeout)
                        if n_orig is not None: assert (n_orig == n_rew) == correct, (name, K, tmpl)
                        o = [t_orig] + ([run_sql(cur, orig, a.timeout)[1] for _ in range(a.reps - 1)] if n_orig is not None else [])
                        w = [run_sql(cur, rew, a.timeout)[1] for _ in range(a.reps)]
                        r.update(orig_ms=statistics.median(o), rew_ms=statistics.median(w), orig_timeout=n_orig is None)
                    res.append(r)
                    print(f"  {k['cls']:4s} {tmpl:8s} licensed={licensed!s:5s} correct={r['correct']} "
                          + (f"{r['orig_ms']:.0f} -> {r['rew_ms']:.1f} ms" if licensed else ''), flush=True)
            cur.execute(f'DROP TABLE {tn}')
        out[name] = dict(rows=len(T.rows), results=res)
        json.dump(out, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()
