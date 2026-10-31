"""Execution time of the rewrites the condunique patch enables, on soft-delete and tenant-scoped
schemas of the kind found in the application study (Section II-A).

  users(id, email NOT NULL, name, deleted_at)   1M rows, 30% soft-deleted, deleted rows reuse
                                                e-mails of live ones;
                                                UNIQUE (email) WHERE deleted_at IS NULL
  orders(id, email, amount)                     5M rows
  items(id, tenant, name, active)               1M rows, 50 tenants, inactive rows repeat names;
                                                UNIQUE (tenant, name) WHERE active
  refs(id, name)                                2M rows
Queries: left-join removal (soft delete; tenant fixed by the query), semi-join to join, GROUP BY
reduction, DISTINCT removal (U= from a nulls-distinct index on a NOT NULL key). Per query: plan and execution time with enable_conditional_unique off and on (two
warm-ups, median of five), results compared as multisets. Writes speedup.json.
Usage: python speedup.py DSN"""
import json, os, statistics, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))

SETUP = """
drop schema if exists sp cascade; create schema sp; set search_path = sp;
create table users (id int primary key, email text not null, name text, deleted_at timestamptz);
insert into users select i, 'user' || case when i <= 700000 then i else i % 700000 + 1 end || '@x.org',
  'name' || i, case when i > 700000 then now() - (i % 1000) * interval '1 day' end
  from generate_series(1, 1000000) i;
create unique index users_email_live on users (email) where deleted_at is null;
create table orders (id int primary key, email text, amount int);
insert into orders select i, 'user' || (i % 800000 + 1) || '@x.org', i % 100 from generate_series(1, 5000000) i;
create table items (id int primary key, tenant int not null, name text, active bool not null);
insert into items select i, i % 50, 'item' || (i / 50) % 10000, (i / 500000) = 0 from generate_series(0, 999999) i;
create unique index items_tn on items (tenant, name) where active;
create table refs (id int primary key, name text);
insert into refs select i, 'item' || i % 12000 from generate_series(1, 2000000) i;
vacuum analyze;
"""

QUERIES = {
    'left join, soft delete': "select o.id, o.amount from sp.orders o left join sp.users u on u.email = o.email and u.deleted_at is null",
    'left join, tenant scope': "select r.* from sp.refs r left join sp.items i on i.name = r.name and i.tenant = 7 and i.active",
    'semi-join, soft delete': "select o.id from sp.orders o where o.email in (select email from sp.users where deleted_at is null) and o.amount < 5",
    'GROUP BY, soft delete': "select u.email, u.name, u.id, count(*) from sp.users u join sp.orders o on o.email = u.email where u.deleted_at is null group by u.email, u.name, u.id",
    'DISTINCT, soft delete': "select distinct email, name from sp.users where deleted_at is null",
}


def run(cur, sql, on):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    for _ in range(2): cur.execute(sql); cur.fetchall()
    ts = []
    for _ in range(5):
        cur.execute('explain (analyze, format json) ' + sql); ts.append(cur.fetchone()[0][0]['Execution Time'])
    cur.execute('explain (costs off) ' + sql)
    p = '\n'.join(r[0] if isinstance(r[0], str) else r[0].decode() for r in cur.fetchall())
    cur.execute(sql)
    return statistics.median(ts), p, Counter(map(tuple, cur.fetchall()))


def main():
    pg = psycopg.connect(sys.argv[1], autocommit=True)
    out = []
    with pg.cursor() as cur:
        cur.execute('set max_parallel_workers_per_gather = 0'); cur.execute("set work_mem = '256MB'")
        for s in SETUP.split(';\n'):
            if s.strip(): cur.execute(s)
        for name, sql in QUERIES.items():
            off, poff, roff = run(cur, sql, False)
            on, pon, ron = run(cur, sql, True)
            r = dict(query=name, sql=sql, off_ms=off, on_ms=on, speedup=off / on, same_result=roff == ron,
                     rows=sum(roff.values()), plan_off=poff, plan_on=pon)
            out.append(r)
            print(f"{name}: off {off:.0f} ms, on {on:.0f} ms, {off / on:.2f}x, same result {r['same_result']}, "
                  f"{r['rows']} rows", flush=True)
    json.dump(out, open(os.path.join(HERE, 'speedup.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
