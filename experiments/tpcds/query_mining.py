"""Mining conditional UNIQUE candidates from the TPC-DS workload and validating them on the data.

1. Conditions. For every query block and every base-table occurrence, the conjuncts of the WHERE
   clause and of inner-join ON clauses that mention only that occurrence (no subquery) form its
   condition P, kept as exact SQL over the table (ranges, LIKE etc. included).
2. Key demands. The columns of the occurrence that the block equates with another source (join
   or correlation), groups on, projects under DISTINCT, or returns from an IN subquery: if they
   (or a subset) are a key of the table under P, the corresponding rewrite becomes possible on
   that side (join-shaped demands use U, group-shaped ones U=).
3. Validation in DuckDB at scale factors 1 and 10:
     holds    -- P : kappa(K) holds on the instance (GROUP BY K HAVING count(*) > 1 over the scope);
     uncond   -- K is a key without P (then the condition adds nothing);
     declared -- K contains the primary key (trivially a key);
     param    -- for conditions made of equalities and IN-lists on columns E, the key holds for
                 every value of E: K + E is a key without the condition while E alone is not
                 (otherwise the scope has one row per value and the test says nothing),
                 i.e. the key does not depend on the substitution parameters of the query.
4. Discovery. For each distinct condition on a dimension table with a scope of at most 200,000
   rows, FixC (experiments/sql_unique/fixc.py) lists the minimal keys of at most two columns
   under P, at SF1, re-checked at SF10; we count those that are not keys without P, and, for
   conditions of equalities and IN-lists, those that are parameter-independent as above.
Writes query_mining.json. Usage: python query_mining.py WORKDIR"""
import json, os, sys, time
from collections import Counter, defaultdict
import duckdb, sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'sql_unique'))
from load_tpcds import PK
from fixc import fixc

FACT = {'store_sales', 'store_returns', 'catalog_sales', 'catalog_returns', 'web_sales', 'web_returns', 'inventory'}


def conjuncts(e):
    if e is None: return []
    e = e.this if isinstance(e, exp.Where) else e
    return list(e.flatten()) if isinstance(e, exp.And) else [e]


def local_sql(c, alias):
    if c.find(exp.Subquery, exp.Select) is not None: return None
    cols = list(c.find_all(exp.Column))
    if not cols or any(x.table != alias for x in cols): return None
    c = c.copy()
    for x in c.find_all(exp.Column): x.set('table', None)
    return c


def eq_only(conds):
    """columns of a condition made only of col = const / col IN (consts), else None"""
    out = set()
    for c in conds:
        c = c.unnest() if hasattr(c, 'unnest') else c
        if isinstance(c, exp.EQ) and isinstance(c.this, exp.Column) and isinstance(c.expression, exp.Literal): out.add(c.this.name)
        elif isinstance(c, exp.In) and isinstance(c.this, exp.Column) and all(isinstance(v, exp.Literal) for v in c.expressions): out.add(c.this.name)
        else: return None
    return out


def mine(Q, schema):
    occ = []                                   # (query, scope, table, condition SQL, demands)
    for n, q in Q:
        e = qualify(sqlglot.parse_one(q, read='duckdb'), schema=schema, dialect='duckdb')
        for si, sc in enumerate(traverse_scope(e)):
            sel = sc.expression
            if not isinstance(sel, exp.Select): continue
            src = {a: s for a, (_, s) in sc.selected_sources.items()}
            tables = {a: s.name for a, s in src.items() if isinstance(s, exp.Table) and s.name in schema}
            cs = conjuncts(sel.args.get('where'))
            for j in sel.args.get('joins') or []:
                if (j.args.get('side') or '').upper() in ('', 'INNER') or not j.args.get('side'):
                    cs += conjuncts(j.args.get('on'))
            dem = defaultdict(list)
            for c in cs:                        # equi-joins and correlations
                if isinstance(c, exp.EQ) and isinstance(c.this, exp.Column) and isinstance(c.expression, exp.Column):
                    for x, y in ((c.this, c.expression), (c.expression, c.this)):
                        if x.table in tables and y.table != x.table:
                            dem[(x.table, 'join', y.table)].append(x.name)
            g = sel.args.get('group')
            if g and not g.args.get('rollup') and not g.args.get('cube'):
                for x in g.expressions:
                    if isinstance(x, exp.Column) and x.table in tables: dem[(x.table, 'group', '')].append(x.name)
            if sel.args.get('distinct'):
                for p in sel.expressions:
                    x = p.unalias()
                    if isinstance(x, exp.Column) and x.table in tables: dem[(x.table, 'distinct', '')].append(x.name)
            par = sel.parent
            while isinstance(par, (exp.Paren, exp.Subquery)): par = par.parent
            if isinstance(par, exp.In) and sel.expressions:
                x = sel.expressions[0].unalias()
                if isinstance(x, exp.Column) and x.table in tables: dem[(x.table, 'in', '')].append(x.name)
            for a, t in tables.items():
                conds = [l for l in (local_sql(c, a) for c in cs) if l is not None]
                if not conds: continue
                P = ' AND '.join(f'({c.sql(dialect="duckdb")})' for c in conds)
                ds = [(kind, sorted(set(cols))) for (al, kind, _), cols in dem.items() if al == a]
                occ.append(dict(query=n, scope=si, table=t, P=P, eqcols=sorted(eq_only(conds) or []),
                                eqonly=eq_only(conds) is not None, demands=ds))
    return occ


def dup_count(con, t, P, K, sem):
    if not K: return con.execute(f'select count(*) > 1 from {t} where {P}').fetchone()[0] * 1
    nn = '' if sem == 'Ueq' else ' and ' + ' and '.join(f'{k} is not null' for k in K)
    return con.execute(f"select count(*) from (select 1 from {t} where ({P}){nn} group by {', '.join(K)} "
                       f"having count(*) > 1)").fetchone()[0]


def param(con, t, K, E, sem):
    """K is a key for every value of the condition columns E, and E alone is not a key"""
    if not E or dup_count(con, t, 'TRUE', sorted(E), sem) == 0: return False
    return dup_count(con, t, 'TRUE', sorted(set(K) | set(E)), sem) == 0


def main():
    work = sys.argv[1]
    cons = {sf: duckdb.connect(os.path.join(work, f'tpcds_sf{sf}.duckdb'), read_only=True) for sf in (1, 10)}
    schema = {}
    for t, c, ty in cons[1].execute("select table_name, column_name, data_type from duckdb_columns() "
                                    "where schema_name='main' order by table_name, column_index").fetchall():
        if t in PK: schema.setdefault(t, {})[c] = ty
    Q = json.load(open(os.path.join(work, 'queries.json')))
    t0 = time.time()
    occ = mine(Q, schema)
    conds = {}
    for o in occ: conds.setdefault((o['table'], o['P']), o)
    print(f'{len(occ)} table occurrences with local predicates in {len({o["query"] for o in occ})} queries; '
          f'{len(conds)} distinct conditions on {len({t for t, _ in conds})} tables ({time.time() - t0:.1f}s)', flush=True)
    # targeted validation of the demands
    demands = {}
    for o in occ:
        for kind, K in o['demands']:
            sem = 'U' if kind in ('join', 'in') else 'Ueq'
            demands.setdefault((o['table'], o['P'], tuple(K), sem), dict(o, kind=kind, K=K, sem=sem))
    res = []
    for (t, P, K, sem), d in demands.items():
        r = dict(table=t, P=P, K=list(K), sem=sem, kind=d['kind'], query=d['query'])
        r['scope_sf1'] = cons[1].execute(f'select count(*) from {t} where {P}').fetchone()[0]
        for sf in (1, 10):
            r[f'holds_sf{sf}'] = dup_count(cons[sf], t, P, list(K), sem) == 0
            r[f'uncond_sf{sf}'] = dup_count(cons[sf], t, 'TRUE', list(K), sem) == 0
        r['declared'] = set(PK[t]) <= set(K)
        if d['eqonly'] and r['holds_sf1']:
            r['param_sf1'] = param(cons[1], t, list(K), d['eqcols'], sem)
        res.append(r)
    c = Counter()
    for r in res:
        c['demands'] += 1
        if r['holds_sf1']: c['hold at SF1'] += 1
        if r['holds_sf1'] and r['holds_sf10']: c['hold at SF1 and SF10'] += 1
        if r['holds_sf1'] and r['holds_sf10'] and not r['declared']: c['... not containing the primary key'] += 1
        if r['holds_sf1'] and r['holds_sf10'] and not r['declared'] and not r['uncond_sf1']: c['... and conditional (not a key without P)'] += 1
        if r.get('param_sf1') and r['holds_sf10'] and not r['declared'] and not r['uncond_sf1']: c['... and independent of the parameter values'] += 1
    print(json.dumps(c, indent=1), flush=True)
    for r in res:
        if r['holds_sf1'] and r['holds_sf10'] and not r['declared'] and not r['uncond_sf1']:
            print(f"  q{r['query']} {r['kind']:8s} {r['table']}: {r['sem']}({','.join(r['K'])}) WHERE {r['P'][:110]} "
                  f"scope {r['scope_sf1']} param {r.get('param_sf1')}")
    # discovery under each mined condition (dimension tables, scope <= 200k rows)
    disc = []
    for (t, P), o in conds.items():
        if t in FACT: continue
        n = cons[1].execute(f'select count(*) from {t} where {P}').fetchone()[0]
        if n > 200000 or n < 2: continue
        cols = list(schema[t])
        rows = [dict(zip(cols, r)) for r in cons[1].execute(f'select * from {t} where {P}').fetchall()]
        full = [{A: ('any',) for A in cols}]
        allrows = None
        for sem in ('U', 'Ueq'):
            t1 = time.perf_counter()
            ks, _ = fixc(rows, cols, full, sem, 2)
            ms = (time.perf_counter() - t1) * 1e3
            new = [K for K in ks if K and not set(PK[t]) <= K and dup_count(cons[1], t, 'TRUE', sorted(K), sem) > 0]
            stable = [K for K in new if dup_count(cons[10], t, P, sorted(K), sem) == 0]
            par = [K for K in stable if o['eqonly'] and param(cons[1], t, sorted(K), o['eqcols'], sem)
                   and param(cons[10], t, sorted(K), o['eqcols'], sem)]
            disc.append(dict(table=t, P=P, sem=sem, scope=n, keys=len(ks), conditional=len(new), stable=len(stable),
                             param=len(par), eqonly=o['eqonly'], ms=ms, examples=[sorted(K) for K in stable[:3]],
                             param_examples=[sorted(K) for K in par[:3]]))
    cnt = Counter();
    for d in disc:
        cnt['conditions x semantics'] += 1; cnt['minimal keys (<=2 cols)'] += d['keys']
        cnt['conditional keys (not keys without P)'] += d['conditional']; cnt['... also at SF10'] += d['stable']
        cnt['conditions with a stable conditional key'] += d['stable'] > 0
        cnt['... of equalities/IN-lists'] += d['eqonly']
        cnt['stable conditional keys under equality/IN conditions'] += d['stable'] if d['eqonly'] else 0
        cnt['... parameter-independent at SF1 and SF10'] += d['param']
        b = '<100' if d['scope'] < 100 else '<1000' if d['scope'] < 1000 else '>=1000'
        cnt[f'stable conditional keys, scope {b}'] += d['stable']
        cnt['FixC ms total'] += round(d['ms'])
    print(json.dumps(cnt, indent=1))
    for d in [d for d in disc if d['param']][:12]:
        print(f"  PARAM {d['table']} {d['sem']} WHERE {d['P'][:70]}: {d['param']} e.g. {d['param_examples']}")
    for d in sorted(disc, key=lambda d: -d['stable'])[:6]:
        print(f"  {d['table']} {d['sem']} WHERE {d['P'][:90]}: scope {d['scope']}, {d['stable']} stable conditional, e.g. {d['examples']}")
    json.dump(dict(occurrences=occ, demands=res, discovery=disc), open(os.path.join(HERE, 'query_mining.json'), 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
