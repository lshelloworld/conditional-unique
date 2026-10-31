"""MusicBrainz: which of its 17 filtered unique indexes does the prover use?

Plans, with enable_conditional_unique off and on (EXPLAIN only, read-only transaction):
  lb   the 20 queries ListenBrainz runs against MusicBrainz (lb_queries.json, extract_lb.py);
  cq   constructed consumer queries that use the filtered keys the way a reader of the data
       would (labelled as such; the MusicBrainz server and ListenBrainz issue none of them).
Per query: plan changed, joins removed, Inner Unique added, GROUP BY key shortened, DISTINCT
removed, the prover's DEBUG1 'implied' messages, and which filtered indexes the query names
(table and predicate columns). Writes mb_plan.json. Usage: python mb_plan.py DSN"""
import json, os, re, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
NOTICES = []

CQ = [
    ('artist with primary English alias (alias used)',
     "SELECT a.gid, a.name, aa.name AS alias FROM artist a LEFT JOIN artist_alias aa "
     "ON aa.artist = a.id AND aa.locale = 'en' AND aa.primary_for_locale"),
    ('artist list, alias join unused (ORM eager load)',
     "SELECT a.gid, a.name FROM artist a LEFT JOIN artist_alias aa "
     "ON aa.artist = a.id AND aa.locale = 'en' AND aa.primary_for_locale"),
    ('credits per artist, grouped with its primary English alias',
     "SELECT a.id, aa.name, count(*) FROM artist a JOIN artist_alias aa ON aa.artist = a.id "
     "AND aa.locale = 'en' AND aa.primary_for_locale JOIN artist_credit_name acn ON acn.artist = a.id "
     "GROUP BY a.id, aa.name"),
    ('distinct artists with primary English alias',
     "SELECT DISTINCT a.id, aa.name FROM artist a JOIN artist_alias aa ON aa.artist = a.id "
     "AND aa.locale = 'en' AND aa.primary_for_locale"),
    ('primary aliases per artist and locale (CHECK implies locale not null)',
     "SELECT DISTINCT artist, locale FROM artist_alias WHERE primary_for_locale"),
    ('... with locale IS NOT NULL written out',
     "SELECT DISTINCT artist, locale FROM artist_alias WHERE primary_for_locale AND locale IS NOT NULL"),
    ('distinct artist names and comments (legacy pair: an unconditional key)',
     "SELECT DISTINCT name, comment FROM artist"),
    ('labels by name and comment, grouped',
     "SELECT name, comment, count(*) FROM label JOIN release_label rl ON rl.label = label.id "
     "GROUP BY label.id, name, comment"),
    ('releases with the primary alias of their release group in a locale',
     "SELECT r.gid, rga.name FROM release r JOIN release_group rg ON rg.id = r.release_group "
     "LEFT JOIN release_group_alias rga ON rga.release_group = rg.id AND rga.locale = 'ja' AND rga.primary_for_locale"),
    ('works with primary alias, IN semi-join on the alias scope',
     "SELECT w.gid FROM work w WHERE w.id IN (SELECT wa.work FROM work_alias wa WHERE wa.locale = 'de' AND wa.primary_for_locale)"),
]


def plan(cur, sql, on, verbose=False):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute(f"explain ({'verbose, ' if verbose else ''}costs off) " + sql)
    return [r[0] for r in cur.fetchall()]


def joins(p): return sum(bool(re.search(r'\b(Join|Nested Loop)\b', l)) for l in p)
def gkeys(p): return [l for l in p if 'Group Key' in l]
def aggs(p): return sum(bool(re.search(r'(Unique|HashAggregate|GroupAggregate)\b', l)) for l in p)


def main():
    con = psycopg.connect(sys.argv[1], autocommit=True, prepare_threshold=None)
    con.add_notice_handler(lambda d: NOTICES.append(d.message_primary))
    cur = con.cursor()
    cur.execute("set search_path = musicbrainz, public")
    cur.execute("""select c.relname, i.relname, pg_get_expr(x.indpred, x.indrelid) from pg_index x
                   join pg_class i on i.oid = x.indexrelid join pg_class c on c.oid = x.indrelid
                   join pg_namespace n on n.oid = c.relnamespace
                   where n.nspname = 'musicbrainz' and x.indisunique and x.indpred is not null""")
    fidx = cur.fetchall()
    qs = [dict(kind='lb', origin=f"{q['file']}:{q['line']}", sql=q['sql'])
          for q in json.load(open(os.path.join(HERE, 'lb_queries.json')))]
    qs += [dict(kind='cq', origin=name, sql=sql) for name, sql in CQ]
    out, st = [], Counter()
    for q in qs:
        low = q['sql'].lower()
        q['names_filtered'] = sorted(ix for t, ix, p in fidx
                                     if re.search(rf'\b{t}\b', low) and
                                     all(re.search(rf'\b{c}\b', low) for c in re.findall(r'\b(primary_for_locale|comment|locale)\b', p)))
        try:
            cur.execute('begin read only')
            off, on = plan(cur, q['sql'], False), plan(cur, q['sql'], True)
            voff = plan(cur, q['sql'], False, True)
            cur.execute('set client_min_messages = debug1'); NOTICES.clear()
            von = plan(cur, q['sql'], True, True)
            cur.execute('reset client_min_messages'); cur.execute('commit')
        except psycopg.Error as ex:
            cur.execute('rollback')
            q['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0][:140]}'
            st[f"{q['kind']} errors"] += 1; out.append(q); continue
        q.update(proofs=sum('conditional unique: implied' in m for m in NOTICES), changed=off != on,
                 removed=joins(on) < joins(off), groupby=gkeys(on) != gkeys(off), distinct=aggs(on) < aggs(off),
                 unique=sum('Inner Unique: true' in l for l in von) > sum('Inner Unique: true' in l for l in voff),
                 plan_off=off, plan_on=on)
        st[f"{q['kind']} planned"] += 1
        for k in ('proofs', 'changed', 'removed', 'groupby', 'distinct', 'unique'):
            if q[k]: st[f"{q['kind']} {k}"] += 1
        if q['names_filtered']: st[f"{q['kind']} names a filtered index"] += 1
        out.append(q)
        flags = ' '.join(k for k in ('changed', 'removed', 'unique', 'groupby', 'distinct') if q[k])
        print(f"{q['kind']} {q['origin'][:70]:70s} proofs {q['proofs']} {flags}", flush=True)
    print(json.dumps(st, indent=1, sort_keys=True))
    json.dump(out, open(os.path.join(HERE, 'mb_plan.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
