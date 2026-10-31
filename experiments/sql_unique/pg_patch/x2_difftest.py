"""X2: differential testing of the condunique patch.

For each of N random schemas:
  t(c0..c{n-1})  3-6 columns over small domains (int 0..3, text 'a'..'d', bool), some NOT NULL;
                 1-4 unique indexes, mostly partial, with random predicates (=, <>, IN, NOT IN,
                 IS [NOT] NULL, boolean columns, AND/OR, sometimes an untranslatable atom), keys
                 of 1-3 columns, NULLS NOT DISTINCT at random; filled with random rows that the
                 indexes admit (INSERT ... ON CONFLICT DO NOTHING), so rows outside each scope
                 repeat keys freely;
  o(c0..c{n-1})  the same column types, random rows.
Per schema, Q random queries of seven shapes over t's key columns J and a random scope P:
  L   left join:  SELECT o.* FROM o LEFT JOIN t ON o.J = t.J AND P
  L2  left join, scope through a clause of the same join: ON o.J = t.J AND t.cm = o.cm
      [WHERE o.cm = const]
  I   inner join: SELECT o.*, t.cx FROM o JOIN t ON o.J = t.J WHERE P
  S   semi-join:  SELECT o.* FROM o WHERE (o.J) IN (SELECT t.J FROM t WHERE P)
  G   grouping:   SELECT G, count(*) FROM t WHERE P GROUP BY G
  GJ  grouping over a join: ... FROM t JOIN o ON ... WHERE P GROUP BY G
  GL  grouping over the nullable side of a left join
  D   DISTINCT:   SELECT DISTINCT G FROM t WHERE P  (G: 1..n columns)
  DJ  DISTINCT over a join: SELECT DISTINCT G FROM t JOIN o ON ... WHERE P
  B   bug #17975 itself, an index predicate that only another join's clause implies:
      SELECT o.*, u.cm FROM o JOIN t ON o.K = t.K JOIN o u ON t.cm = u.cm, where K is the key of
      a partial index of t and, if one has it, of one whose predicate is `cm IS NOT NULL`
      (the strict equality on cm implies it); otherwise K and cm are random
      (only with X2_SHAPES=B: the default shapes and their random stream are unchanged)
With X2_JOINS=1, o and a third table u get random unique indexes as t does (mostly partial), and
five further shapes test uniqueness carried through joins (G mixes columns of the tables):
  XD  DISTINCT over an inner join:  SELECT DISTINCT G FROM t JOIN o ON t.J = o.J [AND Po] WHERE P
  XL  DISTINCT over a left join:    SELECT DISTINCT G FROM t LEFT JOIN o ON t.J = o.J AND Po WHERE P
  X3  DISTINCT over three tables, the second join inner or left; its ON clause may also read
      the other outer table (an equality or <>)
  XG  GROUP BY without aggregates over a two- or three-table join
  XA  GROUP BY with count(*) over a two- or three-table join
Each of them gets a semi-join on t, (t.J) IN (SELECT s.J FROM o s WHERE Ps), a third of the time.
With X2_CHECKS=1, t (and o, u with X2_JOINS) get 0-2 random CHECK constraints from the same
predicate generator: enforced, NOT ENFORCED, or added NOT VALID after the data so that old rows
may violate them; rows that violate an enforced one are not inserted.
The shapes come from X2_SHAPES (default: the seven above, L twice); the output file from X2_OUT.
Each query runs with enable_conditional_unique off and on under random join-method settings;
results are compared as multisets and plans as text. Power check for L: whether dropping the
join changes the result although some unique index (predicate ignored) has its key within J --
the rewrite a naive reading of the index licenses; likewise for D, whether dropping DISTINCT
changes the result although some unique index has its key within G.
Writes x2_difftest.json (summary and every mismatch). Usage: python x2_difftest.py DSN N Q SEED"""
import json, os, random, re, sys, time
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))

TYPES = {'int': ('int', lambda r: str(r.randint(0, 3))),
         'text': ('text', lambda r: "'%s'" % r.choice('abcd')),
         'bool': ('bool', lambda r: r.choice(['true', 'false'])),
         'smallint': ('smallint', lambda r: str(r.randint(0, 3)))}     # compared with int4 constants


TYPE_MIX = os.environ.get('X2_TYPES', 'int,int,text,bool').split(',')
SHAPES = os.environ.get('X2_SHAPES', 'L,L,L2,I,S,G,GJ,GL').split(',')
OUT = os.environ.get('X2_OUT', 'x2_difftest.json')


class Schema:
    def __init__(self, r):
        self.r = r
        self.n = r.randint(3, 6)
        self.ty = [r.choice(TYPE_MIX) for _ in range(self.n)]
        self.nn = [r.random() < 0.25 for _ in range(self.n)]

    def const(self, c):
        return TYPES[self.ty[c]][1](self.r)

    def atom(self, c, alias='', weird=True):
        r, col = self.r, f'{alias}c{c}'
        if weird and r.random() < 0.05:
            return f'({col})::text = {self.const(c)}::text'           # untranslatable
        if self.ty[c] == 'bool':
            return r.choice([col, f'not {col}', f'{col} is null', f'{col} is not null', f'{col} = {self.const(c)}'])
        k = r.random()
        if k < 0.35: return f'{col} = {self.const(c)}'
        if k < 0.5: return f'{col} <> {self.const(c)}'
        if k < 0.62: return f'{col} in ({self.const(c)}, {self.const(c)})'
        if k < 0.7: return f'{col} not in ({self.const(c)}, {self.const(c)})'
        if k < 0.85: return f'{col} is null'
        return f'{col} is not null'

    def cond(self, alias='', maxatoms=2, ors=True, weird=True):
        r = self.r
        def conj():
            return ' and '.join(self.atom(r.randrange(self.n), alias, weird) for _ in range(r.randint(1, maxatoms)))
        if ors and r.random() < 0.3:
            return '(' + ' or '.join(f'({conj()})' for _ in range(2)) + ')'
        return conj()

    def row(self):
        out = []
        for c in range(self.n):
            if not self.nn[c] and self.r.random() < 0.2: out.append('null')
            else: out.append(self.const(c))
        return '(' + ', '.join(out) + ')'


JOINS = os.environ.get('X2_JOINS') == '1'
CHECKS = os.environ.get('X2_CHECKS') == '1'


def checks(cur, s, r, tab, when):
    """0-2 random CHECK constraints on x2.tab: before the data (enforced, or NOT ENFORCED), or
    after it as NOT VALID, so that old rows may violate them"""
    n = 0
    for i in range(r.randint(0, 2)):
        mode = r.choices(['valid', 'notvalid', 'notenforced'], [0.6, 0.25, 0.15])[0]
        if (mode == 'notvalid') != (when == 'after'):
            continue
        sql = (f"alter table x2.{tab} add constraint {tab}_c{when}{i} check ({s.cond(maxatoms=2)})"
               + {'valid': '', 'notvalid': ' not valid', 'notenforced': ' not enforced'}[mode])
        try:
            cur.execute(sql); n += 1
        except psycopg.Error:
            pass
    return n


def insert(cur, tab, row):
    try:
        cur.execute(f'insert into x2.{tab} values {row} on conflict do nothing')
    except psycopg.errors.CheckViolation:
        pass


def indexes(cur, s, r, tab):
    idx = []
    for i in range(r.randint(1, 4)):
        K = sorted(r.sample(range(s.n), r.randint(1, min(3, s.n))))
        P = s.cond() if r.random() < 0.85 else None
        nnd = r.random() < 0.3
        sql = (f"create unique index {tab}_u{i} on x2.{tab} ({', '.join(f'c{c}' for c in K)})"
               + (' nulls not distinct' if nnd else '') + (f' where {P}' if P else ''))
        cur.execute(sql); idx.append(dict(K=K, P=P, nnd=nnd, sql=sql))
    return idx


def setup(cur, s, r):
    cols = ', '.join(f'c{c} {s.ty[c]}' + (' not null' if s.nn[c] else '') for c in range(s.n))
    cur.execute('drop schema if exists x2 cascade'); cur.execute('create schema x2')
    cur.execute(f'create table x2.t ({cols})'); cur.execute(f'create table x2.o ({cols})')
    idx = indexes(cur, s, r, 't')
    if CHECKS: checks(cur, s, r, 't', 'before')
    rows_t = [s.row() for _ in range(r.randint(20, 60))]
    for x in rows_t: insert(cur, 't', x)
    if CHECKS: checks(cur, s, r, 't', 'after')
    if not JOINS:
        cur.execute(f"insert into x2.o values {', '.join(s.row() for _ in range(r.randint(10, 30)))}")
    else:
        cur.execute(f'create table x2.u ({cols})')
        for tab in ('o', 'u'):
            idx += indexes(cur, s, r, tab) if r.random() < 0.8 else []
            if CHECKS: checks(cur, s, r, tab, 'before')
            for _ in range(r.randint(10, 40)): insert(cur, tab, s.row())
            if CHECKS: checks(cur, s, r, tab, 'after')
        cur.execute('analyze x2.u')
    cur.execute('analyze x2.t'); cur.execute('analyze x2.o')
    return idx


def xquery(s, r, shape):
    def jn(a, b):
        J = sorted(r.sample(range(s.n), r.randint(1, min(2, s.n))))
        return ' and '.join(f'{a}.c{c} = {b}.c{c}' for c in J)
    def scope(a): return s.cond(f'{a}.', maxatoms=2) if r.random() < 0.7 else 'true'
    three = shape == 'X3' or (shape in ('XG', 'XA') and r.random() < 0.5)
    tabs = ['t', 'o'] + (['u'] if three else [])
    G = [f'{a}.c{c}' for a in tabs for c in range(s.n) if r.random() < 0.4] or ['t.c0']
    r.shuffle(G); g = ', '.join(G)
    k2 = 'left join' if shape == 'XL' or (shape != 'XD' and r.random() < 0.4) else 'join'
    sql = f'x2.t t {k2} x2.o o on {jn("t", "o")} and {scope("o")}'
    if three:
        k3 = 'left join' if r.random() < 0.5 else 'join'
        a, b = r.sample(['t', 'o'], 2)
        on3 = jn(a, 'u')
        if r.random() < 0.4: on3 += ' and ' + jn(b, 'u')          # ON clause reads both outer tables
        if r.random() < 0.3:
            x = r.randrange(s.n); on3 += f' and {b}.c{x} <> u.c{x}'
        sql += f' {k3} x2.u u on {on3} and {scope("u")}'
    w = f' where {scope("t")}'
    if r.random() < 0.35:                                       # a semi-join: adds no rows, fixes nothing
        J = sorted(r.sample(range(s.n), r.randint(1, min(2, s.n))))
        w += (f" and ({', '.join(f't.c{c}' for c in J)}) in (select {', '.join(f's.c{c}' for c in J)}"
              f" from x2.o s where {scope('s')})")
    if shape in ('XD', 'XL', 'X3'): return shape, G, f'select distinct {g} from {sql}{w}'
    if shape == 'XG': return shape, G, f'select {g} from {sql}{w} group by {g}'
    return shape, G, f'select {g}, count(*) from {sql}{w} group by {g}'


def bquery(s, r, idx):
    nn = [x for x in idx if x['P'] and re.fullmatch(r'c\d+ is not null', x['P'])]
    part = [x for x in idx if x['P']]
    x = r.choice(nn or part or idx)
    J = x['K']
    m = int(x['P'][1:].split()[0]) if x in nn else r.randrange(s.n)
    on = ' and '.join(f'o.c{c} = t.c{c}' for c in J)
    return 'B', J, f'select o.*, u.c{m} from x2.o o join x2.t t on {on} join x2.o u on t.c{m} = u.c{m}'


def query(s, r, idx=None):
    if SHAPES == ['B']:
        return bquery(s, r, idx)
    J = sorted(r.sample(range(s.n), r.randint(1, min(2, s.n))))
    on = ' and '.join(f'o.c{c} = t.c{c}' for c in J)
    P = s.cond('t.', maxatoms=3) if r.random() < 0.85 else 'true'
    shape = r.choice(SHAPES)
    if shape.startswith('X'):
        return xquery(s, r, shape)
    if shape == 'L':
        return shape, J, f'select o.* from x2.o o left join x2.t t on {on} and {P}'
    if shape == 'L2':
        m = r.randrange(s.n)
        w = f' where o.c{m} = {s.const(m)}' if r.random() < 0.5 else ''
        return shape, J, f'select o.* from x2.o o left join x2.t t on {on} and t.c{m} = o.c{m}{w}'
    if shape == 'I':
        x = r.randrange(s.n)
        return shape, J, f'select o.*, t.c{x} from x2.o o join x2.t t on {on} where {P}'
    if shape == 'S':
        oj = ', '.join(f'o.c{c}' for c in J); tj = ', '.join(f't.c{c}' for c in J)
        return shape, J, f'select o.* from x2.o o where ({oj}) in (select {tj} from x2.t t where {P})'
    if shape in ('D', 'DJ'):
        G = r.sample(range(s.n), r.randint(1, s.n))
        g = ', '.join(f't.c{c}' for c in G)
        if shape == 'D':
            return shape, G, f'select distinct {g} from x2.t t where {P}'
        return shape, G, f'select distinct {g} from x2.t t join x2.o o on {on} where {P}'
    G = r.sample(range(s.n), r.randint(2, s.n))
    g = ', '.join(f't.c{c}' for c in G)
    if shape == 'G':
        return shape, J, f'select {g}, count(*) from x2.t t where {P} group by {g}'
    if shape == 'GJ':
        return shape, J, f'select {g}, count(*) from x2.t t join x2.o o on {on} where {P} group by {g}'
    return shape, J, f'select {g}, count(*) from x2.o o left join x2.t t on {on} and {P} group by {g}'


KNOBS = ['enable_hashjoin', 'enable_mergejoin', 'enable_nestloop', 'enable_hashagg', 'enable_sort']


def run(cur, sql, on, knobs):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    for k, v in knobs.items(): cur.execute(f"set {k} = {'on' if v else 'off'}")
    cur.execute('explain (costs off) ' + sql)
    p = '\n'.join(x[0] if isinstance(x[0], str) else x[0].decode() for x in cur.fetchall())
    cur.execute(sql)
    return p, Counter(map(tuple, cur.fetchall()))


def main():
    dsn, N, Q, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    r = random.Random(seed)
    pg = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)   # schemas change between queries
    st = Counter(); bad = []; t0 = time.time()
    with pg.cursor() as cur:
        cur.execute("set client_min_messages = warning")
        for i in range(N):
            s = Schema(r)
            try:
                idx = setup(cur, s, r)
            except psycopg.Error as ex:
                st['schema errors'] += 1; continue
            st['schemas'] += 1; st['indexes'] += len(idx); st['partial indexes'] += sum(x['P'] is not None for x in idx)
            for _ in range(Q):
                shape, J, sql = query(s, r, idx)
                knobs = {k: r.random() < 0.8 for k in KNOBS}
                if not (knobs['enable_hashjoin'] or knobs['enable_mergejoin'] or knobs['enable_nestloop']):
                    knobs['enable_nestloop'] = True
                try:
                    poff, roff = run(cur, sql, False, knobs)
                    pon, ron = run(cur, sql, True, knobs)
                except psycopg.Error as ex:
                    st['query errors'] += 1; st[f'query error {type(ex).__name__}'] += 1; continue
                st['queries'] += 1; st[f'queries {shape}'] += 1
                if poff != pon:
                    st['plans changed'] += 1; st[f'plans changed {shape}'] += 1
                if roff != ron:
                    st['RESULTS DIFFER'] += 1
                    bad.append(dict(schema=[(f'c{c}', s.ty[c], s.nn[c]) for c in range(s.n)],
                                    indexes=[x['sql'] for x in idx], query=sql, knobs=knobs,
                                    plan_off=poff, plan_on=pon))
                if shape == 'L':
                    cur.execute('select * from x2.o'); removed = Counter(map(tuple, cur.fetchall()))
                    naive = any(set(x['K']) <= set(J) for x in idx)
                    if naive: st['L: naive rule licenses removal'] += 1
                    if naive and removed != roff: st['L: ... and removal is wrong on the data'] += 1
                    if 'Join' not in pon and 'Join' in poff:
                        st['L: join removed only with the patch'] += 1
                        if naive and removed != roff: st['L: ... where the naive rule would have been wrong'] += 1
                if shape.startswith('X'):
                    agg = lambda p: 'Unique' in p or 'Aggregate' in p or 'Group' in p
                    if agg(poff) and not agg(pon): st[f'{shape}: DISTINCT/GROUP BY removed'] += 1
                    keys = lambda p: [l for l in p.split('\n') if 'Key:' in l and 'Group' in l]
                    if agg(pon) and keys(poff) != keys(pon): st[f'{shape}: group key changed'] += 1
                if shape == 'D':
                    cur.execute(sql.replace('select distinct', 'select', 1)); raw = Counter(map(tuple, cur.fetchall()))
                    naive = any(set(x['K']) <= set(J) for x in idx)
                    if naive: st['D: naive rule licenses removal'] += 1
                    if naive and raw != roff: st['D: ... and removal is wrong on the data'] += 1
                    agg = lambda p: 'Unique' in p or 'Aggregate' in p
                    if agg(poff) and not agg(pon):
                        st['D: DISTINCT removed only with the patch'] += 1
                        if naive and raw != roff: st['D: ... where the naive rule would have been wrong'] += 1
            if (i + 1) % 50 == 0:
                print(f'{i + 1} schemas, {st["queries"]} queries, {st["plans changed"]} plans changed, '
                      f'{st["RESULTS DIFFER"]} results differ ({time.time() - t0:.0f}s)', flush=True)
        cur.execute('drop schema if exists x2 cascade')
    print(json.dumps(st, indent=1, sort_keys=True))
    json.dump(dict(seed=seed, N=N, Q=Q, stats=st, mismatches=bad), open(os.path.join(HERE, OUT), 'w'), indent=1)


if __name__ == '__main__':
    main()
