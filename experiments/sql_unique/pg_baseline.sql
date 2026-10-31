-- What PostgreSQL's planner does with partial unique indexes: each uniqueness-based optimisation
-- is tried with an unconditional unique index (u_*) and with a partial one whose predicate is
-- exactly the query's predicate (p_*). Run: psql -X -f pg_baseline.sql > pg_baseline.out
\set ECHO queries
SELECT version();
DROP SCHEMA IF EXISTS pgb CASCADE; CREATE SCHEMA pgb; SET search_path = pgb;
SET max_parallel_workers_per_gather = 0;

-- t: k unique among current rows (d IS NULL); several versions per k otherwise
CREATE TABLE u_t (id int PRIMARY KEY, k int NOT NULL, d date, x int);
CREATE TABLE p_t (id int PRIMARY KEY, k int NOT NULL, d date, x int);
INSERT INTO u_t SELECT i, i, NULL, i % 10 FROM generate_series(1, 20000) i;
INSERT INTO p_t SELECT i, (i - 1) % 10000 + 1, CASE WHEN i > 10000 THEN NULL ELSE date '2020-01-01' END, i % 10
  FROM generate_series(1, 20000) i;
CREATE UNIQUE INDEX ON u_t (k);
CREATE UNIQUE INDEX ON p_t (k) WHERE d IS NULL;
CREATE TABLE s (k int, y int);
INSERT INTO s SELECT i % 12000, i FROM generate_series(1, 50000) i;
ANALYZE;

-- 1. left-join removal (join_is_removable)
EXPLAIN (COSTS OFF) SELECT s.* FROM s LEFT JOIN u_t b ON s.k = b.k AND b.d IS NULL;
EXPLAIN (COSTS OFF) SELECT s.* FROM s LEFT JOIN (SELECT * FROM p_t WHERE d IS NULL) b ON s.k = b.k;
EXPLAIN (COSTS OFF) SELECT s.* FROM s LEFT JOIN p_t b ON s.k = b.k AND b.d IS NULL;

-- 2. semi-join to inner join (reduce_unique_semijoins) and inner-unique joins (innerrel_is_unique)
EXPLAIN (COSTS OFF, VERBOSE) SELECT s.y FROM s WHERE s.k IN (SELECT k FROM u_t WHERE d IS NULL);
EXPLAIN (COSTS OFF, VERBOSE) SELECT s.y FROM s WHERE s.k IN (SELECT k FROM p_t WHERE d IS NULL);
EXPLAIN (COSTS OFF, VERBOSE) SELECT s.y, b.x FROM s JOIN u_t b ON s.k = b.k WHERE b.d IS NULL;
EXPLAIN (COSTS OFF, VERBOSE) SELECT s.y, b.x FROM s JOIN p_t b ON s.k = b.k WHERE b.d IS NULL;

-- 3. GROUP BY column removal (remove_useless_groupby_columns)
EXPLAIN (COSTS OFF, VERBOSE) SELECT k, x, count(*) FROM u_t WHERE d IS NULL GROUP BY k, x;
EXPLAIN (COSTS OFF, VERBOSE) SELECT k, x, count(*) FROM p_t WHERE d IS NULL GROUP BY k, x;

-- 4. DISTINCT over a key: no removal even with an unconditional unique index
EXPLAIN (COSTS OFF) SELECT DISTINCT k FROM u_t WHERE d IS NULL;
EXPLAIN (COSTS OFF) SELECT DISTINCT k FROM p_t WHERE d IS NULL;
-- ... but DISTINCT on top of a subquery that is itself DISTINCT is recognised (query_is_distinct_for)
EXPLAIN (COSTS OFF) SELECT s.y FROM s WHERE s.k IN (SELECT DISTINCT k FROM p_t WHERE d IS NULL);

-- 5. self-join elimination (PostgreSQL 18)
SHOW enable_self_join_elimination;
EXPLAIN (COSTS OFF) SELECT a.x, b.id FROM u_t a JOIN u_t b ON a.k = b.k;
EXPLAIN (COSTS OFF) SELECT a.x, b.id FROM p_t a JOIN p_t b ON a.k = b.k WHERE a.d IS NULL AND b.d IS NULL;

-- 6. estimates: partial unique indexes still feed the number-of-groups estimate when predOK
EXPLAIN SELECT k, count(*) FROM u_t WHERE d IS NULL GROUP BY k;
EXPLAIN SELECT k, count(*) FROM p_t WHERE d IS NULL GROUP BY k;

DROP SCHEMA pgb CASCADE;
