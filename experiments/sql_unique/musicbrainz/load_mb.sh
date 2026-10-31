#!/bin/bash
# Load the MusicBrainz core data dump into a fresh database with the real schema, for the
# condunique experiments. The schema scripts of musicbrainz-server (production branch) are applied
# as SQL in the order of admin/InitDb.pl, core schema only: Extensions, (collation), CreateTypes,
# CreateTables, data, CreatePrimaryKeys, CreateSearchConfiguration, CreateFunctions,
# CreateIndexes. Skipped: triggers, replication, constraints and foreign keys (not used by the
# prover), and the other schemas (cover art, statistics, ...). The server here is built without
# ICU, so the musicbrainz collation (ICU, deterministic) is created from "C": it changes ordering,
# not equality.
# DUMPDIR '-' builds the empty schema; TABLES (environment, space-separated) limits the data
# loaded to those tables. To load data into an existing schema, use load_tables.sh.
# Usage: load_mb.sh PSQL_BIN_DIR PORT SQLDIR DUMPDIR DBNAME
set -euo pipefail
BIN=$1; PORT=$2; SQL=$3; DUMP=$4; DB=$5
P="$BIN/psql -X -q -v ON_ERROR_STOP=1 -h localhost -p $PORT -U ck"
$P -d postgres -c "drop database if exists $DB" -c "create database $DB encoding 'UTF8' template template0 locale 'C'"
$P -d $DB -c "create schema musicbrainz" -c "alter database $DB set search_path = musicbrainz, public"
run() { echo "$(date +%T) $1"; PGOPTIONS='-c maintenance_work_mem=2GB -c max_parallel_maintenance_workers=4' $P -d $DB -f "$SQL/$1" > /dev/null; }
run Extensions.sql
$P -d $DB -c 'create collation musicbrainz.musicbrainz from "C"'
run CreateTypes.sql
run CreateTables.sql
echo "$(date +%T) data"
for f in $( [ "$DUMP" = - ] || ls "$DUMP"/mbdump/* ); do
  [ -z "${TABLES:-}" ] || [[ " $TABLES " == *" $(basename "$f") "* ]] || continue
  t=$(basename "$f")
  if $P -d $DB -Atc "select 1 from pg_tables where schemaname = 'musicbrainz' and tablename = '$t'" | grep -q 1; then
    $P -d $DB -c "\\copy musicbrainz.$t from '$f'"
  else
    echo "  skipped $t (no such table)"
  fi
done
run CreatePrimaryKeys.sql
run CreateSearchConfiguration.sql
run CreateFunctions.sql
run CreateIndexes.sql
echo "$(date +%T) analyze"; $P -d $DB -c analyze
$P -d $DB -Atc "select count(*) filter (where indisunique), count(*) filter (where indisunique and indpred is not null) from pg_index x join pg_class c on c.oid = x.indrelid join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'musicbrainz'"
[ "$DUMP" = - ] || cat "$DUMP/SCHEMA_SEQUENCE" "$DUMP/REPLICATION_SEQUENCE" "$DUMP/TIMESTAMP" 2>/dev/null || true
