#!/bin/bash
# Uniqueness-based rewrites in SQL Server with an unconditional (bu) and a filtered (bf) unique
# index on k whose predicate equals the query predicate, an index that only excludes NULL keys
# (bn) and a predicate implied by the query (bfs). Prints the operators of SHOWPLAN_TEXT.
# Usage: probe.sh CONTAINER   (password in .sa_password next to this script)
CT=$1; HERE=$(cd "$(dirname "$0")" && pwd); PW=$(cat "$HERE/.sa_password")
SQ="docker exec -i $CT /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U sa -P $PW -b"
$SQ -Q "SELECT @@VERSION" -h -1 | head -1
$SQ < "$HERE/setup.sql" | grep -E "^Msg" ; true
run() { echo "--- $1"; printf 'USE p;\nGO\nSET SHOWPLAN_TEXT ON;\nGO\n%s;\nGO\n' "$1" | $SQ -h -1 -W | grep '|--' ; }
for T in bu bf; do
  run "SELECT a.id FROM a LEFT JOIN (SELECT * FROM $T WHERE d IS NULL) b ON b.k = a.bk"
  run "SELECT a.id FROM a LEFT JOIN $T b ON b.k = a.bk AND b.d IS NULL"
  run "SELECT a.id FROM a WHERE a.bk IN (SELECT k FROM $T WHERE d IS NULL)"
  run "SELECT DISTINCT k FROM $T WHERE d IS NULL"
  run "SELECT k, x FROM $T WHERE d IS NULL GROUP BY k, x"
done
run "SELECT a.id FROM a LEFT JOIN bn b ON b.k = a.bk"
run "SELECT DISTINCT k FROM bn WHERE k IS NOT NULL"
run "SELECT a.id FROM a LEFT JOIN bfs b ON b.k = a.bk AND b.st = 0"
