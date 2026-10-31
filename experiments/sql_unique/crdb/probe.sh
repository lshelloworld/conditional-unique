#!/bin/bash
# Uniqueness-based rewrites in CockroachDB with an unconditional (bu) and a partial (bf) unique
# index on k whose predicate equals the query predicate, plus a partial UNIQUE WITHOUT INDEX
# constraint (bc), an index that only excludes NULL keys (bn) and a predicate implied by the query
# (bfs). Prints EXPLAIN (OPT). Usage: probe.sh COCKROACH_BINARY HOST:PORT
C=$1; H=$2; HERE=$(cd "$(dirname "$0")" && pwd)
$C sql --insecure --host=$H -f "$HERE/setup.sql" > /dev/null 2>&1
run() { echo "--- $1"; $C sql --insecure --host=$H -d p --format=raw -e "set experimental_enable_unique_without_index_constraints = true; explain (opt) $1" 2>&1 | grep -v '^#\|^SET'; }
$C version | head -1
for T in bu bf; do
  run "select a.id from a left join (select * from $T where d is null) b on b.k = a.bk"
  run "select a.id from a left join $T b on b.k = a.bk and b.d is null"
  run "select a.id from a where a.bk in (select k from $T where d is null)"
  run "select distinct k from $T where d is null"
  run "select k, x from $T where d is null group by k, x"
done
run "select a.id from a left join bc b on b.k = a.bk and b.d is null"
run "select distinct k from bc where d is null"
run "select a.id from a left join bn b on b.k = a.bk"
run "select distinct k from bn where k is not null"
run "select a.id from a left join bfs b on b.k = a.bk and b.st = 0"
