"""Declare the recommender's output (se_mine.json) as filtered unique indexes on the loaded data:
every recommendation that holds on the full dump (or has no dates), one index per condition and
key, NULLS NOT DISTINCT if U= was recommended (it implies U). Presence flags of se_convert.py are
mapped back to the columns they stand for (Closed -> closeddate IS NOT NULL, ...). Creating an
index checks it on the data. With 'drop', removes them again.
Usage: python se_keys.py DSN [drop]"""
import json, os, re, sys
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = {'Closed': 'closeddate', 'CommunityOwned': 'communityowneddate', 'HasWebsite': 'websiteurl',
         'HasLocation': 'location', 'AnonymousName': 'userdisplayname'}


def pred(cond):
    def flag(m):
        return f"{FLAGS[m.group(1)]} IS {'NOT ' if m.group(2) == 'true' else ''}NULL"
    cond = re.sub(r'"(' + '|'.join(FLAGS) + r')" = \'(true|false)\'', flag, cond)
    return re.sub(r'"(\w+)"', lambda m: m.group(1).lower(), cond)


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True)
    for (n,) in con.execute("select indexname from pg_indexes where schemaname = 'public' and indexname like 'rec\\_%'").fetchall():
        con.execute(f'drop index {n}')
    if len(sys.argv) > 2 and sys.argv[2] == 'drop':
        print('dropped'); return
    recs = json.load(open(os.path.join(HERE, 'se_mine.json')))['recommendations']
    want = {}
    for r in recs:
        if r['holds_full'] is False: continue
        k = (r['table'], r['cond'], tuple(r['key']))
        want[k] = want.get(k, False) or r['sem'] == 'Ueq'
    made = 0
    for i, ((t, cond, key), nnd) in enumerate(sorted(want.items())):
        sql = (f"create unique index rec_{i} on {t.lower()} ({', '.join(c.lower() for c in key)})"
               + (' nulls not distinct' if nnd else '') + f' where {pred(cond)}')
        try:
            con.execute(sql); made += 1
        except psycopg.Error as ex:
            print('FAILED', sql, type(ex).__name__, str(ex).splitlines()[0][:100])
    con.execute('analyze')
    print(made, 'filtered unique indexes declared of', len(want))


if __name__ == '__main__':
    main()
