"""Which SEDE queries select a recommended key's scope, in the planner's sense?

se_workload.py counts a query as naming a scope if its text mentions the table and the columns of
the index predicate. This script asks the stricter question the prover asks: does the restriction
of some table instance (conjuncts of WHERE and of ON clauses that read that instance alone, as
PostgreSQL's baserestrictinfo) imply the predicate of one of the 56 recommended filtered unique
indexes? Atoms are read as the prover reads them: = c, IN (...), IS [NOT] NULL, boolean columns,
and any other comparison of the bare column with a constant as IS NOT NULL; NOT NULL columns
satisfy IS NOT NULL. Join clauses never count. Subqueries and CTEs are separate blocks.
Writes se_scope.json. Usage: python se_scope.py DSN"""
import json, os, re, sys
from collections import Counter
import psycopg
import sqlglot
from sqlglot import exp
HERE = os.path.dirname(os.path.abspath(__file__))


def lit(e):
    if isinstance(e, exp.Cast): e = e.this
    if isinstance(e, exp.Neg) and isinstance(e.this, exp.Literal): return '-' + e.this.name
    if isinstance(e, exp.Literal): return e.name
    if isinstance(e, exp.Boolean): return 'true' if e.this else 'false'
    return None


def conj(e):
    while isinstance(e, exp.Paren): e = e.this
    if isinstance(e, exp.And): return conj(e.left) + conj(e.right)
    return [e]


def atom(e):
    """(column expression, fact) or None; facts: ('val', {c..}), 'null', 'notnull'"""
    while isinstance(e, exp.Paren): e = e.this
    if isinstance(e, exp.Column): return e, ('val', {'true'})
    if isinstance(e, exp.Not):
        x = e.this
        while isinstance(x, exp.Paren): x = x.this
        if isinstance(x, exp.Is) and isinstance(x.this, exp.Column) and isinstance(x.expression, exp.Null):
            return x.this, 'notnull'
        if isinstance(x, exp.Column): return x, ('val', {'false'})
        return None
    if isinstance(e, exp.Is) and isinstance(e.this, exp.Column):
        if isinstance(e.expression, exp.Null): return e.this, 'null'
        v = lit(e.expression)
        return (e.this, ('val', {v})) if v else None
    if isinstance(e, exp.In) and isinstance(e.this, exp.Column) and e.expressions:
        vs = {lit(x) for x in e.expressions}
        return (e.this, ('val', vs)) if None not in vs else (e.this, 'notnull')
    if isinstance(e, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Like, exp.ILike)):
        a, b = e.this, e.expression
        if not isinstance(a, exp.Column): a, b = b, a
        if isinstance(a, exp.Column) and lit(b) is not None:
            return (a, ('val', {lit(b)})) if isinstance(e, exp.EQ) else (a, 'notnull')
    if isinstance(e, exp.Between) and isinstance(e.this, exp.Column): return e.this, 'notnull'
    return None


def pred_atoms(p):
    """the conjunctive predicate of a recommended index, as (column, need)"""
    out = []
    for a in re.split(r'\)\s+AND\s+\(', p.strip('()')):
        a = a.strip('()')
        m = re.fullmatch(r'(\w+) IS (NOT )?NULL', a)
        if m: out.append((m.group(1), 'notnull' if m.group(2) else 'null')); continue
        m = re.fullmatch(r"(\w+) = '?([^':]*)'?(::\w+)?", a)
        if m: out.append((m.group(1), m.group(2).lower())); continue
        raise ValueError(a)
    return out


def implied(need, facts, notnull_col):
    if need == 'null': return 'null' in facts
    if need == 'notnull':
        return notnull_col or any(f == 'notnull' or (f != 'null' and f[0] == 'val') for f in facts)
    return any(f != 'null' and f != 'notnull' and f[0] == 'val' and f[1] <= {need} for f in facts)


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True)
    cur = con.cursor()
    cur.execute("""select c.relname, i.relname, pg_get_expr(x.indpred, x.indrelid) from pg_index x
                   join pg_class c on c.oid = x.indrelid join pg_class i on i.oid = x.indexrelid
                   where i.relname like 'rec\\_%' and x.indpred is not null""")
    recs = [(t, n, pred_atoms(p)) for t, n, p in cur.fetchall()]
    cur.execute("""select table_name, column_name, is_nullable from information_schema.columns
                   where table_schema = 'public'""")
    cols, nn = {}, set()
    for t, c, n in cur.fetchall():
        cols.setdefault(t, set()).add(c)
        if n == 'NO': nn.add((t, c))
    work = [q for q in json.load(open(os.path.join(HERE, 'se_workload.json'))) if 'error' not in q]
    st, out = Counter(), []
    for q in work:
        st['planned'] += 1
        try:
            tree = sqlglot.parse_one(q['sql'], read='postgres')
        except Exception:
            st['does not parse'] += 1; continue
        hits = set()
        for sel in tree.find_all(exp.Select):
            inst = {}
            srcs = ([sel.args['from'].this] if sel.args.get('from') else []) + [j.this for j in sel.args.get('joins') or []]
            for s in srcs:
                if isinstance(s, exp.Table) and s.name.lower() in cols:
                    inst[(s.alias_or_name).lower()] = s.name.lower()
            if not inst: continue
            cs = conj(sel.args['where'].this) if sel.args.get('where') else []
            for j in sel.args.get('joins') or []:
                if j.args.get('on'): cs += conj(j.args['on'])
            facts = {}
            for c in cs:
                a = atom(c)
                if not a: continue
                col, f = a
                name, qual = col.name.lower(), col.table.lower()
                if qual: alias = qual if qual in inst else None
                else:
                    cand = [al for al, t in inst.items() if name in cols[t]]
                    alias = cand[0] if len(cand) == 1 else None
                if alias: facts.setdefault((alias, name), []).append(f)
            for al, t in inst.items():
                for rt, rn, atoms in recs:
                    if rt == t and all(implied(need, facts.get((al, c), []), (t, c) in nn) for c, need in atoms):
                        hits.add(rn)
        q2 = dict(id=q['id'], changed=q['changed'], names_filtered=q['names_filtered'], selects_scope=sorted(hits))
        out.append(q2)
        if q['names_filtered']: st['names a scope (lexical)'] += 1
        if hits:
            st['selects a scope (restriction implies predicate)'] += 1
            if q['changed']: st['... and plan changed'] += 1
    by = Counter(r for q in out for r in q['selects_scope'])
    print(json.dumps(dict(st), indent=1)); print(by.most_common())
    json.dump(dict(stats=dict(st), by_index=dict(by), queries=out), open(os.path.join(HERE, 'se_scope.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
