"""Filtered unique indexes in public application schemas: count, classify conditions, and test
each unique index for redundancy (implied by the table's other unique indexes, primary key and
NOT NULL columns) with implication.py. Usage: python schemas_study.py SCHEMADIR REPO"""
import glob, json, os, re, sys
from collections import Counter, defaultdict
import sqlglot
from sqlglot import exp
sys.path.insert(0, os.path.join(sys.argv[2], 'experiments', 'reasoning'))
from implication import implies_sat


class Untr(Exception): pass


def strip(e):
    while isinstance(e, (exp.Cast, exp.Paren)): e = e.this
    return e


def col(e):
    e = strip(e)
    if isinstance(e, exp.Column): return e.name
    raise Untr(e.sql())


def lit(e):
    e = strip(e)
    if isinstance(e, exp.Literal): return e.this
    if isinstance(e, exp.Boolean): return str(e.this).lower()
    if isinstance(e, exp.Neg): return '-' + lit(e.this)
    raise Untr(e.sql())


def dnf(e):
    """-> list of templates {col: 'T' | 'N' | ('C', v)}"""
    e = strip(e)
    if isinstance(e, exp.Or): return dnf(e.this) + dnf(e.expression)
    if isinstance(e, exp.And):
        out = []
        for a in dnf(e.this):
            for b in dnf(e.expression):
                m, ok = dict(a), True
                for c, s in b.items():
                    if c not in m: m[c] = s
                    elif m[c] == s: pass
                    elif m[c] == 'T' and s != 'N': m[c] = s
                    elif s == 'T' and m[c] != 'N': pass
                    else: ok = False
                if ok: out.append(m)
        return out
    if isinstance(e, exp.Column): return [{e.name: ('C', 'true')}]
    if isinstance(e, exp.Not):
        x = strip(e.this)
        if isinstance(x, exp.Is):
            r = strip(x.expression)
            if isinstance(r, exp.Null): return [{col(x.this): 'T'}]
            if isinstance(r, exp.Boolean):                      # IS NOT TRUE: false or null
                other = 'false' if r.this else 'true'
                return [{col(x.this): ('C', other)}, {col(x.this): 'N'}]
        if isinstance(x, exp.Column): return [{x.name: ('C', 'false')}]
        raise Untr(e.sql())
    if isinstance(e, exp.Is):
        r = strip(e.expression)
        if isinstance(r, exp.Null): return [{col(e.this): 'N'}]
        if isinstance(r, exp.Boolean): return [{col(e.this): ('C', str(r.this).lower())}]
        raise Untr(e.sql())
    if isinstance(e, exp.EQ):
        r = strip(e.expression)
        if isinstance(r, exp.Any):
            arr = strip(r.this)
            if not isinstance(arr, exp.Array): raise Untr(e.sql())
            return [{col(e.this): ('C', lit(v))} for v in arr.expressions]
        try: return [{col(e.this): ('C', lit(r))}]
        except Untr: return [{col(r): ('C', lit(e.this))}]
    if isinstance(e, exp.In): return [{col(e.this): ('C', lit(v))} for v in e.expressions]
    raise Untr(e.sql())


def parse_rb(path):
    T = defaultdict(lambda: dict(cols=set(), nn=set(), idx=[]))
    cur = None
    for line in open(path):
        m = re.match(r'\s*create_table "([^"]+)"(.*)', line)
        if m:
            cur = m.group(1); t = T[cur]
            if 'id: false' not in m.group(2):
                pk = re.search(r'primary_key: (\[[^\]]*\]|"[^"]+")', m.group(2))
                K = json.loads(pk.group(1)) if pk else 'id'
                K = [K] if isinstance(K, str) else K
                t['cols'] |= set(K); t['nn'] |= set(K); t['idx'].append(dict(K=K, where=None, nnd=False, pk=True, sql='PK'))
            continue
        if cur is None: continue
        m = re.match(r'\s*t\.(\w+) "([^"]+)"(.*)', line)
        if m and m.group(1) != 'index':
            T[cur]['cols'].add(m.group(2))
            if 'null: false' in m.group(3): T[cur]['nn'].add(m.group(2))
            continue
        if re.match(r'\s*t\.timestamps', line):
            T[cur]['cols'] |= {'created_at', 'updated_at'}
            if 'null: false' in line: T[cur]['nn'] |= {'created_at', 'updated_at'}
        m = re.match(r'\s*t\.index (\[[^\]]*\]|"[^"]*")(.*)', line)
        if m and 'unique: true' in m.group(2):
            K = json.loads(m.group(1)) if m.group(1).startswith('[') else [m.group(1).strip('"')]
            w = re.search(r'where: "((?:[^"\\]|\\.)*)"', m.group(2))
            T[cur]['idx'].append(dict(K=K, where=w.group(1).replace('\\"', '"') if w else None,
                                      nnd='nulls_not_distinct: true' in m.group(2), pk=False, sql=line.strip()))
        if line.strip() == 'end': cur = None
    return T


def parse_sql(path):
    T = defaultdict(lambda: dict(cols=set(), nn=set(), idx=[]))
    txt = open(path).read()
    for m in re.finditer(r'CREATE TABLE (?:public\.)?(\w+) \((.*?)\n\)', txt, re.S):
        t = T[m.group(1)]
        for l in m.group(2).split('\n'):
            c = re.match(r'\s+(\w+) ', l)
            if c and not l.strip().startswith('CONSTRAINT'):
                t['cols'].add(c.group(1))
                if 'NOT NULL' in l: t['nn'].add(c.group(1))
    for m in re.finditer(r'ALTER TABLE ONLY (?:public\.)?(\w+)\s+ADD CONSTRAINT \w+ (PRIMARY KEY|UNIQUE) \(([^)]*)\);', txt):
        K = [c.strip() for c in m.group(3).split(',')]
        if m.group(1) in T:
            T[m.group(1)]['idx'].append(dict(K=K, where=None, nnd=False, pk=m.group(2) == 'PRIMARY KEY', sql=m.group(0)))
            if m.group(2) == 'PRIMARY KEY': T[m.group(1)]['nn'] |= set(K)
    for m in re.finditer(r'CREATE UNIQUE INDEX \w+ ON (ONLY )?(?:public\.)?(\w+(?:\.\w+)?) USING \w+ \((.*?)\)( INCLUDE \([^)]*\))?( NULLS NOT DISTINCT)?( WHERE (.*))?;\n', txt):
        if '.' in m.group(2): continue                                # partitions repeat their parent's index
        K = [c.strip() for c in re.split(r',(?![^(]*\))', m.group(3))]
        if m.group(2) in T:
            T[m.group(2)]['idx'].append(dict(K=K, where=m.group(7), nnd=bool(m.group(5)), pk=False, sql=m.group(0).strip()))
    return T


def shape(K, temps):
    if temps is None: return 'untranslatable'
    if len(temps) > 1: return 'disjunctive (IN/OR)'
    t = temps[0]
    kinds = set()
    for c, s in t.items():
        if s == 'T': kinds.add('notnull-key' if c in K else 'notnull-other')
        elif s == 'N': kinds.add('null-key' if c in K else 'null-other')
        else: kinds.add('constant')
    if kinds == {'notnull-key'}: return 'IS NOT NULL on key only'
    if kinds == {'null-other'}: return 'IS NULL on other column'
    if kinds == {'notnull-other'}: return 'IS NOT NULL on other column'
    if kinds == {'constant'}: return 'constant / boolean'
    return 'conjunction of several kinds'


def main():
    D = sys.argv[1]
    report = {}
    for f in sorted(glob.glob(os.path.join(D, '*'))):
        app = os.path.basename(f).split('.')[0]
        T = parse_sql(f) if f.endswith('.sql') else parse_rb(f)
        S = Counter(); red = Counter(); examples = []
        n_unique = n_filtered = n_tables_f = n_multi_tables = 0
        for tname, t in T.items():
            idx = t['idx']
            conv = []
            for ix in idx:
                exprkey = any(not re.fullmatch(r'"?\w+"?', k) for k in ix['K'])
                K = [k.strip('"') for k in ix['K']]
                try:
                    temps = [{}] if not ix['where'] else dnf(sqlglot.parse_one(ix['where'], read='postgres'))
                except (Untr, sqlglot.errors.ParseError, sqlglot.errors.TokenError):
                    temps = None
                conv.append((ix, K, temps, exprkey))
            nf = sum(1 for ix in idx if ix['where'])
            n_unique += sum(1 for ix in idx if not ix['pk']); n_filtered += nf
            n_tables_f += nf > 0
            n_multi_tables += nf > 1
            for ix, K, temps, ek in conv:
                if ix['where']: S[shape(K, temps)] += 1
            # redundancy: is an index implied by the table's other (translatable) unique indexes?
            for i, (ix, K, temps, ek) in enumerate(conv):
                if ix['pk'] or temps is None or ek: continue
                others = [(tp, 'dom' if o['nnd'] else 'pos', k) for j, (o, k, tp, ek2) in enumerate(conv)
                          if j != i and tp is not None and not ek2]
                if not others: continue
                cols = sorted(set(K) | {c for tp in [temps] + [o[0] for o in others] for d in tp for c in d}
                              | {c for o in others for c in o[2]})
                enc = {}
                def tpl(d):
                    out = {c: '_' for c in cols}
                    for c, s in d.items(): out[c] = enc.setdefault((c, s[1]), len(enc) + 1) if isinstance(s, tuple) else s
                    return out
                NN = set(c for c in cols if c in t['nn'])
                Sig = [([tpl(d) for d in tp], cl, frozenset(k)) for tp, cl, k in others]
                phi = ([tpl(d) for d in temps], 'dom' if ix['nnd'] else 'pos', frozenset(K))
                if implies_sat(cols, NN, Sig, phi):
                    single = any(implies_sat(cols, NN, [s], phi) for s in Sig)
                    kind = ('filtered' if ix['where'] else 'unconditional') + (', by one index' if single else ', only by several')
                    red[kind] += 1
                    examples.append(dict(table=tname, index=ix['sql'][:300], kind=kind))
        report[app] = dict(tables=len(T), unique=n_unique, filtered=n_filtered, tables_with_filtered=n_tables_f,
                           tables_with_several_filtered=n_multi_tables, shapes=dict(S), redundant=dict(red), examples=examples)
        print(f"{app:16s} tables={len(T):5d} unique={n_unique:5d} filtered={n_filtered:4d} "
              f"tables_with_filtered={n_tables_f:4d} (>=2: {n_multi_tables}) redundant={dict(red)}")
        print('     shapes:', dict(S))
    json.dump(report, open(os.path.join(os.path.dirname(D.rstrip('/')), 'schemas_study.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
