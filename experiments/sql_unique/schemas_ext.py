"""The filtered unique indexes of the application schemas in the extended template language
(cunique.py: IN and NOT IN / <> entries). Reports how many predicates translate, their shapes,
and, taking every unique index of a table in turn as the goal (scope = its predicate) with the
table's other unique indexes as premises, how many columns have more than one maximal state
(0 = decided by one canonical pair) and the decision time. Writes schemas_ext.json.
Usage: python schemas_ext.py SCHEMADIR REPO"""
import glob, json, os, re, sys, time
from collections import Counter
import sqlglot
from sqlglot import exp
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv += [] if len(sys.argv) > 2 else ['']
from schemas_study import parse_sql, parse_rb, strip, col, lit, Untr
from cunique import implies


def conj(a, b):
    """conjunction of two entries, or None if contradictory"""
    if a[0] == 'any': return b
    if b[0] == 'any': return a
    if a[0] == 'null' or b[0] == 'null': return a if a == b else None
    if a[0] == 'top': return b
    if b[0] == 'top': return a
    if a[0] == 'in' and b[0] == 'in': return ('in', a[1] & b[1]) if a[1] & b[1] else None
    if a[0] == 'notin' and b[0] == 'notin': return ('notin', a[1] | b[1])
    i, n = (a, b) if a[0] == 'in' else (b, a)
    return ('in', i[1] - n[1]) if i[1] - n[1] else None


def dnf(e):
    """-> list of templates {col: entry}"""
    e = strip(e)
    if isinstance(e, exp.Or): return dnf(e.this) + dnf(e.expression)
    if isinstance(e, exp.And):
        out = []
        for a in dnf(e.this):
            for b in dnf(e.expression):
                m, ok = dict(a), True
                for c, s in b.items():
                    m[c] = conj(m.get(c, ('any',)), s)
                    if m[c] is None: ok = False; break
                if ok: out.append(m)
        return out
    if isinstance(e, exp.Column): return [{e.name: ('in', frozenset(['true']))}]
    if isinstance(e, exp.Not):
        x = strip(e.this)
        if isinstance(x, exp.Is):
            r = strip(x.expression)
            if isinstance(r, exp.Null): return [{col(x.this): ('top',)}]
            if isinstance(r, exp.Boolean):
                return [{col(x.this): ('notin', frozenset([str(r.this).lower()]))}, {col(x.this): ('null',)}]
        if isinstance(x, exp.Column): return [{x.name: ('in', frozenset(['false']))}]
        if isinstance(x, exp.In): return [{col(x.this): ('notin', frozenset(lit(v) for v in x.expressions))}]
        raise Untr(e.sql())
    if isinstance(e, exp.Is):
        r = strip(e.expression)
        if isinstance(r, exp.Null): return [{col(e.this): ('null',)}]
        if isinstance(r, exp.Boolean): return [{col(e.this): ('in', frozenset([str(r.this).lower()]))}]
        raise Untr(e.sql())
    if isinstance(e, (exp.EQ, exp.NEQ)):
        kind = 'in' if isinstance(e, exp.EQ) else 'notin'
        r = strip(e.expression)
        if isinstance(r, exp.Any):
            arr = strip(r.this)
            if not isinstance(arr, exp.Array) or kind == 'notin': raise Untr(e.sql())
            return [{col(e.this): ('in', frozenset(lit(v) for v in arr.expressions))}]
        try: return [{col(e.this): (kind, frozenset([lit(r)]))}]
        except Untr: return [{col(r): (kind, frozenset([lit(e.this)]))}]
    if isinstance(e, exp.In): return [{col(e.this): ('in', frozenset(lit(v) for v in e.expressions))}]
    raise Untr(e.sql())


def shape(K, temps):
    if temps is None: return 'untranslatable'
    if len(temps) > 1: return 'disjunctive'
    kinds = set()
    for c, s in temps[0].items():
        if s[0] == 'top': kinds.add('notnull-key' if c in K else 'notnull-other')
        elif s[0] == 'null': kinds.add('null-other')
        elif s[0] == 'notin': kinds.add('not-equal')
        else: kinds.add('in-list' if len(s[1]) > 1 else 'constant')
    return '+'.join(sorted(kinds))


def main():
    D = sys.argv[1]
    shapes = Counter(); tr = Counter(); opens = Counter(); times = []; ne_tables = []
    for f in sorted(glob.glob(os.path.join(D, '*'))):
        T = parse_sql(f) if f.endswith('.sql') else parse_rb(f)
        for tname, t in T.items():
            conv = []
            for ix in t['idx']:
                if any(not re.fullmatch(r'"?\w+"?', k) for k in ix['K']): conv.append(None); continue
                K = frozenset(k.strip('"') for k in ix['K'])
                try: temps = [{}] if not ix['where'] else dnf(sqlglot.parse_one(ix['where'], read='postgres'))
                except (Untr, sqlglot.errors.ParseError, sqlglot.errors.TokenError): temps = None
                if ix['where']:
                    tr['filtered'] += 1; tr['translated'] += temps is not None
                    shapes[shape(K, temps)] += 1
                conv.append(None if temps is None else (temps, 'Ueq' if ix['nnd'] else 'U', K))
            if not any(c and any(e[0] == 'notin' for r in c[0] for e in r.values()) for c in conv): has_ne = False
            else: has_ne = True; ne_tables.append(f'{os.path.basename(f).split(".")[0]}.{tname}')
            cols = sorted(set(t['cols']) | {A for c in conv if c for r in c[0] for A in r} | {A for c in conv if c for A in c[2]})
            full = lambda c: ([{A: r.get(A, ('any',)) for A in cols} for r in c[0]], c[1], c[2])
            convf = [full(c) if c else None for c in conv]
            for i, phi in enumerate(convf):
                if phi is None or t['idx'][i]['pk']: continue
                Sig = [s for j, s in enumerate(convf) if j != i and s is not None]
                for sem in ('U', 'Ueq'):                       # join-shaped and group-shaped goal
                    st = {}; t0 = time.perf_counter()
                    implies(cols, set(t['nn']) & set(cols), Sig, (phi[0], sem, phi[2]), st)
                    times.append((time.perf_counter() - t0) * 1e3)
                    opens[(sem, has_ne, min(st.get('open', 0), 3))] += 1
    times.sort()
    out = dict(translated=dict(tr), shapes=dict(shapes), tables_with_not_equal=ne_tables,
               open_columns={f'{k[0]} ne={k[1]} open={k[2]}': v for k, v in sorted(opens.items())},
               ms_median=times[len(times) // 2], ms_p99=times[int(len(times) * .99)], ms_max=times[-1], goals=len(times))
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(HERE, 'schemas_ext.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
