"""X11: what Discourse's filtered unique indexes do for real Data Explorer reports.

Input: queries_raw.json (collect.py) and the Discourse schema loaded as database x11_discourse
(load_schema.py) on the patched server. Per query:
  prepare   Data Explorer parameters (-- [params] / -- int :name = default) are replaced by typed
            literals, the default if given, else a neutral value of the type; queries that are
            not SELECT / WITH ... SELECT are skipped (the posts also contain UPDATEs, rake
            tasks and Rails code), as are whole blocks with a writing statement; a block that
            lists several queries without semicolons is split at blank lines before SELECT/WITH; duplicates (same text up to case and whitespace) are
            dropped, the first origin kept.
  plan      EXPLAIN (no ANALYZE: nothing is executed) with enable_conditional_unique off and on,
            in a read-only transaction; as in X5: changed, removed (fewer joins), unique (new
            Inner Unique), groupby (shorter key), distinct (Unique/HashAggregate for DISTINCT
            gone), proofs (the prover's DEBUG1 'implied' messages).
  touches   the query reads a table with a filtered unique index and names its predicate column.
Writes x11_workload.json. Usage: python x11_workload.py DSN"""
import json, os, re, sys
from collections import Counter
import psycopg, sqlglot
HERE = os.path.dirname(os.path.abspath(__file__))
NOTICES = []

DEFAULTS = {'int': '1', 'integer': '1', 'bigint': '1', 'double': '1.0', 'boolean': 'true',
            'null boolean': 'true', 'string': "'a'", 'text': "'a'", 'date': "'2026-01-01'::date",
            'time': "'12:00'::time", 'datetime': "'2026-01-01'::timestamp",
            'user_id': '1', 'post_id': '1', 'topic_id': '1', 'category_id': '1', 'group_id': '1',
            'badge_id': '1', 'tag_id': '1', 'int_list': '1', 'string_list': "'a'", 'user_list': '1',
            'group_list': "'a'", 'category_list': '1', 'username': "'a'", 'group': "'a'",
            'current_user_id': '1', 'backfill': 'true', 'user_ids': '1', 'post_ids': '1'}   # badge queries
WRITE = re.compile(r'\b(insert|update|delete|truncate|drop|alter|create|grant|copy|call|do)\b', re.I)


def literal(typ, default):
    typ = re.sub(r'^null\s+', '', typ.lower().strip())
    if default is None or default.strip() == '': return DEFAULTS.get(typ, "'a'")
    d = default.strip()
    if typ in ('string', 'text', 'username', 'group', 'string_list', 'group_list') and not d.startswith("'"):
        return "'" + d.replace("'", "''") + "'"
    if typ in ('date', 'datetime', 'time'):
        return "'" + d.strip("'").replace("'", "''") + "'::" + {'date': 'date', 'time': 'time'}.get(typ, 'timestamp')
    if typ in ('boolean', 'null boolean'): return 'true' if d.lower() in ('true', 't', '1', '#true') else 'false'
    return d if re.fullmatch(r'-?[\d.]+(,\s*-?[\d.]+)*', d) else DEFAULTS.get(typ, "'a'")


def complete(text):
    """a whole statement: balanced parentheses and parsed by sqlglot"""
    t = re.sub(r"'[^']*'", "''", text)
    if t.count('(') != t.count(')'): return False
    try:
        sqlglot.parse_one(re.sub(r'(?<![:\w]):(\w+)', '1', text), read='postgres')
        return True
    except Exception:
        return False


def prepare(sql):
    """one or more SELECTs (blocks may list variants one after another, without semicolons)"""
    params = {}
    for m in re.finditer(r'^\s*--\s*([\w ]+?)\s*:(\w+)\s*(?:=\s*(.*?))?\s*$', sql, re.M):
        params[m.group(2)] = literal(m.group(1), m.group(3))
    body = re.sub(r'--[^\n]*', ' ', sql)                       # comments (params included)
    body = re.sub(r'/\*.*?\*/', ' ', body, flags=re.S)
    parts = []
    for stmt in body.split(';'):
        cur = ''
        for piece in re.split(r'\n\s*\n(?=\s*(?:select|with)\b)', stmt, flags=re.I):
            if cur and complete(cur): parts.append(cur.strip()); cur = piece
            else: cur = cur + '\n\n' + piece if cur else piece
        parts.append(cur.strip())
    out = []
    for b in parts:
        if not b or not re.match(r'(with|select|\()', b, re.I): continue
        if WRITE.search(re.sub(r"'[^']*'", "''", b)): return [], params
        out.append(re.sub(r'(?<![:\w]):(\w+)', lambda m: params.get(m.group(1), DEFAULTS.get(m.group(1), '1')), b))
    return out, params


def plan(cur, sql, on, verbose=False):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute(f"explain ({'verbose, ' if verbose else ''}costs off) " + sql)
    return [r[0].decode() if isinstance(r[0], bytes) else r[0] for r in cur.fetchall()]


def joins(p): return sum(bool(re.search(r'\b(Join|Nested Loop)\b', l)) for l in p)
def group_keys(p): return [l.split('Key:', 1)[1].strip() for l in p if re.search(r'Group Key:', l)]
def uniques(p): return sum(bool(re.search(r'->\s*(Unique|HashAggregate)|^\s*(Unique|HashAggregate)', l)) for l in p)


def filtered(cur):
    cur.execute("""select c.relname, i.relname, pg_get_expr(x.indpred, x.indrelid)
                   from pg_index x join pg_class i on i.oid = x.indexrelid join pg_class c on c.oid = x.indrelid
                   join pg_namespace n on n.oid = c.relnamespace
                   where n.nspname = 'public' and x.indisunique and x.indpred is not null""")
    out = {}
    for t, ix, p in cur.fetchall():
        t, ix, p = (x.decode() if isinstance(x, bytes) else x for x in (t, ix, p))   # SQL_ASCII clusters
        cols = set(re.findall(r'\b([a-z_]+)\b', p)) - {'and', 'or', 'not', 'is', 'null', 'true', 'false', 'any', 'array', 'text', 'integer'}
        out.setdefault(t, []).append((ix, p, cols))
    return out


def main():
    dsn = sys.argv[1]
    raw = json.load(open(os.path.join(HERE, 'queries_raw.json')))
    con = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
    con.add_notice_handler(lambda d: NOTICES.append(d.message_primary))
    cur = con.cursor()
    cur.execute("set search_path = public"); cur.execute('set statement_timeout = 10000')
    fidx = filtered(cur)
    seen, res, st = set(), [], Counter()
    for q in raw:
        st[f"blocks {q['source']}"] += 1
        sqls, params = prepare(q['sql'])
        if not sqls: st['blocks without a read-only SELECT'] += 1; continue
        if len(sqls) > 1: st['blocks with several SELECTs'] += 1
        for sql in sqls: one(q, sql, params, cur, fidx, seen, res, st)
    print(json.dumps(st, indent=1, sort_keys=True))
    json.dump(res, open(os.path.join(HERE, os.environ.get('X11_OUT', 'x11_workload.json')), 'w'), indent=1)


def one(q, sql, params, cur, fidx, seen, res, st):
    key = re.sub(r'\s+', ' ', sql.lower())
    if key in seen: st['duplicate'] += 1; return
    seen.add(key); st[f"queries {q['source']}"] += 1
    low = sql.lower()
    tabs = {t for t in fidx if re.search(rf'\b{t}\b', low)}
    touch = sorted({ix for t in tabs for ix, p, cols in fidx[t] if all(re.search(rf'\b{c}\b', low) for c in cols)})
    r = dict(q, sql_planned=sql, params=params, tables_with_filtered=sorted(tabs), touches=touch,
             has_left=bool(re.search(r'\bleft\s+(outer\s+)?join\b', low)),
             has_distinct=bool(re.search(r'\bdistinct\b', low)), has_group=bool(re.search(r'\bgroup\s+by\b', low)))
    try:
        cur.execute('begin read only')
        off, on = plan(cur, sql, False), plan(cur, sql, True)
        voff = plan(cur, sql, False, True)
        cur.execute('set client_min_messages = debug1'); NOTICES.clear()
        von = plan(cur, sql, True, True)
        cur.execute('reset client_min_messages')
        cur.execute('commit')
        r['proofs'] = sum('conditional unique: implied' in m for m in NOTICES)
    except psycopg.Error as ex:
        cur.execute('rollback')
        r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0][:150]}'
        st['does not plan'] += 1; res.append(r); return
    st['planned'] += 1
    if tabs: st['planned, reads a table with a filtered unique index'] += 1
    if touch: st['planned, names the predicate columns of one'] += 1
    r['changed'] = off != on
    r['removed'] = joins(on) < joins(off)
    r['unique'] = sum('Inner Unique: true' in l for l in von) > sum('Inner Unique: true' in l for l in voff)
    r['groupby'] = group_keys(on) != group_keys(off)
    r['distinct'] = uniques(on) < uniques(off)
    r['plan_off'], r['plan_on'] = off, on
    for k in ('proofs', 'changed', 'removed', 'unique', 'groupby', 'distinct'):
        if r[k]: st[k] += 1
    res.append(r)


if __name__ == '__main__':
    main()
