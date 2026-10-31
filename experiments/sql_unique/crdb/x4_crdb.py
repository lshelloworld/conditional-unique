"""X4 on CockroachDB: the decisions of x4_decisions.py (Table IV) with the patched CockroachDB.

Same tables, mined keys, query generator and seed as ../x4_decisions.py. CockroachDB has no
NULLS NOT DISTINCT, so every key becomes nulls-distinct partial unique indexes:
  pos(K), cand(K) under C   ->  UNIQUE (K) WHERE C
  dom(K), cert(K) under C   ->  per null pattern S, a proper subset of K:
                                UNIQUE (K \\ S) WHERE C AND S IS NULL AND K \\ S IS NOT NULL
(Proposition 1 without the all-null pattern, which needs a key over no columns). The model is
built from the indexes CockroachDB accepted, so 'ours' is implication from exactly this catalog.
Deciders: crdb_off (optimizer_use_conditional_unique = off, i.e. stock), crdb_on (on), and the
models single (one index at a time) and ours (whole catalog). LEFT JOIN: removed iff EXPLAIN (OPT)
shows no join; DISTINCT: removed iff it shows no distinct-on or group-by. Every decision is checked
on the data. Writes x4_crdb.json. Usage: python x4_crdb.py DSN"""
import itertools, json, os, random, re, sys, time
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'experiments', 'qo_reasoning'))
sys.path.insert(0, os.path.join(HERE, '..'))
from run_e6b import TABLES, parse, Table, queries, violations, q, unique, decide
from implication import Checker
from x4_decisions import pred, model
if os.environ.get('X4_TABLES'):
    TABLES = [tuple(x.split(':', 1)) for x in os.environ['X4_TABLES'].split(',')]
OUT = os.environ.get('X4_OUT', 'x4_crdb.json')


def indexes(T):
    """[(temps, 'U', K)]: every key as nulls-distinct partial unique indexes"""
    out = []
    for k in T.keys:
        K = list(k['K'])
        if k['cls'] in ('pos', 'cand'):
            out.append((k['temps'], 'U', K)); continue
        for r in range(len(K)):
            for S in itertools.combinations(sorted(K), r):
                ts = []
                for t in k['temps']:
                    t2, bad = dict(t), False
                    for A in K:
                        want = 'N' if A in S else 'T'
                        cur = t2.get(A)
                        if cur is None or cur == want: t2[A] = want
                        elif not (want == 'T' and isinstance(cur, tuple)): bad = True
                    if not bad: ts.append(t2)
                if ts: out.append((ts, 'U', [A for A in K if A not in S]))
    return out


def plan(cur, sql, on):
    cur.execute(f"set optimizer_use_conditional_unique = {'on' if on else 'off'}")
    cur.execute('explain (opt) ' + sql)
    return '\n'.join(r[0] for r in cur.fetchall())


def ops_of(plan):
    """operator names of an EXPLAIN (OPT) tree, not its filters (which hold column names); a limit
    pushed into a scan (property 'limit: 1') counts as a limit"""
    ops = {m.group(1) for l in plan.split('\n')
           for m in [re.match(r'^[│├└─\s]*([a-z][a-z-]*)(?: \(.*\))?$', l)] if m}
    if any(re.match(r'^[│├└─\s]*limit: \d+$', l) for l in plan.split('\n')): ops.add('limit')
    return ops


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True, prepare_threshold=None)
    cur = con.cursor()
    rng = random.Random(11)
    out, tot = {}, Counter()
    for ds, name in TABLES:
        t0 = time.time()
        D = json.load(open(os.path.join(ROOT, 'discovery', 'results', f'{ds}.json')))
        raw = [r for t in D['tables'] if t['table'] == name for r in t['conditional'] if r.get('verified')][:40]
        keys = [dict(K=r['K'], cls=r['cls'], temps=parse(r['sql'], r['constants'])) for r in raw if r['cls'] != 'part']
        T = Table(ds, name, keys)
        T.keys = [k for k in keys if not violations(T.rows, T.cols, k['K'], k['cls'], T.scope_mask(k['temps']))]
        Q = queries(T, rng, ncontrol=len(T.keys))
        tn = q('x4_' + name.replace('.', '_'))
        cur.execute(f'DROP TABLE IF EXISTS {tn}')
        cur.execute(f'CREATE TABLE {tn} (' + ', '.join(f'{q(c)} {T.typ}' for c in T.cols) + ')')
        # rows before indexes: COPY into a table with many partial unique indexes reported a
        # violation of an index whose predicate the rows do not satisfy (lbsg.t12; INSERT is fine)
        with cur.copy(f'COPY {tn} ({", ".join(q(c) for c in T.cols)}) FROM STDIN') as cp:
            for r in T.rows: cp.write_row(r)
        built, failed = [], Counter()
        for i, (temps, sem, K) in enumerate(indexes(T)):
            try:
                cur.execute(f"create unique index {q(f'x4i_{i}')} on {tn} ({', '.join(q(c) for c in K)}) where {pred(T, temps)}")
                built.append((temps, sem, K))
            except Exception as ex:
                failed[type(ex).__name__] += 1
        S = model(T, built); chk = Checker(T.cols, S)
        res = []
        for kind, temps, K in Q:
            C = [T.template(t) for t in temps]
            X = next((c for c in T.cols if c not in K), T.cols[0])
            on = ' AND '.join(f'a.{q(c)} = b.{q(c)}' for c in K)
            lj = f'SELECT {", ".join(f"a.{q(c)}" for c in K)}, a.{q(X)} FROM {tn} a LEFT JOIN {tn} b ON {on} AND ({pred(T, temps, "b.")})'
            dq = f'SELECT DISTINCT {", ".join(q(c) for c in K)} FROM {tn} WHERE {pred(T, temps)}'
            for tmpl, cls, sql in (('DISTINCT', 'dom', dq), ('LEFTJOIN', 'pos', lj)):
                d = decide(T, S, chk, (C, cls, frozenset(K)))
                r = dict(kind=kind, template=tmpl, K=K, P=pred(T, temps), ours=d['full'], single=d['single'],
                         correct=unique(cur, tn, pred(T, temps), K, tmpl == 'DISTINCT'))
                for rule, flag in (('crdb_off', False), ('crdb_on', True)):
                    p = plan(cur, sql, flag)
                    # a limit (DISTINCT over columns the query fixes to constants) still de-duplicates
                    ops = ops_of(p)
                    r[rule] = not any(o.endswith('-join') for o in ops) if tmpl == 'LEFTJOIN' else not any(
                        o in ops for o in ('distinct-on', 'group-by', 'limit'))
                res.append(r)
        cur.execute(f'DROP TABLE {tn}')
        out[name] = dict(rows=len(T.rows), keys=len(T.keys), indexes=len(built), failed=dict(failed), results=res)
        line = []
        for rule in ('crdb_off', 'crdb_on', 'single', 'ours'):
            for tmpl in ('LEFTJOIN', 'DISTINCT'):
                xs = [r for r in res if r['template'] == tmpl and r[rule]]
                tot[(rule, tmpl, 'lic')] += len(xs); tot[(rule, tmpl, 'wrong')] += sum(not r['correct'] for r in xs)
            line.append(f"{rule} {sum(r[rule] for r in res)}/{sum(r[rule] and not r['correct'] for r in res)}")
        mism = sum(r['crdb_on'] != r['ours'] for r in res)
        for tmpl in ('LEFTJOIN', 'DISTINCT'):
            tot[('decisions', tmpl, 'lic')] += sum(r['template'] == tmpl for r in res)
            tot[('correct', tmpl, 'lic')] += sum(r['template'] == tmpl and r['correct'] for r in res)
            tot[('on!=ours', tmpl, 'lic')] += sum(r['template'] == tmpl and r['crdb_on'] != r['ours'] for r in res)
        print(f"{name}: {len(T.rows)} rows, {len(T.keys)} keys, {len(built)} indexes (failed {dict(failed)}), "
              f"{len(res)} decisions; licensed/wrong: " + ', '.join(line) + f"; on != ours {mism} ({time.time() - t0:.0f}s)", flush=True)
        json.dump(out, open(os.path.join(HERE, OUT), 'w'), indent=1)
    print('TOTAL (licensed, wrong) per rule and template:')
    for rule in ('decisions', 'correct', 'crdb_off', 'crdb_on', 'single', 'ours', 'on!=ours'):
        print(f"  {rule:9s} " + '  '.join(f"{tmpl} {tot[(rule, tmpl, 'lic')]}" + (f" ({tot[(rule, tmpl, 'wrong')]} wrong)" if rule in ('crdb_off', 'crdb_on', 'single', 'ours') else '')
                                          for tmpl in ('LEFTJOIN', 'DISTINCT')), flush=True)


if __name__ == '__main__':
    main()
