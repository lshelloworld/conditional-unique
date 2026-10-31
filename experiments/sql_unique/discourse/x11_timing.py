"""X11, run times: the Data Explorer reports for which the prover proves a uniqueness or the plan
changes (x11_workload.json), timed with enable_conditional_unique off and on.

Data, for N users: every table the affected reports read is filled once, ON CONFLICT DO NOTHING
so that all unique indexes hold. Values by type as in X5 (../apps/x5_timing.py), with *_id columns
drawn from the size of the table they refer to; the core tables have Discourse-like shapes and
sizes (CORE: 2N topics with 5 posts each and 5% soft-deleted, 10N posts with 3% soft-deleted, 20
daily visits per user, likes as 80% of post actions, custom fields with the names the filtered
indexes mention). Two tables carry the filtered key under test:
  users        ids 1..N;
  user_emails  one primary address per user and 0--2 secondary ones (about 2N rows), so that
               UNIQUE (user_id, primary) WHERE primary holds and the scope excludes a third of
               the rows, as on a site where users add addresses.
Foreign keys and CHECK constraints of these tables are dropped first. Results are compared by
same_result: both settings in one transaction, trailing LIMIT removed (ties). Reports over 1 ms
are re-timed by alternating(): 11 rounds alternating off and on, first dropped. The reports are untrusted
text: they run in a read-only session (default_transaction_read_only). Per report: median of
five EXPLAIN ANALYZE runs after two warm-ups per setting, and the result multisets compared.
Writes X11_TIMING_OUT (default x11_timing.json). Usage: python x11_timing.py DSN N"""
import json, os, re, statistics, sys
from collections import Counter
import psycopg
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'apps'))
from x5_timing import tables, expr, timed


SIZES = {'users': 1.0, 'topics': 2.0, 'posts': 10.0, 'categories': 0.0005, 'groups': 0.001, 'tags': 0.01,
         'chat_channels': 0.01, 'polls': 0.01, 'invites': 0.1}             # rows per user
REF = {'user_id': 'users', 'acting_user_id': 'users', 'target_user_id': 'users', 'granted_by_id': 'users',
       'topic_id': 'topics', 'post_id': 'posts', 'category_id': 'categories', 'parent_category_id': 'categories',
       'group_id': 'groups', 'tag_id': 'tags', 'chat_channel_id': 'chat_channels', 'poll_id': 'polls',
       'invite_id': 'invites'}
CORE = {   # table: (rows per user, {column: expression over i (1..rows) and n (users)})
    'categories': (0.0005, {'id': 'i', 'name': "'c' || i", 'slug': "'c' || i", 'name_lower': "'c' || i",
                            'parent_category_id': 'CASE WHEN i > 40 THEN 1 + i % 10 END', 'read_restricted': 'false'}),
    'groups': (0.001, {'id': 'i', 'name': "'g' || i"}),
    'tags': (0.01, {'id': 'i', 'name': "'t' || i"}),
    'topics': (2.0, {'id': 'i', 'category_id': '1 + (random() * 49)::int', 'title': "'topic ' || i",
                     'deleted_at': "CASE WHEN random() < 0.05 THEN now() - random() * interval '300 days' END",
                     'archetype': "CASE WHEN random() < 0.1 THEN 'private_message' ELSE 'regular' END",
                     'posts_count': '5', 'visible': 'true', 'closed': 'random() < 0.2', 'external_id': 'NULL'}),
    'posts': (10.0, {'id': 'i', 'topic_id': '1 + (i - 1) / 5', 'post_number': '1 + (i - 1) % 5', 'post_type': '1',
                     'deleted_at': "CASE WHEN random() < 0.03 THEN now() - random() * interval '300 days' END",
                     'like_count': '(random() * 5)::int', 'raw': "'post'", 'cooked': "'post'"}),
    'user_visits': (20.0, {'user_id': '1 + (i - 1) % n', 'visited_at': 'current_date - ((i - 1) / n)::int',
                           'posts_read': '(random() * 20)::int'}),
    'post_actions': (5.0, {'post_action_type_id': "CASE WHEN random() < 0.8 THEN 2 ELSE 1 + (random() * 7)::int END",
                           'deleted_at': "CASE WHEN random() < 0.05 THEN now() END",
                           'disagreed_at': "CASE WHEN random() < 0.01 THEN now() END",
                           'deferred_at': "CASE WHEN random() < 0.01 THEN now() END"}),
    'topic_custom_fields': (1.0, {'name': "(ARRAY['accepted_answer_post_id', 'vote_count', 'assigned_to_id', "
                                          "'event_starts_at', 'other'])[1 + (random() * 4)::int]",
                                  'value': '(random() * 1000)::int::text'}),
    'category_users': (0.5, {'category_id': '1 + (random() * 49)::int', 'notification_level': '(random() * 4)::int'}),
    'group_users': (3.0, {'group_id': '1 + (random() * 99)::int'}),
}


def expr2(name, typ, nullable, enum_first, n):
    if name in REF: return f"1 + (random() * {max(1, int(n * SIZES.get(REF[name], 1.0)) - 1)})::int"
    if typ.startswith('timestamp') or typ == 'date':
        return "now() - random() * interval '1000 days'" if not nullable else "CASE WHEN random() < 0.5 THEN NULL ELSE now() - random() * interval '1000 days' END"
    return expr(name, typ, nullable, enum_first, n, set())


def fill2(cur, table, n):
    per, over = CORE.get(table, (1.0, {}))
    rows = max(1, int(n * per))
    cur.execute("""select c.column_name, c.data_type, c.is_nullable = 'YES', c.column_default is not null,
                          (select e.enumlabel from pg_enum e join pg_type t on t.oid = e.enumtypid
                           where t.typname = c.udt_name order by e.enumsortorder limit 1)
                   from information_schema.columns c where c.table_schema = 'public' and c.table_name = %s
                   order by c.ordinal_position""", (table,))
    cols, exprs = [], []
    for name, typ, nullable, has_default, enum_first in cur.fetchall():
        if name in over: e = over[name]
        elif has_default: continue
        else: e = expr2(name, typ, nullable, enum_first, n)
        if e is None: continue
        cols.append(f'"{name}"'); exprs.append(e.replace(' n)', f' {n})').replace('% n', f'% {n}').replace('/ n)', f'/ {n})'))
    cur.execute(f'truncate public."{table}" cascade')
    cur.execute(f'insert into public."{table}" ({", ".join(cols)}) select {", ".join(exprs)} '
                f'from generate_series(1, {rows}) i on conflict do nothing')
    cur.execute(f'analyze public."{table}"')
    cur.execute(f'select count(*) from public."{table}"')
    return cur.fetchone()[0]


def users_and_emails(cur, n):
    cur.execute('truncate users, user_emails cascade')
    cur.execute(f"""insert into users (id, username, username_lower, created_at, updated_at, trust_level,
                       active, admin, moderator, approved, staged)
                    select i, 'u' || i, 'u' || i, now() - random() * interval '1000 days', now(),
                           (random() * 4)::int, true, false, false, true, false
                    from generate_series(1, {n}) i""")
    cur.execute(f"""insert into user_emails (user_id, email, "primary", created_at, updated_at)
                    select u, 'u' || u || '-' || k || '@example.org', k = 0, now(), now()
                    from generate_series(1, {n}) u, generate_series(0, 2) k
                    where k = 0 or random() < 0.5""")
    cur.execute('analyze users'); cur.execute('analyze user_emails')


def same_result(cur, sql):
    """results with the setting off and on, in one transaction (CURRENT_TIMESTAMP fixed) and
    without a trailing LIMIT (which may pick different rows among ties); the multisets compared"""
    q = re.sub(r'\bLIMIT\s+\d+\s*$', '', sql.strip(), flags=re.I)
    cur.execute('begin read only')
    try:
        cur.execute('set local enable_conditional_unique = off'); cur.execute(q); a = Counter(map(tuple, cur.fetchall()))
        cur.execute('set local enable_conditional_unique = on'); cur.execute(q); b = Counter(map(tuple, cur.fetchall()))
    finally:
        cur.execute('rollback')
    return a == b, sum(a.values())


def alternating(cur, sql, rounds=11):
    """medians of EXPLAIN ANALYZE (TIMING OFF) over rounds alternating off and on, the first
    round dropped as warm-up: less sensitive to drift than five runs per setting"""
    ms = {'off': [], 'on': []}
    for _ in range(rounds):
        for v in ('off', 'on'):
            cur.execute(f'set enable_conditional_unique = {v}')
            cur.execute('explain (analyze, timing off, format json) ' + sql)
            ms[v].append(cur.fetchone()[0][0]['Execution Time'])
    return statistics.median(ms['off'][1:]), statistics.median(ms['on'][1:])


def main():
    dsn, n = sys.argv[1], int(sys.argv[2])
    W = [x for x in json.load(open(os.path.join(HERE, 'x11_workload.json')))
         if 'error' not in x and (x.get('changed') or x.get('proofs'))]
    con = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
    cur = con.cursor()
    cur.execute('set max_parallel_workers_per_gather = 0'); cur.execute("set statement_timeout = '300s'")
    need = set()
    for x in W: need |= tables(cur, x['sql_planned'])
    for s, t in sorted(need):
        cur.execute("select conname from pg_constraint where conrelid = %s::regclass and contype in ('f', 'c')", (f'{s}."{t}"',))
        for (c,) in cur.fetchall(): cur.execute(f'alter table {s}."{t}" drop constraint "{c}"')
    rows = {}
    for s, t in sorted(need):
        if t not in ('users', 'user_emails'): rows[t] = fill2(cur, t, n)
    users_and_emails(cur, n)
    for t in ('users', 'user_emails'):
        cur.execute(f'select count(*) from {t}'); rows[t] = cur.fetchone()[0]
    print('rows:', rows, flush=True)
    cur.execute('set default_transaction_read_only = on')
    out = []
    for x in W:
        sql = x['sql_planned']
        r = dict(origin=x['origin'], title=x.get('title'), touches=x['touches'], sql=sql)
        try:
            r['off_ms'], r['plan_off'], a = timed(cur, sql, False)
            r['on_ms'], r['plan_on'], b = timed(cur, sql, True)
            if r['off_ms'] >= 1:
                r['off_alt_ms'], r['on_alt_ms'] = alternating(cur, sql)
                r['speedup_alt'] = r['off_alt_ms'] / r['on_alt_ms']
            r['same_as_timed'] = a == b
            r['same_result'], r['result_rows'] = same_result(cur, sql)
            r['plan_changed'] = r['plan_off'] != r['plan_on']
            r['speedup'] = r['off_ms'] / r['on_ms'] if r['on_ms'] else None
            print(f"{x['origin'][-40:]:40s} rows {r['result_rows']:7d}  off {r['off_ms']:9.1f} ms  on {r['on_ms']:9.1f} ms  "
                  f"{r['speedup']:5.2f}x  plan changed {r['plan_changed']}  same {r['same_result']}", flush=True)
        except psycopg.Error as ex:
            r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0][:150]}'
            print(f"{x['origin'][-40:]:40s} ERROR {r['error'][:90]}", flush=True)
        out.append(r)
    json.dump(dict(n=n, rows=rows, queries=out), open(os.path.join(HERE, os.environ.get('X11_TIMING_OUT', 'x11_timing.json')), 'w'), indent=1)


if __name__ == '__main__':
    main()
