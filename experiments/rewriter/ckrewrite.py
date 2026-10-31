"""A SQL rewrite layer that uses conditional keys from the PostgreSQL catalog.

Catalog: for a table, the unique indexes (with their predicates, NULLS NOT DISTINCT flag and key
columns; an index on the constant (1) is a key over no columns) and the CHECK constraints of the
form  NOT (P) OR (k1 IS NOT NULL AND ...),  read from pg_index / pg_constraint, and the NOT NULL
columns. A unique index on K WHERE P is the conditional possible key C_P:pos(K) (domain key with
NULLS NOT DISTINCT), a CHECK as above the completeness constraint C_P:nn(k1...). Predicates are
translated to conditions exactly (=, IS NULL, IS NOT NULL, IN, AND, OR); an index predicate that
cannot be translated exactly is ignored, a query predicate is over-approximated (any other
comparison on a column requires a value there), which keeps every decision sound.

Rewrites (Table "Rewrites" of the paper):
  SELECT DISTINCT K FROM t WHERE P                     -> drop DISTINCT      if C_P:dom(K) is implied
  SELECT K, count(*) FROM t WHERE P GROUP BY K         -> SELECT K, 1 ...    if C_P:dom(K) is implied
  SELECT a.* FROM t a LEFT JOIN (SELECT * FROM t WHERE P) b ON a.K = b.K
                                                       -> drop the join     if C_P:pos(K) is implied
                                                          and the query uses no column of b
Implication: Algorithm 1 with compatibility pruning and dominance when b <= 10, else SAT
(experiments/reasoning/implication.py)."""
import os, sys, time
import sqlglot
from sqlglot import exp
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'reasoning'))
from implication import implies_pruned, implies_sat, open_positions

BMAX = 10


class Untranslatable(Exception):
    pass


def _strip(e):
    while isinstance(e, (exp.Cast, exp.Paren)): e = e.this
    return e


def _col(e):
    e = _strip(e)
    if isinstance(e, exp.Column): return e.name
    raise Untranslatable(e.sql())


def _lit(e):
    e = _strip(e)
    if isinstance(e, exp.Literal): return e.this
    if isinstance(e, exp.Neg) and isinstance(_strip(e.this), exp.Literal): return '-' + _strip(e.this).this
    raise Untranslatable(e.sql())


def dnf(e, exact):
    """predicate -> list of templates {col: 'T' | 'N' | ('C', value)}; exact=False allows the
    over-approximation of other comparisons by 'T'"""
    e = _strip(e)
    if isinstance(e, exp.Or): return dnf(e.this, exact) + dnf(e.expression, exact)
    if isinstance(e, exp.And):
        out = []
        for a in dnf(e.this, exact):
            for b in dnf(e.expression, exact):
                m = dict(a)
                ok = True
                for c, s in b.items():
                    if c in m and m[c] != s:
                        if {m[c], s} == {'T'} or 'T' in (m[c], s) and 'N' not in (m[c], s):
                            m[c] = s if m[c] == 'T' else m[c]        # T and a constant: the constant
                        else: ok = False                              # contradictory: empty template
                    else: m[c] = s
                if ok: out.append(m)
        return out
    if isinstance(e, exp.Is) and isinstance(_strip(e.expression), exp.Null): return [{_col(e.this): 'N'}]
    if isinstance(e, exp.Not):
        x = _strip(e.this)
        if isinstance(x, exp.Is) and isinstance(_strip(x.expression), exp.Null): return [{_col(x.this): 'T'}]
        raise Untranslatable(e.sql())
    if isinstance(e, exp.EQ):
        r = _strip(e.expression)
        if isinstance(r, exp.Any):                       # PostgreSQL's form of IN: = ANY (ARRAY[...])
            arr = _strip(r.this)
            if not isinstance(arr, exp.Array): raise Untranslatable(e.sql())
            return [{_col(e.this): ('C', _lit(v))} for v in arr.expressions]
        return [{_col(e.this): ('C', _lit(e.expression))}]
    if isinstance(e, exp.In): return [{_col(e.this): ('C', _lit(v))} for v in e.expressions]
    if not exact and isinstance(e, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.NEQ, exp.Like)):
        return [{_col(e.this): 'T'}]
    raise Untranslatable(e.sql())


class Catalog:
    def __init__(self, conn, table):
        self.table = table
        t0 = time.perf_counter()
        with conn.cursor() as cur:
            rel = '"' + table.replace('"', '""') + '"'
            cur.execute("""SELECT attname, attnotnull FROM pg_attribute
                           WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped""", (rel,))
            att = cur.fetchall()
            self.cols = [a for a, _ in att]; self.NN = {a for a, nn in att if nn}
            cur.execute("""SELECT ix.indnullsnotdistinct, pg_get_expr(ix.indpred, ix.indrelid),
                                  ARRAY(SELECT pg_get_indexdef(ix.indexrelid, k, true)
                                        FROM generate_series(1, ix.indnkeyatts) AS k)
                           FROM pg_index ix WHERE ix.indrelid = %s::regclass AND ix.indisunique""", (rel,))
            idx = cur.fetchall()
            cur.execute("""SELECT pg_get_constraintdef(oid) FROM pg_constraint
                           WHERE conrelid = %s::regclass AND contype = 'c'""", (rel,))
            checks = [r[0] for r in cur.fetchall()]
        self.read_ms = (time.perf_counter() - t0) * 1e3
        self.enc = {}
        self.Sigma, self.ignored = [], 0
        for nnd, pred, keys in idx:
            try:
                temps = dnf(sqlglot.parse_one(pred, read='postgres'), True) if pred else [{}]
                K = frozenset() if keys == ['1'] or keys == ['(1)'] else frozenset(k.strip('"') for k in keys)
                if not K <= set(self.cols): raise Untranslatable(keys)
            except (Untranslatable, sqlglot.errors.ParseError):
                self.ignored += 1; continue
            self.Sigma.append(([self.template(t) for t in temps], 'dom' if nnd else 'pos', K))
        for c in checks:
            try:
                e = _strip(sqlglot.parse_one(c[len('CHECK '):], read='postgres'))
                if not isinstance(e, exp.Or) or not isinstance(_strip(e.this), exp.Not): raise Untranslatable(c)
                temps = dnf(_strip(e.this).this, True)
                rhs = dnf(e.expression, True)
                if len(rhs) != 1 or any(s != 'T' for s in rhs[0].values()): raise Untranslatable(c)
            except (Untranslatable, sqlglot.errors.ParseError):
                self.ignored += 1; continue
            self.Sigma.append(([self.template(t) for t in temps], 'nn', frozenset(rhs[0])))

    def code(self, c, v):
        return self.enc.setdefault((c, v), len(self.enc) + 1)

    def template(self, t):
        out = {A: '_' for A in self.cols}
        for c, s in t.items():
            out[c] = self.code(c, s[1]) if isinstance(s, tuple) else s
        return out

    def implies(self, temps, cls, K):
        phi = ([self.template(t) for t in temps], cls, frozenset(K))
        b = open_positions(self.cols, self.NN, self.Sigma, phi)
        if b <= BMAX: return implies_pruned(self.cols, self.NN, self.Sigma, phi), b, 'alg1'
        return implies_sat(self.cols, self.NN, self.Sigma, phi), b, 'sat'


def rewrite(sql, catalogs):
    """returns (rewritten sql or None, info)"""
    q = sqlglot.parse_one(sql, read='postgres')
    info = {}
    if not isinstance(q, exp.Select): return None, info
    frm = q.args.get('from')
    base = _strip(frm.this) if frm else None
    if not isinstance(base, exp.Table) or base.name not in catalogs: return None, info
    cat = catalogs[base.name]
    joins = q.args.get('joins') or []
    where = q.args.get('where')
    try:
        if not joins and (q.args.get('distinct') or q.args.get('group')):
            K = [_col(c) for c in (q.args['group'].expressions if q.args.get('group') else q.expressions)]
            temps = dnf(where.this, False) if where else [{}]
            ok, b, how = cat.implies(temps, 'dom', K)
            info.update(kind='GROUPBY' if q.args.get('group') else 'DISTINCT', implied=ok, b=b, solver=how)
            if not ok: return None, info
            q2 = q.copy()
            if q.args.get('group'):
                q2.set('group', None)
                q2.set('expressions', [e if not isinstance(e.unalias(), exp.Count) else exp.alias_(exp.Literal.number(1), e.alias or 'n')
                                       for e in q2.expressions])
            else:
                q2.set('distinct', None)
            return q2.sql(dialect='postgres'), info
        if len(joins) == 1 and joins[0].args.get('side') == 'LEFT':
            j = joins[0]; sub = _strip(j.this)
            alias_b = j.this.alias_or_name
            inner = sub.this if isinstance(sub, exp.Subquery) else sub
            if not (isinstance(inner, exp.Select) and isinstance(_strip(inner.args['from'].this), exp.Table)
                    and _strip(inner.args['from'].this).name == base.name): return None, info
            if any(c.table == alias_b for c in q.find_all(exp.Column) if c.parent_select is q and not c.find_ancestor(exp.Join)):
                return None, info                                  # the query uses columns of b
            on = _strip(j.args['on'])
            conj = list(on.flatten()) if isinstance(on, exp.And) else [on]
            K = []
            for c in conj:
                c = _strip(c)
                if not isinstance(c, exp.EQ): return None, info
                l, r = _strip(c.this), _strip(c.expression)
                if not (isinstance(l, exp.Column) and isinstance(r, exp.Column) and l.name == r.name): return None, info
                K.append(l.name)
            iw = inner.args.get('where')
            temps = dnf(iw.this, False) if iw else [{}]
            ok, b, how = cat.implies(temps, 'pos', K)
            info.update(kind='LEFTJOIN', implied=ok, b=b, solver=how)
            if not ok: return None, info
            q2 = q.copy(); q2.set('joins', None)
            return q2.sql(dialect='postgres'), info
    except Untranslatable:
        info['untranslatable'] = True
    return None, info
