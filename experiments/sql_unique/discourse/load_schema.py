"""X11: apply Discourse's db/structure.sql (a pg_dump, read and applied as SQL; nothing of
Discourse is executed) to a fresh database. pgvector is not installed, so its extension is
skipped and its halfvec columns become bytea; the 5 triggers that guard deprecated columns are
skipped. Prints the unique indexes and how many have predicates.
Usage: python load_schema.py STRUCTURE_SQL DSN_ADMIN DBNAME"""
import re, sys
import psycopg

src, dsn, db = sys.argv[1], sys.argv[2], sys.argv[3]
sql = open(src, encoding='utf-8').read()
sql = sql.replace('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;', '')
sql = re.sub(r'public\.halfvec(\(\d+\))?', 'bytea', sql)
sql = re.sub(r'^CREATE TRIGGER [^;]*;', '', sql, flags=re.M | re.S)
adm = psycopg.connect(dsn, autocommit=True)
adm.execute(f'DROP DATABASE IF EXISTS {db}'); adm.execute(f'CREATE DATABASE {db}')
con = psycopg.connect(re.sub(r'dbname=\w+', f'dbname={db}', dsn), autocommit=True)
con.execute(sql)
con.execute("SELECT pg_catalog.set_config('search_path', 'public', false)")
n = con.execute("select count(*) from pg_tables where schemaname = 'public'").fetchone()[0]
u = con.execute("select count(*), count(*) filter (where indpred is not null) from pg_index i "
                "join pg_class c on c.oid = i.indrelid join pg_namespace s on s.oid = c.relnamespace "
                "where s.nspname = 'public' and indisunique").fetchone()
print(f'{db}: {n} tables, {u[0]} unique indexes, {u[1]} with predicates')
