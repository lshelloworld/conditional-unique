"""Plan the SQL that MetaBrainz forum users wrote against a MusicBrainz copy (forum_queries.json,
mb_forum.py) with enable_conditional_unique off and on, over the MusicBrainz schema with its own
17 filtered unique indexes and CHECK constraints (database built by load_mb.sh).

Each posted block is split at semicolons; statements that are a single SELECT or WITH ... SELECT
are kept (psql commands, writes and DDL are dropped), psql variables (:'v', :v) and placeholders
($1, %s) become NULL, and duplicates are dropped. Then as in mb_plan.py: EXPLAIN off and on in a
read-only transaction, plan changes, proofs, and which filtered indexes the query names with their
predicate columns. Writes mb_forum_plan.json. Usage: python mb_forum_plan.py DSN"""
import json, os, re, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mb_plan import plan, joins, gkeys, aggs, NOTICES

WRITE = re.compile(r'\b(insert|update|delete|truncate|drop|alter|create|grant|copy|call|do|vacuum)\b', re.I)


def statements(block):
    block = re.sub(r'--[^\n]*', ' ', block)
    block = re.sub(r'/\*.*?\*/', ' ', block, flags=re.S)
    block = '\n'.join(l for l in block.split('\n') if not l.strip().startswith('\\'))   # psql meta-commands
    for st in block.split(';'):
        st = st.strip()
        if not re.match(r'(select|with)\b', st, re.I) or WRITE.search(re.sub(r"'[^']*'", "''", st)):
            continue
        st = re.sub(r":'\w+'|(?<![:\w]):\w+|\$\d+|%s", 'NULL', st)
        yield st


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True, prepare_threshold=None)
    con.add_notice_handler(lambda d: NOTICES.append(d.message_primary))
    cur = con.cursor()
    cur.execute('set search_path = musicbrainz, public'); cur.execute('set statement_timeout = 10000')
    cur.execute("""select c.relname, pg_get_expr(x.indpred, x.indrelid) from pg_index x
                   join pg_class c on c.oid = x.indrelid join pg_namespace n on n.oid = c.relnamespace
                   where n.nspname = 'musicbrainz' and x.indisunique and x.indpred is not null""")
    fidx = cur.fetchall()
    seen, out, st = set(), [], Counter()
    for b in json.load(open(os.path.join(HERE, 'forum_queries.json'))):
        st['blocks'] += 1
        for sql in statements(b['sql']):
            key = re.sub(r'\s+', ' ', sql.lower())
            if key in seen: st['duplicate'] += 1; continue
            seen.add(key); st['queries'] += 1
            low = sql.lower()
            names = sorted({t for t, p in fidx if re.search(rf'\b{t}\b', low) and
                            all(re.search(rf'\b{c}\b', low) for c in re.findall(r'\b(primary_for_locale|comment|locale)\b', p))})
            r = dict(origin=b['origin'], title=b['title'], sql=sql, names_filtered=names)
            try:
                cur.execute('begin read only')
                off, on = plan(cur, sql, False), plan(cur, sql, True)
                voff = plan(cur, sql, False, True)
                cur.execute('set client_min_messages = debug1'); NOTICES.clear()
                von = plan(cur, sql, True, True)
                cur.execute('reset client_min_messages'); cur.execute('commit')
            except psycopg.Error as ex:
                cur.execute('rollback')
                r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0][:140]}'
                st['does not plan'] += 1; out.append(r); continue
            st['planned'] += 1
            r.update(proofs=sum('conditional unique: implied' in m for m in NOTICES), changed=off != on,
                     removed=joins(on) < joins(off), groupby=gkeys(on) != gkeys(off), distinct=aggs(on) < aggs(off),
                     unique=sum('Inner Unique: true' in l for l in von) > sum('Inner Unique: true' in l for l in voff),
                     plan_off=off, plan_on=on)
            for k in ('proofs', 'changed', 'removed', 'groupby', 'distinct', 'unique'):
                if r[k]: st[k] += 1
            if names: st['names a filtered index and its predicate columns'] += 1
            out.append(r)
    print(json.dumps(st, indent=1, sort_keys=True))
    json.dump(out, open(os.path.join(HERE, 'mb_forum_plan.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
