"""Real consumer queries over the Stack Exchange data: the SEDE corpus (Hazoom et al., NLP4Prog
2021; queries users wrote in the Stack Exchange Data Explorer, T-SQL), planned against the
stats.stackexchange.com data loaded by se_load.py, with enable_conditional_unique off and on.

Preparation per query (train, val_original, test_original; duplicates by normalised text dropped):
  parameters  ##Name## / ##Name:type## / ##Name:type?default## -> the default, else 1 or 'a';
              DECLARE @v type = expr -> every @v replaced by expr; other @v -> 1;
  skipped     anything but one read-only SELECT (control flow, temporary tables, writes);
  translated  sqlglot, tsql -> postgres (TOP -> LIMIT, [names], ...).
Then EXPLAIN (no ANALYZE) off and on in a read-only transaction, as in X11: changed, removed
joins, Inner Unique, GROUP BY shortened, DISTINCT removed, the prover's DEBUG1 proofs, and the
filtered indexes of the catalog the query names. Writes OUT (default se_workload.json).
Usage: python se_workload.py SEDE_DATA_DIR DSN [OUT]"""
import json, os, re, sys
from collections import Counter
import psycopg, sqlglot
HERE = os.path.dirname(os.path.abspath(__file__))
NOTICES = []
WRITE = re.compile(r'\b(insert|update|delete|truncate|drop|alter|create|exec|execute|while|if|begin|goto|merge|into)\b', re.I)


def prepare(body):
    body = re.sub(r'--[^\n]*', ' ', body)
    body = re.sub(r'/\*.*?\*/', ' ', body, flags=re.S)
    def param(m):
        name, typ, dflt = m.group(1), (m.group(2) or '').lower(), m.group(3)
        if dflt is not None:
            return dflt if re.fullmatch(r"-?[\d.]+|'.*'", dflt) else "'" + dflt.replace("'", "''") + "'"
        return "'a'" if typ.startswith('string') or typ == 'str' else '1'
    body = re.sub(r'##(\w+)(?::(\w+))?(?:\?([^#]*))?##', param, body)
    decl = {}
    for m in re.finditer(r'\bdeclare\s+@(\w+)\s+[\w()]+(?:\s*=\s*([^;\n]+))?', body, re.I):
        decl[m.group(1).lower()] = (m.group(2) or '1').strip()
    body = re.sub(r'\bdeclare\s+@\w+\s+[\w()]+(?:\s*=\s*[^;\n]+)?;?', ' ', body, flags=re.I)
    body = re.sub(r'\bset\s+@\w+\s*=\s*[^;\n]+;?', ' ', body, flags=re.I)
    body = re.sub(r'@(\w+)', lambda m: decl.get(m.group(1).lower(), '1'), body)
    body = body.strip().rstrip(';').strip()
    if ';' in body or '#' in body or WRITE.search(re.sub(r"'[^']*'", "''", body)) or \
            not re.match(r'(select|with)\b', body, re.I):
        return None
    try:
        out = sqlglot.transpile(body, read='tsql', write='postgres')
    except Exception:
        return None
    return out[0] if len(out) == 1 else None


def plan(cur, sql, on, verbose=False):
    cur.execute(f"set enable_conditional_unique = {'on' if on else 'off'}")
    cur.execute(f"explain ({'verbose, ' if verbose else ''}costs off) " + sql)
    return [r[0] for r in cur.fetchall()]


def joins(p): return sum(bool(re.search(r'\b(Join|Nested Loop)\b', l)) for l in p)
def gkeys(p): return [l for l in p if 'Group Key' in l]
def aggs(p): return sum(bool(re.search(r'(Unique|HashAggregate|GroupAggregate)\b', l)) for l in p)


def main():
    src, dsn = sys.argv[1], sys.argv[2]
    out_name = sys.argv[3] if len(sys.argv) > 3 else 'se_workload.json'
    raw = []
    for f in ('train.jsonl', 'val_original.jsonl', 'test_original.jsonl'):
        raw += [json.loads(l) for l in open(os.path.join(src, f))]
    con = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
    con.add_notice_handler(lambda d: NOTICES.append(d.message_primary))
    cur = con.cursor()
    cur.execute('set statement_timeout = 10000')
    cur.execute("""select c.relname, pg_get_expr(x.indpred, x.indrelid) from pg_index x
                   join pg_class c on c.oid = x.indrelid join pg_namespace n on n.oid = c.relnamespace
                   where n.nspname = 'public' and x.indisunique and x.indpred is not null""")
    fidx = cur.fetchall()
    seen, res, st = set(), [], Counter()
    for q in raw:
        st['corpus'] += 1
        sql = prepare(q['QueryBody'])
        if sql is None: st['not a single read-only SELECT, or untranslatable'] += 1; continue
        key = re.sub(r'\s+', ' ', sql.lower())
        if key in seen: st['duplicate'] += 1; continue
        seen.add(key)
        low = sql.lower()
        names = sorted({t for t, p in fidx if re.search(rf'\b{t}\b', low) and
                        all(re.search(rf'\b{c}\b', low) for c in set(re.findall(r'\b([a-z_]+)\b', p)) -
                            {'and', 'or', 'not', 'is', 'null', 'true', 'false', 'text', 'bigint', 'boolean'})})
        r = dict(id=q['QuerySetId'], title=q['Title'], sql=sql, names_filtered=names)
        try:
            cur.execute('begin read only')
            off, on = plan(cur, sql, False), plan(cur, sql, True)
            voff = plan(cur, sql, False, True)
            cur.execute('set client_min_messages = debug1'); NOTICES.clear()
            von = plan(cur, sql, True, True)
            cur.execute('reset client_min_messages'); cur.execute('commit')
        except psycopg.Error as ex:
            cur.execute('rollback')
            r['error'] = f'{type(ex).__name__}: {str(ex).splitlines()[0][:140]}'
            st['does not plan'] += 1; res.append(r); continue
        st['planned'] += 1
        r.update(proofs=sum('conditional unique: implied' in m for m in NOTICES), changed=off != on,
                 removed=joins(on) < joins(off), groupby=gkeys(on) != gkeys(off), distinct=aggs(on) < aggs(off),
                 unique=sum('Inner Unique: true' in l for l in von) > sum('Inner Unique: true' in l for l in voff),
                 plan_off=off, plan_on=on)
        for k in ('proofs', 'changed', 'removed', 'groupby', 'distinct', 'unique'):
            if r[k]: st[k] += 1
        if names: st['names a table with a filtered index and its predicate columns'] += 1
        res.append(r)
    print(json.dumps(st, indent=1, sort_keys=True))
    json.dump(res, open(os.path.join(HERE, out_name), 'w'), indent=1)


if __name__ == '__main__':
    main()
