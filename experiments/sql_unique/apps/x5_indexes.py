"""X5 step 1: the filtered (partial) unique indexes each application declares, from its current
db/schema.rb (Rails) or db/structure.sql (GitLab; partition copies skipped).
Writes x5_indexes.json: {app: {commit, date, indexes: [{name, table, columns, where, nnd}]}}.
Usage: python x5_indexes.py APPSDIR"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
APPS = ['mastodon', 'forem', 'chatwoot', 'loomio', 'maybe', 'docuseal', 'gitlab']


def from_rb(path):
    out, table = [], None
    for line in open(path):
        m = re.match(r'\s*create_table "([^"]+)"', line)
        if m: table = m.group(1); continue
        m = re.match(r'\s*t\.index (\[[^\]]*\]|"[^"]*"), (.*)$', line)
        if not m or 'unique: true' not in m.group(2): continue
        w = re.search(r'where: "((?:[^"\\]|\\.)*)"', m.group(2))
        if not w: continue
        cols = re.findall(r'"([^"]+)"', m.group(1))
        name = re.search(r'name: "([^"]+)"', m.group(2)).group(1)
        out.append(dict(name=name, table=table, columns=cols, where=w.group(1).replace('\\"', '"'),
                        nnd='nulls_not_distinct: true' in m.group(2)))
    return out


def from_sql(path):
    txt = open(path).read()
    out = []
    for m in re.finditer(r'CREATE UNIQUE INDEX (\w+) ON (?:ONLY )?(?:public\.)?(\w+) USING \w+ \((.*?)\)'
                         r'(?: INCLUDE \([^)]*\))?( NULLS NOT DISTINCT)? WHERE (.*);\n', txt):
        out.append(dict(name=m.group(1), table=m.group(2), columns=[c.strip() for c in m.group(3).split(',')],
                        where=m.group(5), nnd=bool(m.group(4))))
    return out


def main():
    root = sys.argv[1]
    res = {}
    for a in APPS:
        d = os.path.join(root, a)
        git = lambda *x: subprocess.run(['git', '-C', d, *x], capture_output=True, text=True).stdout.strip()
        idx = from_sql(os.path.join(d, 'db', 'structure.sql')) if a == 'gitlab' else from_rb(os.path.join(d, 'db', 'schema.rb'))
        res[a] = dict(commit=git('rev-parse', 'HEAD'), date=git('log', '-1', '--format=%cs'), indexes=idx)
        print(f'{a}: {len(idx)} filtered unique indexes on {len({i["table"] for i in idx})} tables', flush=True)
    json.dump(res, open(os.path.join(HERE, 'x5_indexes.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
