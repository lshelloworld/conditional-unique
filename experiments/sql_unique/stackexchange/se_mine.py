"""Recommend filtered unique indexes for the Stack Exchange data (stats.stackexchange.com) as the
recommendation section describes, and filter accidental keys by a temporal hold-out.

Conditions from schema roles: col = v for the values of categorical columns (at most 40 non-null
values), col IS NULL / IS NOT NULL for nullable columns, and conjunctions of one equality with
one null test on another column; plus the empty condition. Keys from data: by Proposition
'Reduction', the minimal keys of C : U(K) (C : U=(K)) are the minimal unique column combinations
of the rows matching C with each null replaced by a value of its own (all nulls by one value);
HPIValid (Desbordante) computes them. Id (the primary key) is left out of the key columns.
Mined on the rows created before 2020-01-01; a recommendation is (C, K, semantics) with
|scope| >= 50, at least 50 rows of the scope with K wholly non-null (under U a column that is null
throughout the scope is a key, vacuously), |K| <= 3, K not a key of the whole table, and, for a
conjunction, not already a key under either atom alone. Each is then checked on the full dump (April 2024): does it still
hold? Writes se_mine.json. Usage: python se_mine.py CSVDIR"""
import itertools, json, os, re, sys, tempfile, time
import duckdb, desbordante
HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='se_')
CUT = '2020-01-01'


def q(c): return '"' + c + '"'


def atom_sql(a):
    c, op, v = a
    if op == 'null': return f'{q(c)} IS NULL'
    if op == 'notnull': return f'{q(c)} IS NOT NULL'
    return f"{q(c)} = '{v}'"


def cond_sql(C): return ' AND '.join(atom_sql(a) for a in C) or 'true'


def candidate_conditions(con, t, cols):
    eqs, nulls = [], []
    n = con.execute(f'select count(*) from {t}').fetchone()[0]
    for c in cols:
        nn, nd = con.execute(f'select count({q(c)}), count(distinct {q(c)}) from {t}').fetchone()
        if 0 < nd <= 40:
            for (v,) in con.execute(f'select distinct {q(c)} from {t} where {q(c)} is not null order by 1').fetchall():
                eqs.append((c, 'eq', v))
        if 0 < nn < n:
            nulls += [(c, 'null', None), (c, 'notnull', None)]
    conds = [()] + [(a,) for a in eqs + nulls]
    conds += [(a, b) for a in eqs for b in nulls if a[0] != b[0]]
    return conds


def keys(con, t, cols, C, sem, where):
    """minimal UCCs of the encoded scope, as sets of column names"""
    fixed = {a[0] for a in C if a[1] in ('eq', 'null')}
    kc = [c for c in cols if c not in fixed]
    if not kc: return None, 0
    # values are hashed: Desbordante's CSV reader does not handle quoted commas, quotes or newlines
    enc = ', '.join((f"coalesce('v' || md5({q(c)}), 'N' || cast(row_number() over () as varchar))" if sem == 'U'
                     else f"coalesce('v' || md5({q(c)}), 'N')") + f' as c{i}' for i, c in enumerate(kc))
    path = os.path.join(TMP, 'scope.csv')
    n = con.execute(f"copy (select {enc} from {t} where ({cond_sql(C)}) and ({where})) to '{path}' (header true)").fetchone()[0]
    if n < 50: return None, n
    a = desbordante.ucc.algorithms.HPIValid()
    a.load_data(table=(path, ',', True), is_null_equal_null=True)   # nulls already encoded
    a.execute()
    out = []
    for u in a.get_uccs():
        idx = sorted(int(x) for x in re.findall(r'\d+', str(u)))
        out.append(frozenset(kc[i] for i in idx))
    return out, n


def holds(con, t, C, K, sem):
    k = ', '.join(q(c) for c in sorted(K))
    nonnull = ' AND '.join(f'{q(c)} IS NOT NULL' for c in K) if sem == 'U' else 'true'
    return con.execute(f'select count(*) from (select {k} from {t} where ({cond_sql(C)}) and {nonnull} '
                       f'group by {k} having count(*) > 1)').fetchone()[0] == 0


def main():
    csvdir = sys.argv[1]
    con = duckdb.connect()
    out, summary = [], {}
    for f in sorted(os.listdir(csvdir)):
        t = f[:-4]
        con.execute(f"create table {t} as select * from read_csv('{os.path.join(csvdir, f)}', header=true, all_varchar=true)")
        cols = [r[0] for r in con.execute(f"select column_name from duckdb_columns() where table_name = '{t}'").fetchall()]
        dated = 'created' in cols
        cols = [c for c in cols if c not in ('Id', 'created')]
        early = f"created < '{CUT}'" if dated else 'true'
        t0 = time.time()
        conds = candidate_conditions(con, t, cols)
        found = {}
        for sem in ('U', 'Ueq'):
            for C in conds:
                ks, n = keys(con, t, cols, C, sem, early)
                if ks is not None:
                    found[(C, sem)] = ([K for K in ks if len(K) <= 3], n)
        recs = []
        for (C, sem), (ks, n) in found.items():
            if not C: continue
            whole = found.get(((), sem), ([], 0))[0]
            subs = [found.get(((a,), sem), ([], 0))[0] for a in C] if len(C) == 2 else []
            for K in ks:
                if any(W <= K for W in whole) or any(any(W <= K for W in s) for s in subs):
                    continue
                nonnull = ' AND '.join(f'{q(c)} IS NOT NULL' for c in K)
                sup = con.execute(f'select count(*) from {t} where ({cond_sql(C)}) and ({early}) and {nonnull}').fetchone()[0]
                if sup < 50:
                    continue            # vacuous: under U, a column null throughout the scope is a key
                r = dict(table=t, cond=cond_sql(C), key=sorted(K), sem=sem, scope_early=n, support_early=sup,
                         holds_full=holds(con, t, C, K, sem) if dated else None)
                recs.append(r)
        out += recs
        st = dict(rows=con.execute(f'select count(*) from {t}').fetchone()[0], conditions=len(conds),
                  recommended=len(recs), still_hold=sum(r['holds_full'] is True for r in recs),
                  seconds=round(time.time() - t0, 1))
        summary[t] = st
        print(t, st, flush=True)
    json.dump(dict(cut=CUT, summary=summary, recommendations=out), open(os.path.join(HERE, 'se_mine.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
