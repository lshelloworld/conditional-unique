"""How common are filtered unique indexes in the wild, and what do their predicates look like?

Reads SchemaPile-Perm (Doehmen, Radu, Hulsebos, Schelter; Zenodo 12682521, CC BY 4.0: SQL files
from public GitHub repositories with permissive licences) straight from the tarball, as text.
Per file: unique indexes (CREATE UNIQUE [CLUSTERED|NONCLUSTERED] INDEX ... ON t (...)
[NULLS [NOT] DISTINCT] [INCLUDE (...)] [WHERE p]), UNIQUE and PRIMARY KEY constraints, and for each
filtered unique index its predicate, classified as in the paper's study of application schemas:
  exclude-null  every atom is "key column IS NOT NULL"
  null-test     IS [NOT] NULL on another column
  const / flag  = constant, or a bare / negated / IS TRUE-FALSE boolean column
  in-list       IN (...) / = ANY (ARRAY[...])
  inequality    <> / != / NOT IN
  range         <, <=, >, >=, BETWEEN
  other         functions, subqueries, LIKE, ...
and whether it is a conjunction, uses OR, and whether the key has an expression. Comments are
stripped and statements split at semicolons; this is a lexical count, not a parse.
Files are assigned a dialect by lexical cues (dialect()); MySQL has no filtered indexes.
Writes sp_count.json. Usage: python sp_count.py SQLFILES_TARBALL"""
import json, os, re, sys, tarfile
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
UIDX = re.compile(r'\bcreate\s+unique\s+(?:clustered\s+|nonclustered\s+)?index\s+(?:concurrently\s+)?'
                  r'(?:if\s+not\s+exists\s+)?(?:[\w."`\[\]]+\s+)?on\s+(?:only\s+)?([\w."`\[\]]+)\s*'
                  r'(?:using\s+\w+\s*)?\((.*?)\)\s*(.*)$', re.I | re.S)


def strip(sql):
    sql = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.S)
    return re.sub(r'(--|#)[^\n]*', ' ', sql)


def atoms(pred):
    p = re.sub(r"'[^']*'", "'c'", pred)
    parts = re.split(r'\band\b|\bor\b', p, flags=re.I)
    return [a.strip(' ()') for a in parts if a.strip(' ()')], bool(re.search(r'\bor\b', p, re.I))


def kind(a, keycols):
    al = a.lower()
    m = re.fullmatch(r'["`\[]?(\w+)["`\]]?\s+is\s+not\s+null', al)
    if m and m.group(1) in keycols: return 'exclude-null'
    if re.search(r'\bis\s+(not\s+)?null\b', al): return 'null-test'
    if re.search(r'\bbetween\b|<=|>=|(?<![<>!])[<>](?![=>])', al): return 'range'
    if re.search(r'<>|!=|\bnot\s+in\b', al): return 'inequality'
    if re.search(r'\bin\s*\(|=\s*any\s*\(', al): return 'in-list'
    if re.search(r'=', al) or re.fullmatch(r'(not\s+)?["`\[]?\w+["`\]]?(\s+is\s+(not\s+)?(true|false))?', al): return 'const/flag'
    return 'other'


def dialect(sql):
    """a lexical guess: PostgreSQL, SQL Server, SQLite, MySQL, or unknown"""
    if re.search(r'::\w|\bserial\b|\bbigserial\b|create\s+extension|owner\s+to|pg_catalog|\bjsonb\b|\btimestamptz\b|\bplpgsql\b', sql, re.I):
        return 'postgresql'
    if re.search(r'\bnonclustered\b|\bidentity\s*\(|\[dbo\]|\bnvarchar\b|^\s*go\s*$', sql, re.I | re.M):
        return 'sqlserver'
    if re.search(r'\bengine\s*=|\bauto_increment\b|`', sql, re.I):
        return 'mysql'
    if re.search(r'\bautoincrement\b|\bsqlite', sql, re.I):
        return 'sqlite'
    return 'unknown'


def main():
    st, shapes, files = Counter(), Counter(), Counter()
    bydial = Counter()
    with tarfile.open(sys.argv[1]) as tf:
        for m in tf:
            if not m.isfile() or not m.name.lower().endswith('.sql'): continue
            st['files'] += 1
            sql = strip(tf.extractfile(m).read().decode('utf-8', 'replace'))
            dl = dialect(sql)
            bydial[(dl, 'files')] += 1
            fu = ff = 0
            for stmt in sql.split(';'):
                g = UIDX.search(stmt)
                if g:
                    st['unique indexes'] += 1; fu += 1; bydial[(dl, 'unique indexes')] += 1
                    keys, rest = g.group(2), g.group(3)
                    if re.search(r'nulls\s+not\s+distinct', rest, re.I): st['... NULLS NOT DISTINCT'] += 1
                    w = re.search(r'\bwhere\b(.*)$', rest, re.I | re.S)
                    if not w: continue
                    st['filtered unique indexes'] += 1; ff += 1; bydial[(dl, 'filtered unique indexes')] += 1
                    keycols = {re.sub(r'\W', '', k.split()[0]).lower() for k in keys.split(',') if k.strip()}
                    if re.search(r'\w\s*\(', keys): st['... with an expression key'] += 1
                    at, has_or = atoms(w.group(1))
                    ks = [kind(a, keycols) for a in at]
                    if has_or: st['... with OR'] += 1
                    elif len(at) > 1: st['... conjunctions'] += 1
                    if ks and all(k == 'exclude-null' for k in ks): shapes['exclude-null only'] += 1
                    for k in set(ks): shapes[k] += 1
                elif re.search(r'\bcreate\s+table\b', stmt, re.I):
                    n = len(re.findall(r'\bunique\b|\bprimary\s+key\b', stmt, re.I))
                    st['UNIQUE / PRIMARY KEY in CREATE TABLE'] += n
                    fu += n
                if re.search(r'\balter\s+table\b.*\b(unique|primary\s+key)\b', stmt, re.I | re.S):
                    st['UNIQUE / PRIMARY KEY by ALTER TABLE'] += 1; fu += 1
            if fu: files['files with a key'] += 1
            if ff: files['files with a filtered unique index'] += 1; bydial[(dl, 'files with a filtered one')] += 1
    out = dict(stats=dict(st), files=dict(files), shapes=dict(shapes),
               by_dialect={f'{d}: {k}': v for (d, k), v in sorted(bydial.items())})
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(HERE, 'sp_count.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
