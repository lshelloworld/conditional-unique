"""Recommend filtered unique indexes for MediaWiki data as on Stack Exchange (../stackexchange/
se_mine.py, whose condition generator, HPIValid key finder and validity check are reused):
conditions from schema roles (values of columns with at most 40 values, null tests, conjunctions of
one of each), minimal keys of at most three columns per scope under U and U=, at least 50 rows with
the key non-null, not implied by a key of the whole table and the columns the condition fixes, not already a key under one atom of a conjunction.
Primary-key columns of single-column primary keys are left out of the key columns. The dumps carry
no creation dates, so instead of a temporal hold-out each recommendation is checked on a second wiki
(CHECKDIR), as the cross-site check did for Stack Exchange.
Writes wiki_mine.json. Usage: python wiki_mine.py CSVDIR CHECKDIR"""
import json, os, sys, time
import duckdb
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'stackexchange'))
from se_mine import candidate_conditions, keys, holds, cond_sql, q
SKIP = {'page': ['page_id'], 'category': ['cat_id'], 'linktarget': ['lt_id'], 'change_tag_def': ['ctd_id'],
        'geo_tags': ['gt_id'], 'user_groups': [], 'page_restrictions': ['pr_id']}
TABLES = ['page', 'page_props', 'redirect', 'category', 'categorylinks', 'user_groups', 'user_former_groups',
          'page_restrictions', 'protected_titles', 'linktarget', 'geo_tags', 'babel']     # not the id-only link tables


def load(con, d, t, name):
    path = os.path.join(d, t + '.csv')
    if not os.path.exists(path): return False
    con.execute(f"create table {name} as select * from read_csv('{path}', header=true, all_varchar=true)")
    return True


def main():
    src, chk = sys.argv[1], sys.argv[2]
    con = duckdb.connect()
    out, summary = [], {}
    for t in TABLES:
        if not load(con, src, t, t): continue
        has_chk = load(con, chk, t, 'chk_' + t)
        cols = [r[0] for r in con.execute(f"select column_name from duckdb_columns() where table_name = '{t}'").fetchall()]
        cols = [c for c in cols if c not in SKIP.get(t, [])]
        t0 = time.time()
        conds = candidate_conditions(con, t, cols)
        found = {}
        for sem in ('U', 'Ueq'):
            for C in conds:
                ks, n = keys(con, t, cols, C, sem, 'true')
                if ks is not None:
                    found[(C, sem)] = ([K for K in ks if len(K) <= 3], n)
        recs = []
        for (C, sem), (ks, n) in found.items():
            if not C: continue
            whole = found.get(((), sem), ([], 0))[0]
            subs = [found.get(((a,), sem), ([], 0))[0] for a in C] if len(C) == 2 else []
            fixed = {a[0] for a in C if a[1] in ('eq', 'null')}
            for K in ks:
                if any(W <= K | fixed for W in whole) or any(any(W <= K for W in s) for s in subs):
                    continue
                nonnull = ' AND '.join(f'{q(c)} IS NOT NULL' for c in K)
                sup = con.execute(f'select count(*) from {t} where ({cond_sql(C)}) and {nonnull}').fetchone()[0]
                if sup < 50: continue
                r = dict(table=t, cond=cond_sql(C), key=sorted(K), sem=sem, scope=n, support=sup)
                if has_chk:
                    csup = con.execute(f'select count(*) from chk_{t} where ({cond_sql(C)}) and {nonnull}').fetchone()[0]
                    r['check_support'] = csup
                    r['holds_check'] = holds(con, 'chk_' + t, C, K, sem) if csup >= 50 else None
                recs.append(r)
        out += recs
        st = dict(rows=con.execute(f'select count(*) from {t}').fetchone()[0], conditions=len(conds), recommended=len(recs),
                  hold_on_check=sum(r.get('holds_check') is True for r in recs),
                  fail_on_check=sum(r.get('holds_check') is False for r in recs), seconds=round(time.time() - t0, 1))
        summary[t] = st
        print(t, st, flush=True)
    json.dump(dict(summary=summary, recommendations=out), open(os.path.join(HERE, 'wiki_mine.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
