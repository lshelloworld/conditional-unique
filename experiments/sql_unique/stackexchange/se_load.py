"""Load the Stack Exchange dump (stats.stackexchange.com, April 2024) into PostgreSQL with the
table and column names of the Stack Exchange Data Explorer, so that its users' queries run
unchanged (identifiers in lower case, as PostgreSQL folds unquoted names).

Tables: the eight of the dump with all their attributes (types by name: ids and counts as
bigint, dates as timestamp, flags as boolean, the rest as text), primary keys on Id; PostTags
(PostId, TagId) derived from Posts.Tags; and the lookup tables PostTypes and VoteTypes with the
documented names. Usage: python se_load.py XMLDIR DSN"""
import csv, io, os, re, sys
import xml.etree.ElementTree as ET
import psycopg

TABLES = ['Posts', 'Users', 'Votes', 'Comments', 'Badges', 'PostHistory', 'PostLinks', 'Tags']
INT = re.compile(r'(Id|Score|ViewCount|AnswerCount|CommentCount|FavoriteCount|Reputation|Views|UpVotes|'
                 r'DownVotes|BountyAmount|Class|Count)$')
BOOL = {'TagBased', 'IsModeratorOnly', 'IsRequired'}
POST_TYPES = [(1, 'Question'), (2, 'Answer'), (3, 'Wiki'), (4, 'TagWikiExcerpt'), (5, 'TagWiki'),
              (6, 'ModeratorNomination'), (7, 'WikiPlaceholder'), (8, 'PrivilegeWiki')]
VOTE_TYPES = [(1, 'AcceptedByOriginator'), (2, 'UpMod'), (3, 'DownMod'), (4, 'Offensive'), (5, 'Favorite'),
              (6, 'Close'), (7, 'Reopen'), (8, 'BountyStart'), (9, 'BountyClose'), (10, 'Deletion'),
              (11, 'Undeletion'), (12, 'Spam'), (15, 'ModeratorReview'), (16, 'ApproveEditSuggestion')]


def typ(c):
    if c in BOOL: return 'boolean'
    if c == 'Id' or INT.search(c): return 'bigint'
    if 'Date' in c: return 'timestamp'
    return 'text'


def main():
    src, dsn = sys.argv[1], sys.argv[2]
    con = psycopg.connect(dsn, autocommit=True)
    for t in TABLES:
        path = os.path.join(src, f'{t}.xml')
        cols = []
        for _, el in ET.iterparse(path):               # first pass: the attribute names
            if el.tag == 'row':
                for k in el.attrib:
                    if k not in cols: cols.append(k)
            el.clear()
        con.execute(f'drop table if exists {t.lower()} cascade')
        con.execute(f"create table {t.lower()} ({', '.join(f'{c.lower()} {typ(c)}' for c in cols)})")
        n = 0
        with con.cursor() as cur, cur.copy(f"copy {t.lower()} ({', '.join(c.lower() for c in cols)}) from stdin") as cp:
            for _, el in ET.iterparse(path):
                if el.tag != 'row': continue
                cp.write_row([el.attrib.get(c) for c in cols]); el.clear(); n += 1
        con.execute(f'alter table {t.lower()} add primary key (id)')
        print(t, n, len(cols), flush=True)
    con.execute('drop table if exists posttags')
    con.execute("""create table posttags as
                   select p.id as postid, t.id as tagid
                   from posts p cross join lateral unnest(string_to_array(trim(both '|' from p.tags), '|')) as tn(name)
                   join tags t on t.tagname = tn.name""")
    con.execute('alter table posttags add primary key (postid, tagid)')
    for name, rows in (('posttypes', POST_TYPES), ('votetypes', VOTE_TYPES)):
        con.execute(f'drop table if exists {name}')
        con.execute(f'create table {name} (id bigint primary key, name text not null)')
        with con.cursor() as cur:
            cur.executemany(f'insert into {name} values (%s, %s)', rows)
    con.execute('analyze')
    print('posttags', con.execute('select count(*) from posttags').fetchone()[0])


if __name__ == '__main__':
    main()
