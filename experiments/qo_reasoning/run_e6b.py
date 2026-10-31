"""E6b: query optimisation that has to reason. The optimiser sees a catalog of filtered unique
indexes and conditional NOT NULL checks (the enforcement artefacts of the mined conditional
keys) and must decide, for queries whose predicates differ from the index predicates, whether
DISTINCT or a LEFT JOIN may be removed.

Catalog per table, from the verified mined keys (Section VIII-A) that hold on the loaded table:
  pos(K) under C   ->  UNIQUE (K) WHERE C                          C:pos(K)
  dom(K)           ->  UNIQUE (K) NULLS NOT DISTINCT WHERE C       C:dom(K)
  cand(K)          ->  UNIQUE (K) WHERE C, CHECK (NOT C OR K NOT NULL)   C:pos(K), C:nn(K)
  cert(K)          ->  one UNIQUE (K \\ S) WHERE C AND S null AND K\\S not null per null pattern S
                       (the cross-pattern trigger is invisible to the optimiser)
  part(K)          ->  trigger only (invisible)
Queries, per key (C, K) of the table: the exact scope; the scope refined by an atom of another
key's condition; K extended by a column; the union of two scopes that fix distinct constants of
one column, with that column added to K; plus random controls (random key columns and atoms).
Templates: DISTINCT  SELECT DISTINCT K FROM t WHERE P -> SELECT K FROM t WHERE P   (needs C_P:dom(K))
           LEFTJOIN  SELECT a.K, a.X FROM t a LEFT JOIN (SELECT * FROM t WHERE P) b ON a.K = b.K
                     -> SELECT a.K, a.X FROM t a                                  (needs C_P:pos(K))
Deciders: 'full' = implication from the whole catalog (Algorithm 1 if b <= 10, else SAT);
'single' = implication from one catalog constraint at a time; 'unique' = what UNIQUE semantics
suggests: one filtered unique index whose predicate is implied by P on a subset of K licenses
both rewrites. Ground truth: the rewrite returns the same multiset in PostgreSQL, decided by checking the
filtered input for duplicates on K (see unique(); on the first tables this was checked by
comparing the row counts of both queries, which is equivalent)."""
import argparse, glob, itertools, json, os, random, re, statistics, sys, time
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'discovery')); sys.path.insert(0, os.path.join(ROOT, 'experiments', 'reasoning'))
sys.path.insert(0, os.path.join(ROOT, 'experiments', 'cleaning'))
from ckminer import load_export
from run_csv import load_csv, DATA as CSVDATA, DATASETS
from datasets2 import DATASETS2, load2
from run_e7 import violations
from implication import Checker, implies_canonical, implies_sat, _relevant

EXPORTS = os.environ.get('CU_EXPORTS', 'data/exports')
TABLES = [('hockey', 'Hockey.Coaches'), ('hockey', 'Hockey.Goalies'), ('hockey', 'Hockey.SeriesPost'),
          ('hockey', 'Hockey.Teams'), ('hockey', 'Hockey.TeamsPost'), ('voc', 'voc.voyages'),
          ('voc', 'voc.seafarers'), ('ncvoter-full', 'ncvoter.voters'), ('uniprot', 'uniprot.proteins')]
BMAX = 10
q = lambda c: f'"{c}"'


def parse(sql, consts):
    """'(a = :v1 AND b IS NULL) OR (c IS NOT NULL)' -> list of templates as {col: sym}"""
    temps = []
    for part in re.split(r'\) OR \(', sql.strip()[1:-1]):
        t = {}
        for a in part.split(' AND '):
            a = a.strip()
            if a.endswith(' IS NOT NULL'): t[a[:-12]] = 'T'
            elif a.endswith(' IS NULL'): t[a[:-8]] = 'N'
            else:
                c, v = a.split(' = ', 1)
                v = v.strip("'")
                if v.startswith(':'): v = int(consts[f'{c}={v[1:]}'])
                t[c] = ('C', v)
        temps.append(t)
    return temps


class Table:
    def __init__(self, ds, name, keys):
        self.ds, self.name = ds, name
        self.keys = keys
        need = sorted({c for k in keys for c in k['K']} | {c for k in keys for t in k['temps'] for c in t})
        if ds in ('hockey', 'voc'):
            path = glob.glob(os.path.join(EXPORTS, ds, f'{name}-*-full.json'))[0]
            _, cols, rows = load_export(path)
            ix = [cols.index(c) for c in need]
            self.rows = [tuple(r[i] for i in ix) for r in rows]; self.typ = 'bigint'
        elif ds in DATASETS2:
            _, self.rows = load2(ds, need); self.typ = 'text'
        else:
            d = 'ncvoter' if ds.startswith('ncvoter') else ds
            _, self.rows = load_csv(os.path.join(CSVDATA, DATASETS[d]['file']), 0, 7, need); self.typ = 'text'
        self.cols = need
        payload = [c for c in need]
        self.X = payload[0]
        self.enc = {}          # (col, value) -> int code for the reasoner

    def code(self, c, v):
        return self.enc.setdefault((c, v), len(self.enc) + 1)

    def template(self, t):
        """template over the reasoning schema (self.cols)"""
        out = {A: '_' for A in self.cols}
        for c, s in t.items():
            out[c] = self.code(c, s[1]) if isinstance(s, tuple) else s
        return out

    def scope_mask(self, temps):
        ix = {c: i for i, c in enumerate(self.cols)}
        def ok(r, t):
            for c, s in t.items():
                v = r[ix[c]]
                if s == 'T' and v is None or s == 'N' and v is not None: return False
                if isinstance(s, tuple) and v != s[1]: return False
            return True
        return [any(ok(r, t) for t in temps) for r in self.rows]

    def sql(self, temps):
        def atom(c, s):
            if s == 'T': return f'{q(c)} IS NOT NULL'
            if s == 'N': return f'{q(c)} IS NULL'
            return f"{q(c)} = {s[1]}" if self.typ == 'bigint' else f"{q(c)} = '{s[1]}'"
        return ' OR '.join('(' + ' AND '.join(atom(c, s) for c, s in t.items()) + ')' for t in temps)


def catalog(T):
    """constraints visible to the optimiser, in the representation of implication.py"""
    S = []
    for k in T.keys:
        C = [T.template(t) for t in k['temps']]
        K = frozenset(k['K'])
        if k['cls'] == 'pos': S.append((C, 'pos', K))
        elif k['cls'] == 'dom': S.append((C, 'dom', K))
        elif k['cls'] == 'cand': S += [(C, 'pos', K), (C, 'nn', K)]
        elif k['cls'] == 'cert':
            for r in range(len(K) + 1):
                for Sn in itertools.combinations(sorted(K), r):
                    Ct = []
                    for t in C:
                        t2 = dict(t)
                        bad = False
                        for A in K:
                            want = 'N' if A in Sn else 'T'
                            if t2[A] in ('_', want): t2[A] = want
                            elif not (want == 'T' and isinstance(t2[A], int)): bad = True
                        if not bad: Ct.append(t2)
                    if Ct: S.append((Ct, 'pos', K - set(Sn)))
    return S


def decide(T, S, chk, phi):
    cond, cls, K = phi
    rel = _relevant(T.cols, S, K)
    b = max(2 * sum(1 for A in rel if t[A] == '_') for t in cond)
    t0 = time.perf_counter()
    full = implies_canonical(T.cols, set(), S, phi, chk=chk) if b <= BMAX else implies_sat(T.cols, set(), S, phi)
    ms = (time.perf_counter() - t0) * 1e3
    single = any(implies_canonical(T.cols, set(), [s], phi) for s in S
                 if s[1] == cls or (cls == 'pos' and s[1] in ('dom', 'pos')) or (cls == 'dom' and s[1] == 'dom'))
    # UNIQUE semantics: a filtered unique index (pos or dom artefact) whose predicate P implies
    uniq = any(s[1] in ('pos', 'dom') and s[2] <= K and implies_canonical(T.cols, set(), [(s[0], 'pos', s[2])], (cond, 'pos', K))
               for s in S)
    return dict(full=full, single=single, unique=uniq, b=b, solver='alg1' if b <= BMAX else 'sat', ms=ms)


def queries(T, rng, ncontrol):
    Q = []
    atoms = [(c, s) for k in T.keys for t in k['temps'] for c, s in t.items()]
    keycols = sorted({c for k in T.keys for c in k['K']})
    for i, k in enumerate(T.keys):
        Q.append(('exact', k['temps'], k['K']))
        t2 = []
        for t in k['temps']:
            extra = [a for a in atoms if a[0] not in t]
            t = dict(t)
            if extra:
                c, s = rng.choice(extra); t[c] = s
            t2.append(t)
        Q.append(('refined', t2, k['K']))
        other = [c for c in T.cols if c not in k['K']]
        if other: Q.append(('superkey', k['temps'], k['K'] + [rng.choice(other)]))
    seen = set()
    for k1, k2 in itertools.combinations(T.keys, 2):
        if set(k1['K']) != set(k2['K']) or len(k1['temps']) != 1 or len(k2['temps']) != 1: continue
        for c, s in k1['temps'][0].items():
            s2 = k2['temps'][0].get(c)
            if isinstance(s, tuple) and isinstance(s2, tuple) and s != s2 and c not in k1['K']:
                key = (tuple(sorted(k1['K'])), c, s, s2)
                if key in seen: continue
                seen.add(key)
                Q.append(('union', [k1['temps'][0], k2['temps'][0]], k1['K'] + [c]))
    for _ in range(ncontrol):
        K = rng.sample(keycols, min(len(keycols), rng.randint(1, 3)))
        t = dict(rng.sample(atoms, min(len(atoms), rng.randint(1, 2))))   # a table may have one atom
        if t: Q.append(('random', [t], K))
    return Q


def load_pg(cur, T, tn):
    cur.execute(f'DROP TABLE IF EXISTS {tn}')
    cur.execute(f'CREATE TABLE {tn} (' + ', '.join(f'{q(c)} {T.typ}' for c in T.cols) + ')')
    with cur.copy(f'COPY {tn} ({", ".join(q(c) for c in T.cols)}) FROM STDIN') as cp:
        for r in T.rows: cp.write_row(r)
    cur.execute(f'ANALYZE {tn}')


def unique(cur, tn, P, K, nulls_equal):
    """does the filtered input sigma_P(t) have no two records agreeing on K? With nulls_equal
    (DISTINCT, domain semantics) nulls are grouped together; otherwise (equi-join, possible
    keys) records with a null on K never match. The DISTINCT rewrite is correct iff this holds
    with nulls_equal, the LEFT JOIN rewrite iff it holds without: every record of sigma_P(t) is
    also an outer record, so a duplicate gives it two join partners."""
    Kc = ', '.join(q(c) for c in K)
    nn = '' if nulls_equal else ' AND ' + ' AND '.join(f'{q(c)} IS NOT NULL' for c in K)
    cur.execute(f'SELECT 1 FROM {tn} WHERE ({P}){nn} GROUP BY {Kc} HAVING count(*) > 1 LIMIT 1')
    return cur.fetchone() is None


def explain(cur, sql, reps):
    v = []
    for _ in range(reps):
        cur.execute('EXPLAIN (ANALYZE, FORMAT JSON) ' + sql); v.append(cur.fetchone()[0][0]['Execution Time'])
    return statistics.median(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dsn', default='host=localhost port=5444 user=ck dbname=ckqo')
    ap.add_argument('--keys', type=int, default=40)
    ap.add_argument('--reps', type=int, default=5)
    ap.add_argument('--tables', default='')
    ap.add_argument('--out', default=os.path.join(HERE, 'results_e6b.json'))
    a = ap.parse_args()
    rng = random.Random(11)
    conn = psycopg.connect(a.dsn, autocommit=True)
    out = json.load(open(a.out)) if os.path.exists(a.out) else {}
    for ds, name in TABLES:
        if a.tables and name not in a.tables.split(','): continue
        if name in out: continue
        D = json.load(open(os.path.join(ROOT, 'discovery', 'results', f'{ds}.json')))
        raw = [r for t in D['tables'] if t['table'] == name for r in t['conditional'] if r.get('verified')][:a.keys]
        keys = [dict(K=r['K'], cls=r['cls'], temps=parse(r['sql'], r['constants'])) for r in raw if r['cls'] != 'part']
        T = Table(ds, name, keys)
        held = []
        for k in keys:   # keep only keys that hold on the loaded table
            if not violations(T.rows, T.cols, k['K'], k['cls'], T.scope_mask(k['temps'])): held.append(k)
        T.keys = held
        S = catalog(T); chk = Checker(T.cols, S)
        tn = q('e6b_' + name.replace('.', '_'))
        with conn.cursor() as cur:
            cur.execute('SET max_parallel_workers_per_gather = 0')
            load_pg(cur, T, tn)
            res = []
            Q = queries(T, rng, ncontrol=len(T.keys))
            print(f'{name}: {len(T.rows)} rows, {len(held)}/{len(keys)} keys hold, catalog {len(S)}, {len(Q)} predicates', flush=True)
            for kind, temps, K in Q:
                P = T.sql(temps); C = [T.template(t) for t in temps]
                Kc = ', '.join(q(c) for c in K); aK = ', '.join(f'a.{q(c)}' for c in K)
                on = ' AND '.join(f'a.{q(c)} = b.{q(c)}' for c in K)
                X = next((c for c in T.cols if c not in K), T.cols[0])
                for tmpl, cls, orig, rew in (
                        ('DISTINCT', 'dom', f'SELECT DISTINCT {Kc} FROM {tn} WHERE {P}', f'SELECT {Kc} FROM {tn} WHERE {P}'),
                        ('LEFTJOIN', 'pos', f'SELECT {aK}, a.{q(X)} FROM {tn} a LEFT JOIN (SELECT * FROM {tn} WHERE {P}) b ON {on}',
                         f'SELECT {aK}, a.{q(X)} FROM {tn} a')):
                    d = decide(T, S, chk, (C, cls, frozenset(K)))
                    correct = unique(cur, tn, P, K, tmpl == 'DISTINCT')
                    r = dict(kind=kind, template=tmpl, K=K, P=P, correct=correct, **d)
                    if d['full']:
                        r['orig_ms'] = explain(cur, orig, a.reps); r['rew_ms'] = explain(cur, rew, a.reps)
                    res.append(r)
            cur.execute(f'DROP TABLE {tn}')
        out[name] = dict(rows=len(T.rows), keys=len(held), catalog=len(S), results=res)
        json.dump(out, open(a.out, 'w'), indent=1)
        f = [r for r in res if r['full']]
        print(f"  full licenses {len(f)}/{len(res)} (wrong {sum(not r['correct'] for r in f)}), single {sum(r['single'] for r in res)}, "
              f"unique {sum(r['unique'] for r in res)} (wrong {sum(r['unique'] and not r['correct'] for r in res)}), "
              f"correct-but-unlicensed {sum(r['correct'] and not r['full'] for r in res)}", flush=True)


if __name__ == '__main__':
    main()
