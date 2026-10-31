"""Do the keys recommended on stats.stackexchange.com hold on other Stack Exchange sites?

All sites share one schema, so a recommendation that states an invariant of the platform should
hold on every site, and one that follows a correlation of the data of one site need not. For each
recommendation of se_mine.json and each site (CSV directories made by se_convert.py): untestable if
fewer than 50 rows of the site's scope have the key wholly non-null, else holds or fails on the
whole dump (as se_mine.holds: duplicates on K in the scope, rows with a null in K left out
under U). Writes se_transfer.json. Usage: python se_transfer.py SITE=CSVDIR..."""
import json, os, sys
import duckdb
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from se_mine import q


def kind(r):
    c = r['cond']
    if any(x in c for x in ('ContentLicense', 'HasLocation', 'HasWebsite', 'BountyAmount', 'CommunityOwned')):
        return 'correlation'
    if r['table'] == 'PostHistory' and 'UserId' in c and 'PostHistoryTypeId' not in c:
        return 'correlation'
    return 'invariant'


def main():
    recs = json.load(open(os.path.join(HERE, 'se_mine.json')))['recommendations']
    sites = dict(a.split('=', 1) for a in sys.argv[1:])
    out = []
    for site, d in sites.items():
        con = duckdb.connect()
        for f in os.listdir(d):
            con.execute(f"create table {f[:-4]} as select * from read_csv('{os.path.join(d, f)}', header=true, all_varchar=true)")
        for r in recs:
            K = r['key']
            nonnull = ' AND '.join(f'{q(c)} IS NOT NULL' for c in K)
            sup = con.execute(f"select count(*) from {r['table']} where ({r['cond']}) and {nonnull}").fetchone()[0]
            res = 'untestable'
            if sup >= 50:
                k = ', '.join(q(c) for c in sorted(K))
                nn = nonnull if r['sem'] == 'U' else 'true'
                dup = con.execute(f"select count(*) from (select {k} from {r['table']} where ({r['cond']}) and {nn} "
                                  f"group by {k} having count(*) > 1)").fetchone()[0]
                res = 'holds' if dup == 0 else 'fails'
            out.append(dict(site=site, table=r['table'], cond=r['cond'], key=K, sem=r['sem'], kind=kind(r),
                            holds_stats_2024=r['holds_full'], support=sup, result=res))
        print(site, 'done', flush=True)
    json.dump(out, open(os.path.join(HERE, 'se_transfer.json'), 'w'), indent=1)
    from collections import Counter
    print(Counter((x['site'], x['kind'], x['result']) for x in out))


if __name__ == '__main__':
    main()
