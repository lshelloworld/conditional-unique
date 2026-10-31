"""Minimise the SQLite 'internal query planner error' that x4_decisions.py hit: rebuild the
table and indexes of the first failing query, then drop indexes, rows, ANALYZE and query
conjuncts while the error persists. Prints a self-contained SQL script.
Usage: python sqlite_repro.py WORKFILE"""
import json, os, random, re, sqlite3, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from x4_decisions import TABLES, ROOT, parse, Table, violations, q, indexes, pred


def fails(stmts, query):
    con = sqlite3.connect(':memory:')
    try:
        for s in stmts: con.execute(s)
    except sqlite3.Error:
        return False
    try:
        con.execute('explain query plan ' + query).fetchall(); return False
    except sqlite3.InternalError:
        return True


def main():
    d = json.load(open(os.path.join(HERE, 'x4_decisions.json')))
    name = next(n for n, v in d.items() if v['sqlite_errors'])
    query = d[name]['sqlite_errors'][0]['sql']
    ds = dict((n, s) for s, n in TABLES)[name]
    D = json.load(open(os.path.join(ROOT, 'discovery', 'results', f'{ds}.json')))
    raw = [r for t in D['tables'] if t['table'] == name for r in t['conditional'] if r.get('verified')][:40]
    keys = [dict(K=r['K'], cls=r['cls'], temps=parse(r['sql'], r['constants'])) for r in raw if r['cls'] != 'part']
    T = Table(ds, name, keys)
    T.keys = [k for k in keys if not violations(T.rows, T.cols, k['K'], k['cls'], T.scope_mask(k['temps']))]
    tn = q('x4_' + name.replace('.', '_'))
    create = f'CREATE TABLE {tn} (' + ', '.join(f'{q(c)} INTEGER' for c in T.cols) + ')'
    idx = [f"CREATE UNIQUE INDEX i{i} ON {tn} ({', '.join(q(c) for c in K)}) WHERE {pred(T, temps)}"
           for i, (temps, sem, K) in enumerate(indexes(T))]
    rows = [f'INSERT INTO {tn} VALUES ({", ".join("NULL" if v is None else str(v) for v in r)})' for r in T.rows]
    stmts = [create] + idx + rows + ['ANALYZE']
    assert fails(stmts, query), 'does not reproduce'
    changed = True
    while changed:                                   # one-at-a-time deletion (ddmin, step 1)
        changed = False
        for i in range(len(stmts) - 1, 0, -1):
            trial = stmts[:i] + stmts[i + 1:]
            if fails(trial, query): stmts, changed = trial, True
        conj = query.split(' AND ')
        for i in range(len(conj) - 1, 0, -1):
            trial = ' AND '.join(conj[:i] + conj[i + 1:])
            if trial.count('(') == trial.count(')') and fails(stmts, trial): query, changed = trial, True; break
    used = set(re.findall(r'"(\w+)"', ' '.join(stmts[1:]) + query)) - {tn.strip('"'), 'a', 'b'}
    cols = [c for c in T.cols if c in used]
    print(f'-- SQLite {sqlite3.sqlite_version}: "internal query planner error" ({name}, minimised)')
    print(create + ';')
    for s in stmts[1:]: print(s + ';')
    print('EXPLAIN QUERY PLAN ' + query + ';')
    print('-- columns referenced:', cols)


if __name__ == '__main__':
    main()
