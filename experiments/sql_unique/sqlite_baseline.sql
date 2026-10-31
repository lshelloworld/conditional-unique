-- What SQLite's planner does with partial unique indexes: as pg_baseline.sql, an unconditional
-- unique index (u_*) against a partial one whose predicate equals the query's (p_*).
-- Run: sqlite3 :memory: < sqlite_baseline.sql > sqlite_baseline.out
.echo on
SELECT sqlite_version();
CREATE TABLE u_t (id INTEGER PRIMARY KEY, k INT NOT NULL, d TEXT, x INT);
CREATE TABLE p_t (id INTEGER PRIMARY KEY, k INT NOT NULL, d TEXT, x INT);
CREATE UNIQUE INDEX u_k ON u_t (k);
CREATE UNIQUE INDEX p_k ON p_t (k) WHERE d IS NULL;
CREATE TABLE s (k INT, y INT);
WITH RECURSIVE g(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM g WHERE i < 20000)
INSERT INTO u_t SELECT i, i, NULL, i % 10 FROM g;
WITH RECURSIVE g(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM g WHERE i < 20000)
INSERT INTO p_t SELECT i, (i - 1) % 10000 + 1, CASE WHEN i > 10000 THEN NULL ELSE '2020-01-01' END, i % 10 FROM g;
WITH RECURSIVE g(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM g WHERE i < 50000)
INSERT INTO s SELECT i % 12000, i FROM g;
ANALYZE;

-- 1. DISTINCT removal (whereDistinctRedundant): no "USE TEMP B-TREE FOR DISTINCT" when redundant
EXPLAIN QUERY PLAN SELECT DISTINCT k FROM u_t WHERE d IS NULL;
EXPLAIN QUERY PLAN SELECT DISTINCT k FROM p_t WHERE d IS NULL;
EXPLAIN QUERY PLAN SELECT DISTINCT k, x FROM u_t WHERE d IS NULL;
EXPLAIN QUERY PLAN SELECT DISTINCT k, x FROM p_t WHERE d IS NULL;

-- 2. LEFT JOIN omission (omit-noop-join): the right table disappears from the plan
EXPLAIN QUERY PLAN SELECT DISTINCT s.k, s.y FROM s LEFT JOIN u_t b ON s.k = b.k AND b.d IS NULL;
EXPLAIN QUERY PLAN SELECT s.k, s.y FROM s LEFT JOIN u_t b ON s.k = b.k AND b.d IS NULL;
EXPLAIN QUERY PLAN SELECT s.k, s.y FROM s LEFT JOIN p_t b ON s.k = b.k AND b.d IS NULL;

-- 3. GROUP BY over a key (no aggregation removal expected for either)
EXPLAIN QUERY PLAN SELECT k, count(*) FROM u_t WHERE d IS NULL GROUP BY k;
EXPLAIN QUERY PLAN SELECT k, count(*) FROM p_t WHERE d IS NULL GROUP BY k;

-- 4. the partial index is used as an access path when the query implies its predicate
EXPLAIN QUERY PLAN SELECT x FROM p_t WHERE k = 5 AND d IS NULL;
EXPLAIN QUERY PLAN SELECT x FROM p_t WHERE k = 5;

-- 5. LEFT JOIN omission needs a single query term that matches the index predicate syntactically
CREATE TABLE q_t (id INTEGER PRIMARY KEY, k INT NOT NULL, st INT, x INT);
CREATE UNIQUE INDEX q_k ON q_t (k) WHERE st IN (0, 1);
WITH RECURSIVE g(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM g WHERE i < 20000)
INSERT INTO q_t SELECT i, (i - 1) % 10000 + 1, CASE WHEN i > 10000 THEN 0 ELSE 2 END, i % 10 FROM g;
ANALYZE;
-- implied (st = 0 implies st IN (0, 1)) but not matched: join kept
EXPLAIN QUERY PLAN SELECT s.k, s.y FROM s LEFT JOIN q_t b ON s.k = b.k AND b.st = 0;
-- syntactically equal predicate: join omitted
EXPLAIN QUERY PLAN SELECT s.k, s.y FROM s LEFT JOIN q_t b ON s.k = b.k AND b.st IN (0, 1);
-- scope narrowed by an extra term: still omitted
EXPLAIN QUERY PLAN SELECT s.k, s.y FROM s LEFT JOIN p_t b ON s.k = b.k AND b.d IS NULL AND b.x > 3;
-- the same predicate written differently (d IS NULL AND d IS NULL is fine; NOT (d IS NOT NULL) is not)
EXPLAIN QUERY PLAN SELECT s.k, s.y FROM s LEFT JOIN p_t b ON s.k = b.k AND NOT (b.d IS NOT NULL);
-- single-table DISTINCT whose scope is implied: not removed (ordered scan of the index instead)
EXPLAIN QUERY PLAN SELECT DISTINCT k FROM q_t WHERE st = 0;
