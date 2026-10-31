"""X4: decisions on catalogs of filtered unique indexes only, against real optimisers.

Tables, mined keys and query generator of E6b (experiments/qo_reasoning/run_e6b.py, seed 11).
The catalog is now only what an application declares, filtered unique indexes:
  pos(K) under C, cand(K) under C  ->  CREATE UNIQUE INDEX ... (K) WHERE C          C : U(K)
  dom(K) under C                   ->  ... NULLS NOT DISTINCT WHERE C               C : U=(K)
                                       (SQLite has no NULLS NOT DISTINCT: nulls distinct there)
  cert(K) under C                  ->  per null pattern S (K \\ S non-empty):
                                       UNIQUE (K \\ S) WHERE C AND S IS NULL AND K \\ S IS NOT NULL
no CHECK constraints, no triggers. An index the system cannot build is left out everywhere.
Templates (as in E6b):
  LEFTJOIN  SELECT a.K, a.X FROM t a LEFT JOIN t b ON a.K = b.K AND P(b)  ->  drop the join (needs P : U(K))
  DISTINCT  SELECT DISTINCT K FROM t WHERE P                          ->  drop DISTINCT (needs P : U=(K))
Deciders:
  *_iu      the same systems, join kept: with nested loops forced, EXPLAIN VERBOSE shows
            'Inner Unique: true' for b (patched: removed or inner unique). In 15.x predOK is
            computed after join removal, so the old rule could only mark joins inner-unique.
  pg18      PostgreSQL 18.6, stock rule (enable_conditional_unique = off): the plan has no join
  pg15.3    PostgreSQL 15.3, before the bug #17975 fix: partial unique index usable if predOK
  sqlite    SQLite 3.54: the LEFT JOIN is omitted (EXPLAIN QUERY PLAN no longer mentions b)
  patched   PostgreSQL 18.6 + condunique (enable_conditional_unique = on): the plan has no join
  single    implication from one index at a time (model)
  naive     an index whose predicate P implies, on a subset of K, read as plain UNIQUE (model)
  ours      implication from the whole catalog (model; Algorithm 1 if b <= 10, else SAT)
DISTINCT: PostgreSQL 18.6 off/on and 15.3 are asked (the plan has no Unique or Aggregate node);
SQLite's isDistinctRedundant skips partial indexes, so its DISTINCT entry is 0 by source.
Every decision is checked on the data (run_e6b.unique).
Writes x4_decisions.json. Usage: python x4_decisions.py PG18DSN PG15DSN SQLITEFILE"""
import itertools, json, os, random, re, sqlite3, sys, time
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'experiments', 'qo_reasoning'))
from run_e6b import TABLES, parse, Table, queries, violations, q, unique, decide, load_pg
from implication import Checker
# X4_TABLES=ds:name,... runs other tables (e.g. those of datasets2.py); X4_OUT names the output
if os.environ.get('X4_TABLES'):
    TABLES = [tuple(x.split(':', 1)) for x in os.environ['X4_TABLES'].split(',')]
OUT = os.environ.get('X4_OUT', 'x4_decisions.json')


def lit(T, v):
    return str(v) if T.typ == 'bigint' else "'%s'" % str(v).replace("'", "''")


def pred(T, temps, alias=''):
    def atom(c, s):
        if s == 'T': return f'{alias}{q(c)} IS NOT NULL'
        if s == 'N': return f'{alias}{q(c)} IS NULL'
        return f'{alias}{q(c)} = {lit(T, s[1])}'
    return ' OR '.join('(' + ' AND '.join(atom(c, s) for c, s in t.items()) + ')' for t in temps)


def indexes(T):
    """[(temps, sem, K)] with sem 'U' or 'Ueq', temps in parse() form"""
    out = []
    for k in T.keys:
        K = list(k['K'])
        if k['cls'] in ('pos', 'cand'): out.append((k['temps'], 'U', K))
        elif k['cls'] == 'dom': out.append((k['temps'], 'Ueq', K))
        elif k['cls'] == 'cert':
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


def model(T, idx):
    return [([T.template(t) for t in temps], 'dom' if sem == 'Ueq' else 'pos', frozenset(K)) for temps, sem, K in idx]


def pg_nodes(cur, sql):
    """the plan's node names (not its conditions, which hold column names such as 'In City Limits')"""
    cur.execute('explain (costs off) ' + sql)
    out = []
    for i, (l,) in enumerate(cur.fetchall()):
        s = l.strip()
        if s.startswith('->'): s = s[2:].strip()
        elif i: continue
        out.append(re.split(r' on | using |  \(', s)[0])
    return out


def pg_removed(cur, sql, on=None):
    if on is not None: cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    return not any('Join' in n or 'Nested Loop' in n for n in pg_nodes(cur, sql))


SQLITE_ERRORS = []


def pg_distinct_removed(cur, sql, on=None):
    if on is not None: cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    # a Limit (DISTINCT over columns the query fixes to constants) still de-duplicates
    return not any('Unique' in n or 'Aggregate' in n or n == 'Limit' for n in pg_nodes(cur, sql))


def pg_inner_unique(cur, sql, on=None):
    """with nested loops only, is the inner side (b) of the remaining left join proven unique?"""
    if on is not None: cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute('set enable_hashjoin = off'); cur.execute('set enable_mergejoin = off')
    cur.execute('explain (verbose, costs off) ' + sql)
    plan = [r[0] for r in cur.fetchall()]
    cur.execute('reset enable_hashjoin'); cur.execute('reset enable_mergejoin')
    return any('Inner Unique: true' in l for l in plan)


def sqlite_removed(con, sql):
    try:
        return not any(re.search(r'\bb\b', r[3]) for r in con.execute('explain query plan ' + sql))
    except sqlite3.Error as ex:            # recorded, counted as not removed
        SQLITE_ERRORS.append(dict(sql=sql, error=f'{type(ex).__name__}: {ex}'))
        return False


def main():
    pg18 = psycopg.connect(sys.argv[1], autocommit=True, prepare_threshold=None)
    pg15 = psycopg.connect(sys.argv[2], autocommit=True, prepare_threshold=None)
    sl = sqlite3.connect(sys.argv[3])
    rng = random.Random(11)
    out = {}
    tot = Counter()
    c18, c15 = pg18.cursor(), pg15.cursor()
    for c in (c18, c15): c.execute('set max_parallel_workers_per_gather = 0')
    for ds, name in TABLES:
        t0 = time.time()
        D = json.load(open(os.path.join(ROOT, 'discovery', 'results', f'{ds}.json')))
        raw = [r for t in D['tables'] if t['table'] == name for r in t['conditional'] if r.get('verified')][:40]
        keys = [dict(K=r['K'], cls=r['cls'], temps=parse(r['sql'], r['constants'])) for r in raw if r['cls'] != 'part']
        T = Table(ds, name, keys)
        T.keys = [k for k in keys if not violations(T.rows, T.cols, k['K'], k['cls'], T.scope_mask(k['temps']))]
        Q = queries(T, rng, ncontrol=len(T.keys))
        tn = q('x4_' + name.replace('.', '_'))
        load_pg(c18, T, tn); load_pg(c15, T, tn)
        sl.execute(f'DROP TABLE IF EXISTS {tn}')
        sl.execute(f'CREATE TABLE {tn} (' + ', '.join(f'{q(c)} {"INTEGER" if T.typ == "bigint" else "TEXT"}' for c in T.cols) + ')')
        sl.executemany(f'INSERT INTO {tn} VALUES ({", ".join("?" * len(T.cols))})', T.rows); sl.commit()
        built, failed = [], Counter()
        for i, (temps, sem, K) in enumerate(indexes(T)):
            cols = ', '.join(q(c) for c in K); P = pred(T, temps)
            ok = True
            for sysname, run in (
                    ('pg18', lambda: c18.execute(f"create unique index {q(f'x4i_{i}')} on {tn} ({cols})"
                                                 + (' nulls not distinct' if sem == 'Ueq' else '') + f' where {P}')),
                    ('pg15.3', lambda: c15.execute(f"create unique index {q(f'x4i_{i}')} on {tn} ({cols})"
                                                   + (' nulls not distinct' if sem == 'Ueq' else '') + f' where {P}')),
                    ('sqlite', lambda: sl.execute(f"create unique index {q(f'x4i_{name}_{i}')} on {tn} ({cols}) where {P}"))):
                try: run()
                except Exception as ex:
                    failed[f'{sysname}: {type(ex).__name__}'] += 1; ok = False; break
            if ok: built.append((temps, sem, K))
            else:
                for stmt in (lambda: c18.execute(f"drop index if exists {q(f'x4i_{i}')}"),
                             lambda: c15.execute(f"drop index if exists {q(f'x4i_{i}')}"),
                             lambda: sl.execute(f"drop index if exists {q(f'x4i_{name}_{i}')}")):
                    stmt()
        c18.execute(f'analyze {tn}'); c15.execute(f'analyze {tn}'); sl.execute('analyze'); sl.commit()
        S = model(T, built); chk = Checker(T.cols, S)
        res = []
        for kind, temps, K in Q:
            C = [T.template(t) for t in temps]
            Kc = ', '.join(q(c) for c in K); X = next((c for c in T.cols if c not in K), T.cols[0])
            on = ' AND '.join(f'a.{q(c)} = b.{q(c)}' for c in K)
            lj = f'SELECT {", ".join(f"a.{q(c)}" for c in K)}, a.{q(X)} FROM {tn} a LEFT JOIN {tn} b ON {on} AND ({pred(T, temps, "b.")})'
            for tmpl, cls in (('DISTINCT', 'dom'), ('LEFTJOIN', 'pos')):
                d = decide(T, S, chk, (C, cls, frozenset(K)))
                r = dict(kind=kind, template=tmpl, K=K, P=pred(T, temps), ours=d['full'], single=d['single'],
                         naive=d['unique'], b=d['b'], ms=d['ms'],
                         correct=unique(c18, tn, pred(T, temps), K, tmpl == 'DISTINCT'))
                if tmpl == 'LEFTJOIN':
                    r['pg18'] = pg_removed(c18, lj, False)
                    r['patched'] = pg_removed(c18, lj, True)
                    r['pg15.3'] = pg_removed(c15, lj)
                    r['pg18_iu'] = pg_inner_unique(c18, lj, False)
                    r['pg15.3_iu'] = pg_inner_unique(c15, lj)
                    r['patched_iu'] = r['patched'] or pg_inner_unique(c18, lj, True)
                    r['sqlite'] = sqlite_removed(sl, lj)
                else:
                    dq = f'SELECT DISTINCT {Kc} FROM {tn} WHERE {pred(T, temps)}'
                    r['pg18'] = pg_distinct_removed(c18, dq, False)
                    r['patched'] = pg_distinct_removed(c18, dq, True)
                    r['pg15.3'] = pg_distinct_removed(c15, dq)
                    r['sqlite'] = False
                    r['pg18_iu'] = r['pg15.3_iu'] = r['patched_iu'] = False
                res.append(r)
        c18.execute(f'drop table {tn}'); c15.execute(f'drop table {tn}'); sl.execute(f'drop table {tn}'); sl.commit()
        out[name] = dict(rows=len(T.rows), keys=len(T.keys), indexes=len(built), failed=dict(failed), results=res,
                         sqlite_errors=[e for e in SQLITE_ERRORS if tn in e['sql']])
        line = []
        for rule in ('pg18', 'pg15.3', 'sqlite', 'patched', 'pg18_iu', 'pg15.3_iu', 'patched_iu', 'single', 'naive', 'ours'):
            for tmpl in ('LEFTJOIN', 'DISTINCT'):
                xs = [r for r in res if r['template'] == tmpl and r[rule]]
                tot[(rule, tmpl, 'lic')] += len(xs); tot[(rule, tmpl, 'wrong')] += sum(not r['correct'] for r in xs)
            line.append(f"{rule} {sum(r[rule] for r in res)}/{sum(r[rule] and not r['correct'] for r in res)}")
        line.append(f"sqlite errors {len(out[name]['sqlite_errors'])}")
        for tmpl in ('LEFTJOIN', 'DISTINCT'):
            tot[('decisions', tmpl, 'lic')] += sum(r['template'] == tmpl for r in res)
            tot[('correct', tmpl, 'lic')] += sum(r['template'] == tmpl and r['correct'] for r in res)
        print(f"{name}: {len(T.rows)} rows, {len(T.keys)} keys, {len(built)} indexes (failed {dict(failed)}), "
              f"{len(res)} decisions; licensed/wrong: " + ', '.join(line) + f" ({time.time() - t0:.0f}s)", flush=True)
        json.dump(out, open(os.path.join(HERE, OUT), 'w'), indent=1)
    print('TOTAL (licensed, wrong) per rule and template:')
    for rule in ('decisions', 'correct', 'pg18', 'pg15.3', 'sqlite', 'patched', 'pg18_iu', 'pg15.3_iu', 'patched_iu', 'single', 'naive', 'ours'):
        print(f"  {rule:9s} " + '  '.join(f"{tmpl} {tot[(rule, tmpl, 'lic')]}" + (f" ({tot[(rule, tmpl, 'wrong')]} wrong)" if rule not in ('decisions', 'correct') else '')
                                          for tmpl in ('LEFTJOIN', 'DISTINCT')), flush=True)


if __name__ == '__main__':
    main()
