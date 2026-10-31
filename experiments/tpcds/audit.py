"""Which TPC-DS query blocks can a key-aware optimiser simplify, and which keys does it need?

For every query block (sqlglot scope) of the 99 TPC-DS queries we look at the constructs whose
work a key makes redundant:
  DISTINCT       SELECT DISTINCT X ...            redundant if X (plain columns) is a domain key of
                                                  the block's input
  GROUPBY        GROUP BY X (no ROLLUP)           each group has one row if X is a domain key
  SEMIJOIN       x IN (SELECT y ...), EXISTS      may become a join if the subquery's input has a
                                                  possible key on y (on its correlation columns)
  SETOP          INTERSECT / EXCEPT (distinct)    may become ... ALL if its left input is
                                                  duplicate-free (trivially so if it is DISTINCT or
                                                  grouped, which we count separately)
Keys of a block's input: every base table gets the condition its local predicates impose (=, IN,
IS [NOT] NULL, any other comparison and every equi-join require a value), and a table is
determined once one of its keys, implied under that condition, lies in the closure of the tested
columns under the block's column equalities; a derived table is determined by its GROUP BY
columns (or all columns if it is DISTINCT). The tested columns are a key iff every source is
determined. Implication: experiments/reasoning/implication.py (Algorithm 1 with reductions for
b <= 10, else SAT).

Catalogs (cumulative):
  pk     primary keys of the TPC-DS specification, NOT NULL on key and business-key columns
  bk     + unconditional business keys of the non-versioned tables (UNIQUE), and UNIQUE (d_date)
  scd    + the business keys of the five versioned dimensions, unique among current rows:
         UNIQUE (i_item_id) WHERE i_rec_end_date IS NULL, etc.
  mined-unc  + unconditional keys mined on the generated dimension tables that hold at scale
             factors 1 and 10 (mined.json, 'stable')
  mined      + the conditional keys mined there that hold at both scale factors
Usage: python audit.py WORKDIR  (WORKDIR holds tpcds_sf1.duckdb and queries.json)"""
import itertools, json, os, sys, time
from collections import Counter, defaultdict
import duckdb, sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'reasoning'))
sys.path.insert(0, HERE)
from implication import implies_pruned, implies_sat, open_positions
from load_tpcds import PK, BUSINESS

SCD = {'item': ('i_item_id', 'i_rec_end_date'), 'store': ('s_store_id', 's_rec_end_date'),
       'call_center': ('cc_call_center_id', 'cc_rec_end_date'), 'web_page': ('wp_web_page_id', 'wp_rec_end_date'),
       'web_site': ('web_site_id', 'web_rec_end_date')}


class Catalog:
    def __init__(self, schema, level, mined=None):
        self.schema = schema; self.enc = {}; self.S = {}; self.NN = {}
        for t, cols in schema.items():
            bot = {c: '_' for c in cols}
            S = [([dict(bot)], 'pos', frozenset(PK[t]))]
            if level in ('bk', 'scd', 'mined-unc', 'mined'):
                if t in BUSINESS and t not in SCD: S.append(([dict(bot)], 'pos', frozenset([BUSINESS[t]])))
                if t == 'date_dim': S.append(([dict(bot)], 'pos', frozenset(['d_date'])))
            if level in ('scd', 'mined-unc', 'mined') and t in SCD:
                k, e = SCD[t]; S.append(([dict(bot, **{e: 'N'})], 'pos', frozenset([k])))
            if level in ('mined-unc', 'mined') and mined:
                for m in mined.get(t, []):
                    if m['kind'] == 'conditional' and level != 'mined': continue
                    if not m.get('stable', True): continue
                    temps = [{c: (tuple(v) if isinstance(v, list) else v) for c, v in tp.items()} for tp in m['temps']]
                    S.append(([self.template(t, tp) for tp in temps], m['cls'], frozenset(m['K'])))
            self.S[t] = S
            self.NN[t] = set(PK[t]) | ({BUSINESS[t]} if t in BUSINESS else set())
        self.cache = {}

    def code(self, t, c, v):
        return self.enc.setdefault((t, c, str(v)), len(self.enc) + 1)

    def template(self, t, tp):
        out = {c: '_' for c in self.schema[t]}
        for c, s in tp.items():
            out[c] = self.code(t, c, s[1]) if isinstance(s, tuple) else s
        return out

    def keys(self, t):
        return {K for _, _, K in self.S[t]}

    def implied(self, t, temps, cls, K):
        key = (t, json.dumps(temps, sort_keys=True, default=str), cls, tuple(sorted(K)))
        if key in self.cache: return self.cache[key]
        cols = list(self.schema[t]); phi = ([self.template(t, tp) for tp in temps], cls, frozenset(K))
        b = open_positions(cols, self.NN[t], self.S[t], phi)
        r = implies_pruned(cols, self.NN[t], self.S[t], phi) if b <= 10 else implies_sat(cols, self.NN[t], self.S[t], phi)
        self.cache[key] = r
        return r


# ------------------------------------------------------------------ predicates of a block
def _col(e):
    while isinstance(e, exp.Paren): e = e.this
    return e if isinstance(e, exp.Column) else None


def _lit(e):
    while isinstance(e, (exp.Paren, exp.Cast)): e = e.this
    if isinstance(e, exp.Literal): return e.this
    if isinstance(e, exp.Neg) and isinstance(e.this, exp.Literal): return '-' + e.this.this
    return None


def atoms(e):
    """conjunct -> (alias, [templates over that alias]) or ('EQ', a, b) for column equalities, or None"""
    while isinstance(e, exp.Paren): e = e.this
    if isinstance(e, exp.EQ):
        l, r = _col(e.this), _col(e.expression)
        if l is not None and r is not None:
            return ('EQ', (l.table, l.name), (r.table, r.name))
        c, v = (l, _lit(e.expression)) if l is not None else (r, _lit(e.this))
        if c is not None: return (c.table, [{c.name: ('C', v)}] if v is not None else [{c.name: 'T'}])
        return None
    if isinstance(e, exp.In) and _col(e.this) is not None and not e.args.get('query'):
        c = _col(e.this); vs = [_lit(x) for x in e.expressions]
        return (c.table, [{c.name: ('C', v)} for v in vs]) if all(v is not None for v in vs) else (c.table, [{c.name: 'T'}])
    if isinstance(e, exp.Is) and isinstance(e.expression, exp.Null) and _col(e.this) is not None:
        return (_col(e.this).table, [{_col(e.this).name: 'N'}])
    if isinstance(e, exp.Not):
        x = e.this
        while isinstance(x, exp.Paren): x = x.this
        if isinstance(x, exp.Is) and isinstance(x.expression, exp.Null) and _col(x.this) is not None:
            return (_col(x.this).table, [{_col(x.this).name: 'T'}])
        return None
    if isinstance(e, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.NEQ, exp.Like, exp.Between)):
        cs = [c for c in (e.this, e.args.get('expression'), e.args.get('low'), e.args.get('high')) if c is not None and _col(c) is not None]
        if len({_col(c).table for c in cs}) == 1 and cs:
            return (_col(cs[0]).table, [{_col(c).name: 'T' for c in cs}])
        return ('MULTI', [(_col(c).table, _col(c).name) for c in cs])
    if isinstance(e, exp.Or):
        parts = [atoms(x) for x in e.flatten()]
        if all(p and p[0] not in ('EQ', 'MULTI') for p in parts) and len({p[0] for p in parts}) == 1:
            return (parts[0][0], [t for p in parts for t in p[1]])
    return None


def conj(tps1, tps2):
    out = []
    for a in tps1:
        for b in tps2:
            m = dict(a); ok = True
            for c, s in b.items():
                if c not in m or m[c] == s: m[c] = s
                elif m[c] == 'T' and isinstance(s, tuple): m[c] = s
                elif s == 'T' and isinstance(m[c], tuple): pass
                else: ok = False
            if ok: out.append(m)
    return out


class Block:
    """a SELECT scope: its base tables (alias -> table), derived sources, conditions, equalities"""
    def __init__(self, scope, keys_of_scope):
        self.scope = scope; sel = scope.expression
        src = {a: s for a, (_, s) in scope.selected_sources.items()}    # FROM/JOIN sources only
        self.tables = {a: s.name for a, s in src.items() if isinstance(s, exp.Table)}
        self.derived = {a: s for a, s in src.items() if not isinstance(s, exp.Table)}
        self.cond = {a: [{}] for a in self.tables}
        self.eq = []
        self.outer = set()
        cs = []
        if sel.args.get('where'): cs += list(sel.args['where'].this.flatten()) if isinstance(sel.args['where'].this, exp.And) else [sel.args['where'].this]
        for j in sel.args.get('joins') or []:
            side = (j.args.get('side') or '').upper()
            on = j.args.get('on')
            if side in ('LEFT', 'RIGHT', 'FULL'): self.outer.add(j.this.alias_or_name)
            if on is not None: cs += list(on.flatten()) if isinstance(on, exp.And) else [on]
        self.correl = []     # (inner column, outer column) equalities with columns of enclosing scopes
        for c in cs:
            a = atoms(c)
            if a is None: continue
            if a[0] == 'EQ':
                (ta, ca), (tb, cb) = a[1], a[2]
                ina, inb = ta in src, tb in src
                if ina and inb: self.eq.append(((ta, ca), (tb, cb)))
                elif ina: self.correl.append((ta, ca))
                elif inb: self.correl.append((tb, cb))
                for t, col in ((ta, ca), (tb, cb)):
                    if t in self.tables: self.cond[t] = conj(self.cond[t], [{col: 'T'}])
            elif a[0] == 'MULTI':
                for t, col in a[1]:
                    if t in self.tables: self.cond[t] = conj(self.cond[t], [{col: 'T'}])
            elif a[0] in self.tables:
                self.cond[a[0]] = conj(self.cond[a[0]], a[1])
        self.keys_of_scope = keys_of_scope

    def is_key(self, cat, X, cls):
        """is the set X of (alias, column) a key of cls on the block's input?"""
        clo = set(X); done = set()
        changed = True
        while changed:
            changed = False
            for a, b in self.eq:
                if a in clo and b not in clo: clo.add(b); changed = True
                if b in clo and a not in clo: clo.add(a); changed = True
            for a, t in self.tables.items():
                if a in done: continue
                cols = {c for (al, c) in clo if al == a}
                for K in cat.keys(t):
                    if K <= cols and cat.implied(t, self.cond[a], cls, K):
                        done.add(a); clo |= {(a, c) for c in cat.schema[t]}; changed = True; break
            for a, s in self.derived.items():
                ks = self.keys_of_scope(s, cat)
                if a in done: continue
                cols = {c for (al, c) in clo if al == a}
                if any(k is not None and k <= cols for k in ks):
                    done.add(a); changed = True
                    clo |= {(a, c) for k in ks if k for c in k}
        return set(self.tables) | set(self.derived) <= done


_KEYS = {}


def output_keys(scope, cat):
    """keys of a derived table's output (sets of output column names): all columns of a
    duplicate-eliminating set operation or DISTINCT block, the GROUP BY columns, and otherwise the
    projected columns (singly or together) that are domain keys of the block's input"""
    k = (id(scope), id(cat))
    if k in _KEYS: return _KEYS[k]
    _KEYS[k] = []                                    # guards recursion
    sel = scope.expression
    out = []
    if isinstance(sel, (exp.Union, exp.Intersect, exp.Except)):
        left = sel
        while not isinstance(left, exp.Select) and left is not None: left = left.this
        if sel.args.get('distinct') is not False and isinstance(sel, (exp.Intersect, exp.Except, exp.Union)) and left is not None:
            out = [frozenset(p.alias_or_name for p in left.expressions)]
    elif isinstance(sel, exp.Select):
        outs = {}
        for p in sel.expressions:
            c = _col(p.unalias()) if isinstance(p, exp.Alias) else _col(p)
            if c is not None: outs[(c.table, c.name)] = p.alias_or_name
        g = sel.args.get('group')
        if sel.args.get('distinct'):
            out = [frozenset(p.alias_or_name for p in sel.expressions)]
        elif g and not g.args.get('rollup') and not g.args.get('cube') and g.expressions:
            ks = []
            for e in g.expressions:
                c = _col(e)
                if c is None or (c.table, c.name) not in outs: ks = None; break
                ks.append(outs[(c.table, c.name)])
            out = [frozenset(ks)] if ks else []
        elif outs and not g:
            blk = Block(scope, output_keys)
            for X in [{x} for x in outs] + [set(outs)]:
                if blk.is_key(cat, X, 'dom'):
                    out.append(frozenset(outs[x] for x in X))
    _KEYS[k] = out
    return out


def analyse(q, schema, cats):
    e = qualify(sqlglot.parse_one(q, read='duckdb'), schema=schema, dialect='duckdb')
    scopes = list(traverse_scope(e))
    keys_of = output_keys
    res = []
    for si, sc in enumerate(scopes):
        sel = sc.expression
        if not isinstance(sel, exp.Select): continue
        blk = Block(sc, keys_of)
        def test(kind, X, cls):
            res.append(dict(kind=kind, scope=si, cols=sorted(f'{a}.{c}' for a, c in X),
                            **{lv: blk.is_key(cat, X, cls) for lv, cat in cats.items()}))
        projected = [(_col(p.unalias()) if isinstance(p, exp.Alias) else _col(p)) for p in sel.expressions]
        if sel.args.get('distinct') and projected and all(c is not None for c in projected):
            test('DISTINCT', {(c.table, c.name) for c in projected}, 'dom')
        g = sel.args.get('group')
        if g and not g.args.get('rollup') and not g.args.get('cube') and g.expressions:
            X = {(c.table, c.name) for c in (_col(x) for x in g.expressions) if c is not None}
            if X: test('GROUPBY', X, 'dom')
        # subqueries used as semi-joins: IN (SELECT y ...) and EXISTS (correlated)
        par = sel.parent
        while isinstance(par, (exp.Paren, exp.Subquery)): par = par.parent
        if isinstance(par, exp.In) and projected and projected[0] is not None:
            test('SEMIJOIN-IN', {(projected[0].table, projected[0].name)}, 'pos')
        if isinstance(par, exp.Exists) and blk.correl:
            test('SEMIJOIN-EXISTS', set(blk.correl), 'pos')
    # set operations
    for u in e.find_all(exp.Intersect, exp.Except):
        if u.args.get('distinct') is False: continue
        left = u.this
        while isinstance(left, (exp.Paren, exp.Subquery)): left = left.this
        trivial = isinstance(left, exp.Select) and (left.args.get('distinct') or left.args.get('group'))
        res.append(dict(kind='SETOP', cols=[], trivial=bool(trivial), **{lv: bool(trivial) for lv in cats}))
    return res, len(scopes)


def main():
    work = sys.argv[1]
    con = duckdb.connect(os.path.join(work, 'tpcds_sf1.duckdb'), read_only=True)
    schema = {}
    for t, c, ty in con.execute("select table_name, column_name, data_type from duckdb_columns() "
                                "where schema_name='main' order by table_name, column_index").fetchall():
        if t in PK: schema.setdefault(t, {})[c] = ty
    mined = json.load(open(os.path.join(HERE, 'mined.json'))) if os.path.exists(os.path.join(HERE, 'mined.json')) else None
    levels = ['pk', 'bk', 'scd'] + (['mined-unc', 'mined'] if mined else [])
    cats = {lv: Catalog(schema, lv, mined) for lv in levels}
    Q = json.load(open(os.path.join(work, 'queries.json')))
    out = []; t0 = time.time(); nb = 0
    for n, q in Q:
        r, k = analyse(q, schema, cats); nb += k
        for x in r: x['query'] = n
        out += r
    print(f'{len(Q)} queries, {nb} blocks, {len(out)} constructs, {time.time() - t0:.1f}s')
    by = defaultdict(Counter)
    for x in out:
        by[x['kind']]['n'] += 1
        for lv in levels: by[x['kind']][lv] += x[lv]
    for k, v in sorted(by.items()):
        print(f"{k:16s} n={v['n']:3d} " + ' '.join(f'{lv}={v[lv]}' for lv in levels))
    for x in out:
        if any(x[lv] for lv in levels) and x['kind'] != 'SETOP':
            print('  q%-3d %-15s %s %s' % (x['query'], x['kind'], ','.join(x['cols'])[:70], {lv: x[lv] for lv in levels}))
    json.dump(dict(levels=levels, constructs=out), open(os.path.join(HERE, 'audit.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
