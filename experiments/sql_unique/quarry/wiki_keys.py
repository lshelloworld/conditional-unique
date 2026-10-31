"""Declare the recommendations of wiki_mine.json that hold on the check wiki, for tables of the
MediaWiki core schema, as filtered unique indexes wk_* in DSN (NULLS NOT DISTINCT for U=), or drop
them again. Usage: python wiki_keys.py DSN [drop]"""
import json, os, sys
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True)
    cur = con.cursor()
    cur.execute("select indexname from pg_indexes where indexname like 'wk\\_%'")
    for (n,) in cur.fetchall(): cur.execute(f'drop index {n}')
    if len(sys.argv) > 2: return
    made = 0
    for i, r in enumerate(json.load(open(os.path.join(HERE, 'wiki_mine.json')))['recommendations']):
        if r.get('holds_check') is not True: continue
        cur.execute("select to_regclass(%s) is not null", (r['table'],))
        if not cur.fetchone()[0]: print('  no table', r['table']); continue
        nnd = ' nulls not distinct' if r['sem'] == 'Ueq' else ''
        cur.execute(f"create unique index wk_{i} on {r['table']} ({', '.join(r['key'])}){nnd} where {r['cond']}")
        made += 1
    print(made, 'indexes')


if __name__ == '__main__':
    main()
