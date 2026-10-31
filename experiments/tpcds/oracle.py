"""Data-level upper bound for audit.py: for each construct, does the uniqueness that would make it
redundant actually hold on the generated data? If not, no declared key, conditional or not, can
license the rewrite. For a block and tested columns X we run, in DuckDB, the block's FROM and
WHERE with the select list replaced by count(*) and GROUP BY X (correlation predicates of
EXISTS subqueries are dropped, so the groups are the matches per outer value; for possible
keys, rows with a null in X are excluded since they never match), and test whether some group
has more than one row. Writes oracle.json and prints the comparison with audit.json."""
import json, os, sys
from collections import Counter, defaultdict
import duckdb, sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit import PK, _col


def check(con, root, sc, X, nulls_match):
    sel = sc.expression.copy()
    src = set(sc.selected_sources)
    for k in ('distinct', 'order', 'limit', 'having', 'group', 'qualify'):
        sel.set(k, None)
    w = sel.args.get('where')
    if w is not None:
        cs = list(w.this.flatten()) if isinstance(w.this, exp.And) else [w.this]
        keep = [c for c in cs if all(col.table in src for col in c.find_all(exp.Column)
                                     if col.find_ancestor(exp.Select) is c.find_ancestor(exp.Select))]
        sel.set('where', exp.Where(this=exp.and_(*keep)) if keep else None)
    cols = [exp.column(c, table=a, quoted=True) for a, c in sorted(X)]
    if not nulls_match:
        nn = exp.and_(*[exp.Not(this=exp.Is(this=c.copy(), expression=exp.Null())) for c in cols])
        sel.set('where', exp.Where(this=exp.and_(sel.args['where'].this, nn) if sel.args.get('where') else nn))
    sel.set('expressions', [exp.alias_(exp.Count(this=exp.Star()), 'c')])
    sel.set('group', exp.Group(expressions=cols))
    with_ = root.args.get('with')
    q = exp.select('max(c)').from_(exp.Subquery(this=sel, alias=exp.TableAlias(this=exp.to_identifier('s'))))
    if with_ is not None: q.set('with', with_.copy())
    m = con.execute(q.sql(dialect='duckdb')).fetchone()[0]
    return m is None or m <= 1


def main():
    work = sys.argv[1]
    con = duckdb.connect(os.path.join(work, 'tpcds_sf1.duckdb'), read_only=True)
    schema = {}
    for t, c, ty in con.execute("select table_name, column_name, data_type from duckdb_columns() "
                                "where schema_name='main' order by table_name, column_index").fetchall():
        if t in PK: schema.setdefault(t, {})[c] = ty
    A = json.load(open(os.path.join(HERE, 'audit.json')))
    Q = dict((n, q) for n, q in json.load(open(os.path.join(work, 'queries.json'))))
    byq = defaultdict(list)
    for x in A['constructs']: byq[x['query']].append(x)
    out = []
    for n, xs in sorted(byq.items()):
        root = qualify(sqlglot.parse_one(Q[n], read='duckdb'), schema=schema, dialect='duckdb')
        scopes = list(traverse_scope(root))
        for x in xs:
            if x['kind'] == 'SETOP': x['data_unique'] = x['trivial'] or None; out.append(x); continue
            X = {tuple(c.split('.', 1)) for c in x['cols']}
            try:
                x['data_unique'] = check(con, root, scopes[x['scope']], X, x['kind'] in ('DISTINCT', 'GROUPBY'))
            except Exception as e:
                x['data_unique'] = None; x['error'] = str(e)[:200]
            out.append(x)
    levels = A['levels']
    by = defaultdict(Counter)
    for x in out:
        by[x['kind']]['n'] += 1; by[x['kind']]['data'] += bool(x['data_unique'])
        by[x['kind']]['unknown'] += x['data_unique'] is None
        for lv in levels: by[x['kind']][lv] += x[lv]
    for k, v in sorted(by.items()):
        print(f"{k:16s} n={v['n']:3d} unique-on-data={v['data']:3d} (unknown {v['unknown']}) " + ' '.join(f'{lv}={v[lv]}' for lv in levels))
    for x in out:
        if x.get('data_unique') and not x[levels[-1]]:
            print('  unique on data, not licensed: q%d %s %s' % (x['query'], x['kind'], ','.join(x['cols'])))
    json.dump(out, open(os.path.join(HERE, 'oracle.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
