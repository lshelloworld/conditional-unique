"""Plan the SQL that users of Wikimedia's Quarry wrote against the Wiki Replicas, on MediaWiki's own
PostgreSQL schema (REL1_40 maintenance/postgres/tables-generated.sql, the release of the dataset's
time), with enable_conditional_unique off, on, and on with enable_conditional_unique_costing.

Queries: the Hugging Face dataset htriedman/wikidb (25,555 Quarry queries with title, wiki and SQL,
built for Wikimedia's task T337019, mid-2023; Quarry's SQL is CC0), read as data.
Preparation: comments, USE and SET statements dropped; anything but one read-only SELECT skipped;
@variables become NULL; MySQL translated by sqlglot (backticks, "strings", DATE(), IF(), ...).
Schema as on the replicas: timestamp columns are 14-digit strings (numeric constants compared with
them are quoted), templatelinks keeps tl_namespace and tl_title, "user" is quoted.
Also: the Wiki Replicas' alias views (revision_userindex, logging_logindex, actor_revision,
comment_logging, ...) are views over the base tables; extension tables (Wikibase, PageTriage,
GlobalUsage) are absent, so queries reading them do not plan.
Per query: plan changes, joins removed, GROUP BY keys shortened, DISTINCT removed, Inner Unique.
Writes OUT (default quarry_workload.json). Usage: python quarry_workload.py PARQUET DSN [OUT]"""
import json, os, re, sys
from collections import Counter
import duckdb, psycopg, sqlglot
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'stackexchange'))
from se_workload import joins, gkeys, aggs
WRITE = re.compile(r'\b(insert|update|delete|truncate|drop|alter|create|call|into|handler|load|lock)\b', re.I)
ALIASES = {
    'revision': ['revision_userindex', 'revision_compat'], 'logging': ['logging_logindex', 'logging_userindex', 'logging_compat'],
    'recentchanges': ['recentchanges_userindex', 'recentchanges_compat'], 'archive': ['archive_userindex'],
    'filearchive': ['filearchive_userindex'], 'ipblocks': ['ipblocks_ipindex'], 'oldimage': ['oldimage_userindex'],
    'actor': ['actor_' + t for t in ('archive', 'filearchive', 'image', 'ipblocks', 'logging', 'oldimage',
                                     'protected_titles', 'recentchanges', 'revision', 'user')],
    'comment': ['comment_' + t for t in ('archive', 'filearchive', 'image', 'ipblocks', 'logging', 'oldimage',
                                         'protected_titles', 'recentchanges', 'revision')],
}


def prepare(body):
    if not body: return None
    body = re.sub(r'(--|#)[^\n]*', ' ', body)
    body = re.sub(r'/\*.*?\*/', ' ', body, flags=re.S)
    parts = [p.strip() for p in body.split(';') if p.strip()]
    parts = [p for p in parts if not re.match(r'(use|set)\b', p, re.I)]
    if len(parts) != 1: return None
    sql = parts[0]
    if not re.match(r'(select|with)\b', sql, re.I) or WRITE.search(re.sub(r"'[^']*'|\"[^\"]*\"", "''", sql)):
        return None
    sql = re.sub(r'@\w+', 'NULL', sql)
    sql = re.sub(r'`?\b\w+_p`?\.(?=[`\w])', '', sql)            # enwiki_p.page -> page
    sql = re.sub(r'(\w*timestamp\w*\s*(?:[<>=!]=?|<>)\s*)(\d{4,14})\b', r"\1'\2'", sql, flags=re.I)
    try:
        out = sqlglot.transpile(sql, read='mysql', write='postgres')
    except Exception:
        return None
    if len(out) != 1: return None
    return re.sub(r'\b(from|join)\s+user\b', r'\1 "user"', out[0], flags=re.I)


def plan(cur, sql, on, costing, verbose=False):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute(f"set enable_conditional_unique_costing = {'on' if costing else 'off'}")
    cur.execute(f"explain ({'verbose, ' if verbose else ''}costs off) " + sql)
    return [r[0] for r in cur.fetchall()]


def main():
    parquet, dsn = sys.argv[1], sys.argv[2]
    out_name = sys.argv[3] if len(sys.argv) > 3 else 'quarry_workload.json'
    con = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
    cur = con.cursor()
    for base, views in ALIASES.items():                 # replicas: MySQL timestamps are 14-digit strings
        for v in views:
            cur.execute(f"select 1 from pg_views where viewname = '{v}'")
            if cur.fetchone(): cur.execute(f'drop view {v}')
    cur.execute("""select table_name, column_name from information_schema.columns
                   where table_schema = 'public' and data_type = 'timestamp with time zone'""")
    for t, c in cur.fetchall():
        cur.execute(f'alter table "{t}" alter column {c} type text using to_char({c}, \'YYYYMMDDHH24MISS\')')
    cur.execute('alter table templatelinks add column if not exists tl_namespace integer, '
                'add column if not exists tl_title text')  # still on the replicas in 2023
    for base, views in ALIASES.items():
        for v in views:
            cur.execute(f"select to_regclass('{v}') is null or exists (select 1 from pg_views where viewname = '{v}')")
            if cur.fetchone()[0]:                    # a name the schema already uses (an index) stays
                cur.execute(f'create or replace view {v} as select * from "{base}"')
    cur.execute('set statement_timeout = 10000')
    rows = duckdb.connect().execute(f"select title, wikidb, query from read_parquet('{parquet}')").fetchall()
    seen, res, st = set(), [], Counter()
    for title, wikidb, body in rows:
        st['queries'] += 1
        sql = prepare(body)
        if sql is None: st['not one read-only SELECT, or untranslatable'] += 1; continue
        key = re.sub(r'\s+', ' ', sql.lower())
        if key in seen: st['duplicate'] += 1; continue
        seen.add(key)
        r = dict(title=title, wiki=wikidb, sql=sql)
        try:
            cur.execute('begin read only')
            off, on, oc = plan(cur, sql, False, False), plan(cur, sql, True, False), plan(cur, sql, True, True)
            voff, voc = plan(cur, sql, False, False, True), plan(cur, sql, True, True, True)
            cur.execute('commit')
        except psycopg.Error as ex:
            cur.execute('rollback')
            r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0][:140]}'
            st['does not plan'] += 1; res.append(r); continue
        st['planned'] += 1
        r.update(changed=off != on, changed_costing=off != oc, removed=joins(on) < joins(off),
                 groupby=gkeys(on) != gkeys(off), distinct=aggs(on) < aggs(off),
                 unique=sum('Inner Unique: true' in l for l in voc) > sum('Inner Unique: true' in l for l in voff),
                 plan_off=off, plan_on=on, plan_costing=oc)
        for k in ('changed', 'changed_costing', 'removed', 'groupby', 'distinct', 'unique'):
            if r[k]: st[k] += 1
        if re.search(r'\bdistinct\b|\bgroup by\b|\bleft join\b', sql, re.I): st['has DISTINCT, GROUP BY or LEFT JOIN'] += 1
        res.append(r)
    print(json.dumps(st, indent=1))
    json.dump(res, open(os.path.join(HERE, out_name), 'w'), indent=1)


if __name__ == '__main__':
    main()
