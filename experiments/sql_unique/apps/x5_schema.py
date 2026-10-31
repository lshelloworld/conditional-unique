"""X5: Rails db/schema.rb -> PostgreSQL DDL (tables, NOT NULL, primary keys, enums, btree
indexes; unique and partial indexes exactly as declared). Defaults, foreign keys, check
constraints and non-btree indexes are left out: the experiment only needs the columns, the
nullability and the indexes the planner sees. Usage: python x5_schema.py schema.rb > out.sql"""
import re, sys

TYPES = {'string': 'varchar', 'text': 'text', 'integer': 'integer', 'bigint': 'bigint', 'boolean': 'boolean',
         'datetime': 'timestamp', 'timestamp': 'timestamp', 'timestamptz': 'timestamptz', 'date': 'date',
         'time': 'time', 'decimal': 'numeric', 'float': 'double precision', 'json': 'json', 'jsonb': 'jsonb',
         'uuid': 'uuid', 'inet': 'inet', 'cidr': 'cidr', 'citext': 'citext', 'binary': 'bytea', 'hstore': 'hstore',
         'ltree': 'ltree', 'interval': 'interval', 'xml': 'xml', 'tsvector': 'tsvector', 'daterange': 'daterange',
         'int4range': 'int4range', 'tstzrange': 'tstzrange', 'macaddr': 'macaddr', 'money': 'money', 'point': 'point',
         'serial': 'serial', 'bigserial': 'bigserial', 'vector': 'text', 'bit': 'bit'}


def q(x):
    return '"' + x + '"'


def convert(src):
    out, enums, exts = [], [], set()
    lines = src.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'\s*enable_extension "(?:pg_catalog\.)?([\w-]+)"', line)
        if m and m.group(1) not in ('plpgsql', 'vector', 'pg_stat_statements', 'pgcrypto'): exts.add(m.group(1))
        m = re.match(r'\s*create_enum "([^"]+)", \[(.*)\]', line)
        if m:
            vals = re.findall(r'"([^"]*)"', m.group(2))
            enums.append(f'CREATE TYPE {q(m.group(1))} AS ENUM (' + ', '.join("'%s'" % v.replace("'", "''") for v in vals) + ');')
        m = re.match(r'\s*create_table "([^"]+)"(.*) do \|t\|', line)
        if not m: i += 1; continue
        table, opts = m.group(1), m.group(2)
        cols, idx = [], []
        pk = None
        idm = re.search(r'id: (false|:\w+|"\w+")', opts)
        pkm = re.search(r'primary_key: (\[[^\]]*\]|"[^"]+")', opts)
        if pkm: pk = re.findall(r'"([^"]+)"', pkm.group(1))
        if not idm or idm.group(1) != 'false':
            if not pkm or len(pk) == 1:
                name = pk[0] if pk else 'id'
                kind = idm.group(1) if idm else ':bigint'
                typ = {':uuid': 'uuid', ':serial': 'serial', ':integer': 'serial', ':string': 'varchar',
                       ':bigserial': 'bigserial', ':bigint': 'bigserial', '"uuid"': 'uuid'}.get(kind, 'bigserial')
                cols.append(f'{q(name)} {typ} NOT NULL'); pk = [name]
        i += 1
        while i < len(lines) and not re.match(r'\s*end\s*$', lines[i]):
            l = lines[i]; i += 1
            m = re.match(r'\s*t\.(\w+) "([^"]+)"(.*)$', l)
            if m and m.group(1) not in ('index', 'check_constraint', 'virtual', 'exclusion_constraint'):
                kind, name, rest = m.groups()
                if kind == 'enum':
                    et = re.search(r'enum_type: "([^"]+)"', rest)
                    typ = q(et.group(1)) if et else 'varchar'
                else:
                    typ = TYPES.get(kind, 'text')
                    lim = re.search(r'limit: (\d+)', rest)
                    if kind == 'integer' and lim: typ = {'2': 'smallint', '8': 'bigint'}.get(lim.group(1), 'integer')
                if 'array: true' in rest: typ += '[]'
                if name in (pk or []) and any(c.startswith(q(name) + ' ') for c in cols): continue
                cols.append(f'{q(name)} {typ}' + (' NOT NULL' if 'null: false' in rest else ''))
                continue
            m = re.match(r'\s*t\.index (\[[^\]]*\]|"[^"]*"), (.*)$', l)
            if m:
                rest = m.group(2)
                using = re.search(r'using: :(\w+)', rest)
                if using and using.group(1) != 'btree': continue
                opc = re.search(r'opclass: :(\w+)', rest)
                if opc and opc.group(1) not in ('text_pattern_ops', 'varchar_pattern_ops'): continue
                name = re.search(r'name: "([^"]+)"', rest).group(1)
                if m.group(1).startswith('['):
                    body = ', '.join(q(c) + (f' {opc.group(1)}' if opc else '') for c in re.findall(r'"([^"]+)"', m.group(1)))
                else: body = m.group(1)[1:-1].replace('\\"', '"')
                w = re.search(r'where: "((?:[^"\\]|\\.)*)"', rest)
                idx.append(f"CREATE {'UNIQUE ' if 'unique: true' in rest else ''}INDEX {q(name)} ON {q(table)} ({body})"
                           + (' NULLS NOT DISTINCT' if 'nulls_not_distinct: true' in rest else '')
                           + (f" WHERE {w.group(1)}".replace('\\"', '"') if w else '') + ';')
        if pk: cols.append('PRIMARY KEY (' + ', '.join(q(c) for c in pk) + ')')
        out.append(f'CREATE TABLE {q(table)} (\n  ' + ',\n  '.join(cols) + '\n);')
        out += idx
        i += 1
    return [f'CREATE EXTENSION IF NOT EXISTS "{e}";' for e in sorted(exts)] + enums + out


if __name__ == '__main__':
    print('\n'.join(convert(open(sys.argv[1]).read())))
