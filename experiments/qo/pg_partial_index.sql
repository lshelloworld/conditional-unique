-- Does PostgreSQL use a partial (filtered) unique index to remove a join or a DISTINCT when
-- the query predicate implies the index predicate? Run with psql on a scratch database.
\set ON_ERROR_STOP on
DROP TABLE IF EXISTS t;
CREATE TABLE t (id int PRIMARY KEY, k int, s int, v int);
INSERT INTO t SELECT i, i / 2, i % 2, i FROM generate_series(1, 100000) i;
-- within s = 1, k is unique (each k occurs once with s = 0 and once with s = 1)
CREATE UNIQUE INDEX t_k_s1 ON t (k) WHERE s = 1;
ANALYZE t;
\echo '== 1 left join, predicate in ON (partial unique index)'
EXPLAIN (COSTS OFF) SELECT a.id FROM t a LEFT JOIN t b ON b.k = a.k AND b.s = 1;
\echo '== 2 left join, predicate in a subquery (partial unique index)'
EXPLAIN (COSTS OFF) SELECT a.id FROM t a LEFT JOIN (SELECT * FROM t WHERE s = 1) b ON b.k = a.k;
\echo '== 3 DISTINCT over the key within the scope (partial unique index)'
EXPLAIN (COSTS OFF) SELECT DISTINCT k FROM t WHERE s = 1;
\echo '== 4 inner self-join on the key within the scope (self-join elimination, PG 18)'
SHOW enable_self_join_elimination;
EXPLAIN (COSTS OFF) SELECT a.id, b.v FROM t a JOIN t b ON b.k = a.k WHERE a.s = 1 AND b.s = 1;
\echo '== control: the same queries with a full unique index'
DROP TABLE IF EXISTS u;
CREATE TABLE u (id int PRIMARY KEY, k int, s int, v int);
INSERT INTO u SELECT i, i, 1, i FROM generate_series(1, 100000) i;
CREATE UNIQUE INDEX u_k ON u (k);
ANALYZE u;
\echo '== 5 left join (full unique index)'
EXPLAIN (COSTS OFF) SELECT a.id FROM u a LEFT JOIN u b ON b.k = a.k AND b.s = 1;
\echo '== 6 left join, predicate in a subquery (full unique index)'
EXPLAIN (COSTS OFF) SELECT a.id FROM u a LEFT JOIN (SELECT * FROM u WHERE s = 1) b ON b.k = a.k;
\echo '== 7 DISTINCT (full unique index)'
EXPLAIN (COSTS OFF) SELECT DISTINCT k FROM u WHERE s = 1;
\echo '== 8 inner self-join (full unique index)'
EXPLAIN (COSTS OFF) SELECT a.id, b.v FROM u a JOIN u b ON b.k = a.k WHERE a.s = 1 AND b.s = 1;
DROP TABLE t; DROP TABLE u;
