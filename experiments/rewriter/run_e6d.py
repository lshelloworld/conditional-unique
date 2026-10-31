"""E6d: the rewrite layer end to end. For the tables and queries of E6b, the mined keys are
declared in PostgreSQL as their enforcement artefacts (filtered unique indexes, NULLS NOT
DISTINCT, conditional CHECKs, per-null-pattern index families for certain keys; creating them
also re-checks that the keys hold). ckrewrite.py then reads the catalog from pg_index /
pg_constraint, receives every E6b query as SQL text, decides by implication and emits the
rewritten SQL. Checked: every decision equals E6b's; for a sample of rewritten queries, the
emitted SQL returns the same row count as the original. Measured: catalog read, and per query
parse + implication + SQL generation. Writes results_e6d.json."""
import json, os, random, statistics, sys, time
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'qo_reasoning'))
from ckrewrite import Catalog, rewrite
from run_e6b import TABLES, ROOT, parse, Table, queries, violations, q, load_pg

def artefacts(T, tn):
    sql = []
    for n, k in enumerate(T.keys):
        P = T.sql(k['temps']); K = k['K']; Kc = ', '.join(q(c) for c in K)
        if k['cls'] in ('pos', 'cand'): sql.append(f'CREATE UNIQUE INDEX ON {tn} ({Kc}) WHERE {P}')
        if k['cls'] == 'dom': sql.append(f'CREATE UNIQUE INDEX ON {tn} ({Kc}) NULLS NOT DISTINCT WHERE {P}')
        if k['cls'] == 'cand':
            sql.append(f'ALTER TABLE {tn} ADD CONSTRAINT ck_{n} CHECK (NOT ({P}) OR (' +
                       ' AND '.join(f'{q(c)} IS NOT NULL' for c in K) + '))')
        if k['cls'] == 'cert':
            import itertools
            for r in range(len(K) + 1):
                for S in itertools.combinations(K, r):
                    rest = [c for c in K if c not in S]
                    cond = ' AND '.join([f'({P})'] + [f'{q(c)} IS NULL' for c in S] + [f'{q(c)} IS NOT NULL' for c in rest])
                    sql.append(f'CREATE UNIQUE INDEX ON {tn} (' + (', '.join(q(c) for c in rest) if rest else '(1)') + f') WHERE {cond}')
    return sql

def count(cur, sql):
    cur.execute(f'SELECT count(*) FROM ({sql}) s'); return cur.fetchone()[0]

def main():
    old = json.load(open(os.path.join(HERE, '..', 'qo_reasoning', 'results_e6b.json')))
    conn = psycopg.connect('host=localhost port=5444 user=ck dbname=ckqo', autocommit=True)
    rng = random.Random(11); out = {}; srng = random.Random(5)
    for ds, name in TABLES:
        if name == 'ncvoter.voters': rng = random.Random(11)
        D = json.load(open(os.path.join(ROOT, 'discovery', 'results', f'{ds}.json')))
        raw = [r for t in D['tables'] if t['table'] == name for r in t['conditional'] if r.get('verified')][:40]
        keys = [dict(K=r['K'], cls=r['cls'], temps=parse(r['sql'], r['constants'])) for r in raw if r['cls'] != 'part']
        T = Table(ds, name, keys)
        T.keys = [k for k in keys if not violations(T.rows, T.cols, k['K'], k['cls'], T.scope_mask(k['temps']))]
        Q = queries(T, rng, ncontrol=len(T.keys))
        raw_name = 'e6d_' + name.replace('.', '_'); tn = q(raw_name)
        with conn.cursor() as cur:
            cur.execute('SET max_parallel_workers_per_gather = 0')
            load_pg(cur, T, tn)
            t0 = time.perf_counter()
            A = artefacts(T, tn)
            for s in A: cur.execute(s)
            build_s = time.perf_counter() - t0
            cur.execute(f'ANALYZE {tn}')
            cat = Catalog(conn, raw_name)
            stored = old[name]['results']; res = []; i = 0
            for kind, temps, K in Q:
                P = T.sql(temps)
                Kc = ', '.join(q(c) for c in K); aK = ', '.join(f'a.{q(c)}' for c in K)
                on = ' AND '.join(f'a.{q(c)} = b.{q(c)}' for c in K)
                X = next((c for c in T.cols if c not in K), T.cols[0])
                for tmpl, orig in (('DISTINCT', f'SELECT DISTINCT {Kc} FROM {tn} WHERE {P}'),
                                   ('LEFTJOIN', f'SELECT {aK}, a.{q(X)} FROM {tn} a LEFT JOIN (SELECT * FROM {tn} WHERE {P}) b ON {on}')):
                    o = stored[i]; i += 1
                    t1 = time.perf_counter(); new, info = rewrite(orig, {raw_name: cat}); ms = (time.perf_counter() - t1) * 1e3
                    r = dict(kind=kind, template=tmpl, rewritten=new is not None, e6b=o['full'], ms=ms,
                             b=info.get('b'), solver=info.get('solver'), new_sql=new)
                    assert r['rewritten'] == o['full'], (name, i, orig, info)
                    res.append(r)
            sample = srng.sample([r for r in res if r['rewritten']], min(10, sum(r['rewritten'] for r in res)))
            for r in sample:   # the emitted SQL runs and returns what the original returns
                idx = res.index(r); kind, temps, K = Q[idx // 2]
            checked = 0
            for r in sample:
                idx = res.index(r); kind, temps, K = Q[idx // 2]
                P = T.sql(temps); Kc = ', '.join(q(c) for c in K); aK = ', '.join(f'a.{q(c)}' for c in K)
                on = ' AND '.join(f'a.{q(c)} = b.{q(c)}' for c in K); X = next((c for c in T.cols if c not in K), T.cols[0])
                orig = (f'SELECT DISTINCT {Kc} FROM {tn} WHERE {P}' if r['template'] == 'DISTINCT' else
                        f'SELECT {aK}, a.{q(X)} FROM {tn} a LEFT JOIN (SELECT * FROM {tn} WHERE {P}) b ON {on}')
                assert count(cur, orig) == count(cur, r['new_sql']), (name, r['new_sql'])
                checked += 1
            cur.execute(f'DROP TABLE {tn}')
        out[name] = dict(artefacts=len(A), catalog_constraints=len(cat.Sigma), ignored=cat.ignored,
                         build_s=build_s, catalog_read_ms=cat.read_ms, sample_checked=checked, results=res)
        ms = [r['ms'] for r in res]
        print(f"{name}: {len(A)} artefacts built in {build_s:.1f}s, catalog {len(cat.Sigma)} constraints read in "
              f"{cat.read_ms:.1f} ms ({cat.ignored} ignored); {len(res)} queries, all decisions = E6b, "
              f"{sum(r['rewritten'] for r in res)} rewritten, {checked} emitted rewrites checked; "
              f"rewrite ms median {statistics.median(ms):.2f} max {max(ms):.1f}", flush=True)
        json.dump(out, open(os.path.join(HERE, 'results_e6d.json'), 'w'), indent=1)

if __name__ == '__main__':
    main()
