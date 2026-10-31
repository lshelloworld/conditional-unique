"""X8: do the mined keys survive TPC-DS-style data maintenance?

DuckDB's dsdgen cannot generate refresh sets, so the dimension maintenance of the TPC-DS
specification is emulated on a copy of the SF1 database (an emulation, not the official
refresh data):
  history-keeping dimensions (item, store, call_center, web_page, web_site): per round, RATE of
    the current versions (rec_end_date IS NULL) get a new version: the current row is closed
    (rec_end_date = the refresh date) and a successor with a fresh surrogate key, the same
    business key, rec_start_date = refresh date + 1 and rec_end_date NULL is inserted;
  non-history dimensions (call_center ... see DYNAMIC): RATE of the rows are updated in place;
  all maintained dimensions: RATE / 2 new entities are inserted (fresh surrogate and business
    keys).
New attribute values: each non-key attribute keeps its old value with probability 1/2 and is
otherwise drawn from the column's existing values (new rows: every attribute drawn), so values
stay within each column's domain. Static dimensions (date_dim, time_dim, household_demographics,
customer_demographics, income_band, reason, ship_mode) are not maintained.
After each of ROUNDS rounds every mined key of mined.json is re-validated with stable.holds().
Writes x8_refresh.json. Usage: python x8_refresh.py WORKDIR"""
import datetime, json, os, random, shutil, sys, time
from collections import Counter
import duckdb
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from load_tpcds import PK, BUSINESS
from stable import holds

HISTORY = {'item': 'i', 'store': 's', 'call_center': 'cc', 'web_page': 'wp', 'web_site': 'web'}
DYNAMIC = ['call_center', 'catalog_page', 'customer', 'customer_address', 'item', 'promotion',
           'store', 'warehouse', 'web_page', 'web_site']
RATE, ROUNDS = 0.05, 3


def refresh(con, t, rnd, rng, day):
    cols = [r[0] for r in con.execute(f"select column_name from duckdb_columns() where table_name = '{t}' order by column_index").fetchall()]
    sk, bk = PK[t][0], BUSINESS.get(t)
    pool = {c: [r[0] for r in con.execute(f'select {c} from {t}').fetchall()] for c in cols}
    hist = HISTORY.get(t)
    fixed = {sk, bk} | ({f'{hist}_rec_start_date', f'{hist}_rec_end_date'} if hist else set())
    nxt = con.execute(f'select max({sk}) from {t}').fetchone()[0] + 1
    where = f'{hist}_rec_end_date IS NULL' if hist else 'TRUE'
    rows = con.execute(f'select * from {t} where {where}').fetchall()
    chosen = rng.sample(rows, max(1, int(RATE * len(rows))))
    news, upd = [], 0
    def mutate(r):
        return [r[i] if c in fixed or rng.random() < 0.5 else rng.choice(pool[c]) for i, c in enumerate(cols)]
    for r in chosen:
        n = mutate(r)
        if hist:
            con.execute(f'update {t} set {hist}_rec_end_date = ?::date where {sk} = ?', [day, r[0]])
            n[cols.index(sk)] = nxt; nxt += 1
            n[cols.index(f'{hist}_rec_start_date')] = day + datetime.timedelta(days=1)
            n[cols.index(f'{hist}_rec_end_date')] = None
            news.append(n)
        else:
            sets = [c for i, c in enumerate(cols) if c not in fixed and n[i] != r[i]]
            if sets:
                con.execute(f"update {t} set {', '.join(f'{c} = ?' for c in sets)} where {sk} = ?",
                            [n[cols.index(c)] for c in sets] + [r[0]])
                upd += 1
    for k in range(max(1, int(RATE / 2 * len(rows)))):
        n = [rng.choice(pool[c]) for c in cols]
        n[cols.index(sk)] = nxt; nxt += 1
        if bk: n[cols.index(bk)] = f'X{rnd}{k:07d}'.ljust(16, 'A')[:16]
        if hist:
            n[cols.index(f'{hist}_rec_start_date')] = day + datetime.timedelta(days=1)
            n[cols.index(f'{hist}_rec_end_date')] = None
        news.append(n)
    if news:
        con.executemany(f"insert into {t} values ({', '.join('?' * len(cols))})", news)
    return dict(versions=len(chosen) if hist else 0, updated=upd, inserted=len(news) - (len(chosen) if hist else 0))


def main():
    work = sys.argv[1]
    db = os.path.join(work, 'x8_sf1.duckdb')
    shutil.copy(os.path.join(work, 'tpcds_sf1.duckdb'), db)
    con = duckdb.connect(db)
    M = json.load(open(os.path.join(HERE, 'mined.json')))
    rng = random.Random(8)
    day = datetime.date(2003, 1, 2)
    status = {(t, i): [] for t, ks in M.items() for i in range(len(ks))}
    log = []
    for rnd in range(1, ROUNDS + 1):
        t0 = time.time()
        ops = {t: refresh(con, t, rnd, rng, day) for t in DYNAMIC if t in M}
        day += datetime.timedelta(days=30)
        alive = Counter()
        for t, ks in M.items():
            for i, k in enumerate(ks):
                if status[(t, i)] and status[(t, i)][-1] is False:
                    status[(t, i)].append(False); continue          # broken keys stay broken
                ok = holds(con, t, k['K'], k['cls'], k['temps'])
                status[(t, i)].append(ok); alive[t] += ok
        log.append(dict(round=rnd, ops=ops, alive=dict(alive)))
        print(f'round {rnd}: ' + ', '.join(f"{t} {alive[t]}/{len(M[t])}" for t in M) + f' ({time.time() - t0:.0f}s)', flush=True)
    out = []
    for t, ks in M.items():
        n = con.execute(f'select count(*) from {t}').fetchone()[0]
        for i, k in enumerate(ks):
            out.append(dict(table=t, K=k['K'], cls=k['cls'], kind=k['kind'], stable_sf10=k.get('stable'),
                            maintained=t in DYNAMIC, temps=k['temps'], survived=status[(t, i)]))
    json.dump(dict(rate=RATE, rounds=ROUNDS, log=log, keys=out), open(os.path.join(HERE, 'x8_refresh.json'), 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
