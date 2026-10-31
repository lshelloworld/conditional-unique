"""Probe of the patched CockroachDB: each query with optimizer_use_conditional_unique off and on.
Prints whether the join, DISTINCT or grouping is gone, and compares the results as multisets.
Tables of setup.sql, plus cases for the two pitfalls, CHECK constraints and keys through joins.
Usage: python probe_cu.py DSN"""
import sys
from collections import Counter
import psycopg

SETUP = """
set experimental_enable_unique_without_index_constraints = true;
drop table if exists cu_u, cu_e, cu_n, cu_m, cu_s;
create table cu_u (id int primary key, email text not null, deleted_at int);
create unique index on cu_u (email) where deleted_at is null;
insert into cu_u values (1, 'a', null), (2, 'a', 5), (3, 'b', null);
create table cu_e (uid int, addr text, prim bool, unique (uid, prim) where prim);
insert into cu_e values (1, 'a', true), (1, 'a2', false), (3, 'b', true);
create table cu_n (id int primary key, k int, unique (k) where k is not null);
insert into cu_n values (1, null), (2, null), (3, 7);
create table cu_m (id int primary key, ent int not null, locale text, prim bool not null,
  check ((locale is null and prim is false) or locale is not null));
create unique index on cu_m (ent, locale) where prim and locale is not null;
insert into cu_m values (1, 1, 'en', true), (2, 1, 'de', false), (3, 1, null, false), (4, 2, 'en', true);
create table cu_s (id int primary key, k int not null, st int, d int);
create unique index on cu_s (k) where st = 0;
create unique index on cu_s (k) where st = 1;
insert into cu_s values (1, 1, 0, null), (2, 1, 1, null), (3, 2, 0, null);
"""

QUERIES = [
    ('left join, predicate = index predicate', 'select a.id from a left join bf b on b.k = a.bk and b.d is null', 'join'),
    ('left join, subquery form', 'select a.id from a left join (select * from bf where d is null) b on b.k = a.bk', 'join'),
    ('DISTINCT, k NOT NULL', 'select distinct k from bf where d is null', 'distinct'),
    ('GROUP BY', 'select k, x from bf where d is null group by k, x', 'distinct'),
    ('semi-join', 'select a.id from a where a.bk in (select k from bf where d is null)', 'none'),
    ('implied predicate (st = 0 vs IN (0, 1))', 'select a.id from a left join bfs b on b.k = a.bk and b.st = 0', 'join'),
    ('index excluding NULL keys: left join', 'select a.id from a left join bn b on b.k = a.bk', 'join'),
    ('index excluding NULL keys: DISTINCT', 'select distinct k from bn where k is not null', 'distinct'),
    ('bug #17975 shape: predicate only via join clause (must keep)',
     'select a.id from a left join bf b on b.k = a.bk and b.d = a.v', 'join'),
    ('union of two scopes (must keep)', 'select a.id from a left join cu_s b on b.k = a.bk and b.st in (0, 1)', 'join'),
    ('one scope of two', 'select a.id from a left join cu_s b on b.k = a.bk and b.st = 1', 'join'),
    ('nulls: DISTINCT over nullable key (must keep)', 'select distinct k from cu_n', 'distinct'),
    ('nulls: left join over nullable key', 'select a.id from a left join cu_n b on b.k = a.bk', 'join'),
    ('running example: DISTINCT through join',
     'select distinct u.email, e.addr from cu_u u join cu_e e on e.uid = u.id and e.prim where u.deleted_at is null', 'distinct'),
    ('running example without e.prim (must keep)',
     'select distinct u.email, e.addr from cu_u u join cu_e e on e.uid = u.id where u.deleted_at is null', 'distinct'),
    ('CHECK gives the primary alias a locale', 'select distinct ent, locale from cu_m where prim', 'distinct'),
    ('without the CHECK reasoning: locale written out', 'select distinct ent, locale from cu_m where prim and locale is not null', 'distinct'),
]


def plan(cur, sql, on):
    cur.execute(f"set optimizer_use_conditional_unique = {'on' if on else 'off'}")
    cur.execute('explain (opt) ' + sql)
    return [r[0] for r in cur.fetchall()]


def gone(p, what):
    s = '\n'.join(p)
    if what == 'join': return 'join' not in s
    if what == 'distinct': return 'distinct-on' not in s and 'group-by' not in s
    return None


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True, prepare_threshold=None)
    cur = con.cursor()
    for stmt in SETUP.split(';'):
        if stmt.strip(): cur.execute(stmt)
    for title, sql, what in QUERIES:
        off, on = plan(cur, sql, False), plan(cur, sql, True)
        res = {}
        for flag in (False, True):
            cur.execute(f"set optimizer_use_conditional_unique = {'on' if flag else 'off'}")
            cur.execute(sql); res[flag] = Counter(map(tuple, cur.fetchall()))
        print(f"--- {title}\n    {sql}\n    off: {'gone' if gone(off, what) else 'kept'}  on: {'gone' if gone(on, what) else 'kept'}"
              f"  plan changed: {off != on}  same result: {res[False] == res[True]}")
        if what == 'none' or off != on:
            print('    on plan: ' + ' | '.join(l.strip() for l in on[:8]))


if __name__ == '__main__':
    main()
