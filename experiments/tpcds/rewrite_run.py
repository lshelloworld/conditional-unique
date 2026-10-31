"""Apply the rewrites that audit.py licenses to the TPC-DS queries and time them in PostgreSQL.

The licensed rewrite is IN-subquery to join: a conjunct  x IN (SELECT y FROM ... )  of a WHERE
clause becomes  x = d.y  with the subquery added to the FROM list as derived table d; this
returns the same multiset when the subquery's input has a possible key on y (every x then has at
most one partner, and nulls never match). Queries are transpiled from DuckDB's dialect to
PostgreSQL's with sqlglot; original and rewrite are run (two warm-ups, median of five
EXPLAIN ANALYZE runs) and their results compared as multisets. Writes rewrite_run.json.
Usage: python rewrite_run.py WORKDIR DSN LEVEL"""
import json, os, statistics, sys
from collections import Counter
import duckdb, psycopg, sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit import PK, _col


def rewrite(q, schema, licensed_scopes):
    e = qualify(sqlglot.parse_one(q, read='duckdb'), schema=schema, dialect='duckdb')
    scopes = list(traverse_scope(e))
    done = 0
    for n, si in enumerate(sorted(licensed_scopes, reverse=True)):
        sub = scopes[si].expression
        node = sub.parent
        while isinstance(node, (exp.Paren, exp.Subquery)): node = node.parent
        if not isinstance(node, exp.In): continue
        where = node.parent
        while isinstance(where, (exp.Paren, exp.And)): where = where.parent
        if not isinstance(where, exp.Where): continue                     # only top-level conjuncts
        outer = where.parent
        alias = f'ckin_{n}'; y = f'{alias}_y'                         # fresh names: no clash with the query
        d = sub.copy()
        d.set('expressions', [exp.alias_(d.expressions[0].unalias().copy(), y, quoted=True)])
        node.replace(exp.EQ(this=node.this.copy(), expression=exp.column(y, table=alias, quoted=True)))
        outer.append('joins', exp.Join(this=exp.Subquery(this=d, alias=exp.TableAlias(this=exp.to_identifier(alias)))))
        done += 1
    return e, done


def timed(cur, sql, reps=5):
    for _ in range(2): cur.execute(sql); cur.fetchall()
    ts = []
    for _ in range(reps):
        cur.execute('EXPLAIN (ANALYZE, FORMAT JSON) ' + sql); ts.append(cur.fetchone()[0][0]['Execution Time'])
    return statistics.median(ts)


def main():
    work, dsn, level = sys.argv[1], sys.argv[2], sys.argv[3]
    con = duckdb.connect(os.path.join(work, 'tpcds_sf1.duckdb'), read_only=True)
    schema = {}
    for t, c, ty in con.execute("select table_name, column_name, data_type from duckdb_columns() "
                                "where schema_name='main' order by table_name, column_index").fetchall():
        if t in PK: schema.setdefault(t, {})[c] = ty
    A = json.load(open(os.path.join(HERE, 'audit.json')))['constructs']
    Q = dict((n, q) for n, q in json.load(open(os.path.join(work, 'queries.json'))))
    lic = {}
    for x in A:
        if x['kind'] == 'SEMIJOIN-IN' and x.get(level): lic.setdefault(x['query'], set()).add(x['scope'])
    pg = psycopg.connect(dsn, autocommit=True)
    out = []
    with pg.cursor() as cur:
        cur.execute('SET max_parallel_workers_per_gather = 0'); cur.execute("SET statement_timeout = '600s'")
        for n, scopes in sorted(lic.items()):
            orig = qualify(sqlglot.parse_one(Q[n], read='duckdb'), schema=schema, dialect='duckdb').sql(dialect='postgres')
            new, k = rewrite(Q[n], schema, scopes)
            new = new.sql(dialect='postgres')
            cur.execute(orig); a = Counter(map(tuple, cur.fetchall()))
            cur.execute(new); b = Counter(map(tuple, cur.fetchall()))
            r = dict(query=n, licensed=len(scopes), rewritten=k, same_result=a == b, rows=sum(a.values()),
                     orig_ms=timed(cur, orig), rew_ms=timed(cur, new), orig_sql=orig, rew_sql=new)
            out.append(r)
            print(f"q{n}: {k}/{len(scopes)} rewritten, same result {r['same_result']} ({r['rows']} rows), "
                  f"{r['orig_ms']:.1f} -> {r['rew_ms']:.1f} ms", flush=True)
    json.dump(out, open(os.path.join(HERE, f'rewrite_run_{level}.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
