#!/bin/bash
# Load selected tables of an extracted MusicBrainz dump into the schema built by load_mb.sh
# (indexes in place, so all unique indexes are checked on load), then ANALYZE them.
# Usage: load_tables.sh PSQL_BIN_DIR PORT DUMPDIR DBNAME TABLE...
set -euo pipefail
BIN=$1; PORT=$2; DUMP=$3; DB=$4; shift 4
P="$BIN/psql -X -q -v ON_ERROR_STOP=1 -h localhost -p $PORT -U ck -d $DB"
for t in "$@"; do
  echo "$(date +%T) $t"
  $P -c "truncate musicbrainz.$t" -c "\\copy musicbrainz.$t from '$DUMP/mbdump/$t'" -c "analyze musicbrainz.$t"
done
$P -Atc "select relname, n_live_tup from pg_stat_user_tables where schemaname = 'musicbrainz' and n_live_tup > 0 order by 1"
