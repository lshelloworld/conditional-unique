"""Rebuild the SDSS DR18 catalog schema (BestDR18 on SkyServer) in PostgreSQL from its metadata.

Input: JSON exports of INFORMATION_SCHEMA.COLUMNS, TABLES, TABLE_CONSTRAINTS/KEY_COLUMN_USAGE,
ROUTINES, ROUTINE_COLUMNS, PARAMETERS and the view definitions (sys.sql_modules), fetched through
the public SkyServer SQL search service (see README). Output, applied to DSN:
  tables     every base table, lower-case names, types mapped (bit and tinyint -> smallint,
             float -> double precision, character types -> text, binary -> bytea), NOT NULL as
             declared, PRIMARY KEY and UNIQUE as declared;
  views      the 60 views, translated from T-SQL by sqlglot (PhotoPrimary = PhotoObjAll WHERE
             mode = 1, SpecObj = SpecObjAll WHERE sciencePrimary = 1, ...); views that do not
             translate are skipped;
  functions  stand-ins in schema dbo with the declared signatures, so that queries calling them
             plan: table-valued functions return no rows (plpgsql, never inlined, ROWS 100),
             scalar functions return NULL. They are for planning only.
No data. Writes the DDL to sdss_schema.sql and prints what was skipped.
Usage: python sdss_schema.py METADATA_DIR DSN"""
import json, os, re, sys
import psycopg, sqlglot
HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = {'real': 'real', 'float': 'double precision', 'int': 'integer', 'bigint': 'bigint',
         'smallint': 'smallint', 'tinyint': 'smallint', 'bit': 'smallint', 'numeric': 'numeric',
         'decimal': 'numeric', 'money': 'numeric', 'varchar': 'text', 'char': 'text', 'nvarchar': 'text',
         'nchar': 'text', 'text': 'text', 'ntext': 'text', 'sysname': 'text', 'binary': 'bytea',
         'varbinary': 'bytea', 'image': 'bytea', 'datetime': 'timestamp', 'datetime2': 'timestamp',
         'smalldatetime': 'timestamp', 'date': 'date', 'time': 'time', 'uniqueidentifier': 'uuid',
         'sql_variant': 'text', 'xml': 'text'}


def rows(d, f):
    return json.load(open(os.path.join(d, f + '.json')))[0]['Rows']


def q(n):
    return '"' + n.lower().replace('"', '') + '"'


def main():
    d, dsn = sys.argv[1], sys.argv[2]
    base = {r['table_name'].lower() for r in rows(d, 'tables') if r['table_type'] == 'BASE TABLE'}
    cols = {}
    for r in rows(d, 'columns'):
        t = r['table_name'].lower()
        if t in base: cols.setdefault(t, []).append(r)
    keys = {}
    for r in rows(d, 'keys'):
        keys.setdefault((r['table_name'].lower(), r['constraint_type']), []).append(r['column_name'].lower())
    ddl, skipped = ['create schema if not exists dbo;'], []
    for t in sorted(cols):
        cs = [f"{q(c['column_name']) if c['column_name'].lower() not in ('cmin', 'cmax', 'xmin', 'xmax') else q(c['column_name'] + '_')} {TYPES.get(c['data_type'], 'text')}" + (' not null' if c['is_nullable'] == 'NO' else '')
              for c in sorted(cols[t], key=lambda c: c['ordinal_position'])]
        for kind in ('PRIMARY KEY', 'UNIQUE'):
            if (t, kind) in keys:
                cs.append(f"{kind.lower()} ({', '.join(q(c) for c in keys[(t, kind)])})")
        ddl.append(f'create table {q(t)} (\n  ' + ',\n  '.join(cs) + '\n);')
    views = []
    for r in rows(d, 'views'):
        body = re.sub(r'--[^\n]*', ' ', r['definition'])
        body = re.sub(r'\bwith\s*\(\s*nolock\s*\)', ' ', body, flags=re.I)
        try:
            v = sqlglot.transpile(body, read='tsql', write='postgres')[0]
            v = re.sub(r'^CREATE VIEW\s+\S+', f"create view {q(r['name'])}", v, flags=re.I)
            v = re.sub(r'"([^"]+)"', lambda m: '"' + m.group(1).lower() + '"', v)
            views.append((r['name'].lower(), v + ';'))
        except Exception as ex:
            skipped.append(('view', r['name'], type(ex).__name__))
    params = {}
    for r in rows(d, 'parameters'):
        params.setdefault(r['specific_name'].lower(), []).append(TYPES.get(r['data_type'], 'text'))
    rcols = {}
    for r in rows(d, 'routine_columns'):
        rcols.setdefault(r['table_name'].lower(), []).append(r)
    for r in rows(d, 'routines'):
        n = r['routine_name'].lower()
        args = ', '.join(f'p{i} {t}' for i, t in enumerate(params.get(n, []), 1))
        if n in rcols:
            out = ', '.join(f"{q(c['column_name'])} {TYPES.get(c['data_type'], 'text')}"
                            for c in sorted(rcols[n], key=lambda c: c['ordinal_position']))
            ddl.append(f'create function dbo.{q(n)}({args}) returns table ({out}) language plpgsql rows 100 '
                       f'as $$ begin return; end $$;')
        elif r['data_type'] and r['data_type'].upper() != 'TABLE':
            ddl.append(f"create function dbo.{q(n)}({args}) returns {TYPES.get(r['data_type'], 'text')} "
                       f'language plpgsql as $$ begin return null; end $$;')
        else:
            skipped.append(('function', n, 'no signature'))
    con = psycopg.connect(dsn, autocommit=True)
    cur = con.cursor()
    for s in ddl:
        try: cur.execute(s)
        except psycopg.Error as ex: skipped.append(('ddl', s[:60], str(ex).splitlines()[0][:80]))
    pending = views
    while pending:                                   # views may read views
        left = []
        for n, v in pending:
            try: cur.execute(v); ddl.append(v)
            except psycopg.Error as ex: left.append((n, v, str(ex).splitlines()[0][:100]))
        if len(left) == len(pending):
            skipped += [('view', n, e) for n, v, e in left]; break
        pending = [(n, v) for n, v, e in left]
    open(os.path.join(HERE, 'sdss_schema.sql'), 'w').write('\n\n'.join(ddl) + '\n')
    print(len(cols), 'tables,', len(views), 'views translated,', len(skipped), 'skipped')
    for s in skipped: print('  skipped', s)


if __name__ == '__main__':
    main()
