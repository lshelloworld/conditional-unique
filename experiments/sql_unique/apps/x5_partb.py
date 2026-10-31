"""X5 part B: would a recommender propose the declared conditions? Hide the 174 declared filtered
unique indexes and generate candidate conditions per table from two sources:
  schema roles  every nullable column (IS NULL / IS NOT NULL), boolean columns (= true / false),
                status-like columns (name matches status|state|type|kind|role|level|visibility|
                link_type|list_type|event|layout|locale|trigger, or an enum type): '= c' and
                'IN (...)' for constants c the data would supply;
  workload      the atoms (column IS [NOT] NULL, = c, IN (...), <> c) the code-derived queries
                (sites_*.json, lookups included) apply to the table.
An index condition is recovered by a source if every atom of it is among the source's
candidates, compared at the level of (column, atom kind) for schema roles (constants come from
the data) and with the constants for the workload. Conditions of the form 'K IS NOT NULL' on
key columns ('excluding null keys') follow from the key alone and are reported separately.
Writes x5_partb.json. Usage: python x5_partb.py APPSDIR"""
import json, os, re, sys
from collections import Counter, defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
ROLE = re.compile(r'(status|state|type|kind|role|level|visibility|link_type|list_type|event|layout|locale|trigger)', re.I)


def atoms(pred):
    """[(column, kind, constants)] of a predicate; kind in null, notnull, eq, neq, bool"""
    out = []
    p = pred
    for m in re.finditer(r'"?(\w+)"?\s+IS\s+(NOT\s+)?NULL', p, re.I):
        out.append((m.group(1), 'notnull' if m.group(2) else 'null', ()))
    for m in re.finditer(r'"?(\w+)"?\s*(?:::\w+)?\s*=\s*ANY\s*\(\s*(?:ARRAY)?\[?([^\])]*)', p, re.I):
        out.append((m.group(1), 'eq', tuple(v.strip(" '") for v in m.group(2).split(',') if v.strip())))
    for m in re.finditer(r'"?(\w+)"?\s+IN\s*\(([^)]*)\)', p, re.I):
        out.append((m.group(1), 'eq', tuple(v.strip(" '") for v in m.group(2).split(','))))
    for m in re.finditer(r'"?(\w+)"?\)?\s*(?:::[\w ]+)?\s*(=|<>|!=)\s*\(?\s*(\'[^\']*\'|-?\d+|true|false)', p, re.I):
        c, op, v = m.group(1), m.group(2), m.group(3).strip("'").lower()
        if c.upper() in ('ANY', 'ARRAY'): continue
        out.append((c, 'eq' if op == '=' else 'neq', (v,)))
    seen = {c for c, _, _ in out}
    for m in re.finditer(r'(?:^|\(|AND\s+|OR\s+)(NOT\s+)?"?(\w+)"?\s*(?=\)|$|\s+AND|\s+OR)', p, re.I):
        c = m.group(2)                            # bare boolean column, unless compared elsewhere
        if c.upper() not in ('TRUE', 'FALSE', 'NULL', 'NOT') and c not in seen:
            out.append((c, 'eq', ('false' if m.group(1) else 'true',)))
    return out


def schema_columns(appsdir, app):
    """{table: {column: (type, nullable)}} from schema.rb / structure.sql"""
    cols = defaultdict(dict)
    if app == 'gitlab':
        txt = open(os.path.join(appsdir, app, 'db', 'structure.sql')).read()
        for m in re.finditer(r'CREATE TABLE (?:public\.)?(\w+) \((.*?)\n\)', txt, re.S):
            for l in m.group(2).split('\n'):
                c = re.match(r'\s+(\w+) ([\w ]+?)(?:\[\])?(?: DEFAULT [^,]*)?( NOT NULL)?,?$', l)
                if c and c.group(1) != 'CONSTRAINT': cols[m.group(1)][c.group(1)] = (c.group(2), not c.group(3))
    else:
        table = None
        for l in open(os.path.join(appsdir, app, 'db', 'schema.rb')):
            m = re.match(r'\s*create_table "([^"]+)"', l)
            if m: table = m.group(1); continue
            m = re.match(r'\s*t\.(\w+) "([^"]+)"(.*)', l)
            if m and table and m.group(1) not in ('index', 'check_constraint'):
                cols[table][m.group(2)] = (m.group(1), 'null: false' not in m.group(3))
    return cols


def main():
    appsdir = sys.argv[1]
    idx = json.load(open(os.path.join(HERE, 'x5_indexes.json')))
    sites = []
    for f in os.listdir(HERE):
        if f.startswith('sites_') and f.endswith('.json'): sites += json.load(open(os.path.join(HERE, f)))
    st, rows = Counter(), []
    for app, v in idx.items():
        cols = schema_columns(appsdir, app)
        wl = defaultdict(set)                     # table -> {(col, kind, consts)}
        for s in sites:
            if s['app'] != app or not s.get('sql'): continue
            for t, c, rest in re.findall(r'"?(\w+)"?\."?(\w+)"?(\s*(?:IS (?:NOT )?NULL|=|IN|<>|!=)[^,]*)', s['sql']):
                for a in atoms(f'{c}{rest}'): wl[t].add(a)
            for a in atoms(s['sql']): wl[s['table']].add(a)
        for i in v['indexes']:
            t, K, A = i['table'], set(i['columns']), atoms(i['where'])
            if not A: st['predicate not parsed'] += 1; continue
            tc = cols.get(t, {})
            excl = all(k == 'notnull' and c in K for c, k, _ in A)
            def role(c, k):
                typ, nullable = tc.get(c, ('?', True))
                if k in ('null', 'notnull'): return nullable
                if typ in ('boolean',): return True
                return bool(ROLE.search(c)) or typ in ('enum', 'USER-DEFINED')
            by_role = all(role(c, k) for c, k, _ in A)
            by_wl_col = all(any(w[0] == c and w[1] == k for w in wl[t]) for c, k, _ in A)
            by_wl = all(any(w[0] == c and w[1] == k and set(cs) <= set(w[2]) | set() for w in wl[t]) if k in ('eq', 'neq')
                        else any(w[0] == c and w[1] == k for w in wl[t]) for c, k, cs in A)
            r = dict(app=app, index=i['name'], table=t, where=i['where'], atoms=[list(a) for a in A], excluding_nulls=excl,
                     schema_roles=by_role, workload_columns=by_wl_col, workload_exact=by_wl)
            rows.append(r)
            cls = 'excluding-null key' if excl else 'other condition'
            st[f'{cls}'] += 1
            for k in ('schema_roles', 'workload_columns', 'workload_exact'):
                if r[k]: st[f'{cls}: recovered by {k}'] += 1
            if r['schema_roles'] or r['workload_exact']: st[f'{cls}: recovered by either'] += 1
        st[f'{app}: candidate atoms from schema roles'] += sum(
            (2 if nullable else 0) + (2 if typ == 'boolean' else 0) + (1 if ROLE.search(c) and typ != 'boolean' else 0)
            for tbl in {i['table'] for i in v['indexes']} for c, (typ, nullable) in cols.get(tbl, {}).items())
        st[f'{app}: candidate atoms from workload'] += sum(len(wl[tbl]) for tbl in {i['table'] for i in v['indexes']})
    print(json.dumps(st, indent=1, sort_keys=True))
    json.dump(dict(stats=st, indexes=rows), open(os.path.join(HERE, 'x5_partb.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
