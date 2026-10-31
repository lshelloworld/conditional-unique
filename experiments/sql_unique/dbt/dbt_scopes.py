"""Static analysis of a dbt project: which left joins would filtered unique keys let a planner remove?

Read only: nothing in the project is executed. For a dbt project directory:
  1. Uniqueness the analysts assert, from the YAML properties: `unique` column tests and
     `dbt_utils.unique_combination_of_columns`, each with its `where:` scope if any (dbt runs the
     test on the rows matching it, i.e. it states C : U(K)). Scopes are classified as
       sample   test-cost filters: sampling flags, recent time windows (CURRENT_DATE/TIMESTAMP);
       semantic everything else (flags, status, versions, exclusions).
  2. The models' SQL after crude Jinja stripping ({{ ref('m') }} -> m, {{ source('s','t') }} ->
     s__t, {{ config() }} dropped, {{ dbt.type_*() }} -> varchar, other {{ }} -> a placeholder,
     {% %} and {# #} tags dropped), parsed with sqlglot.
  3. Every LEFT JOIN: its right relation is followed through simple CTEs (one FROM, no joins,
     aggregation or window) to a model, collecting the CTE WHERE conjuncts and the ON-clause
     conjuncts on the right side alone (the scope) and the right columns equated with the left
     side (the key). Classified as
       unconditional  an unconditional test has its key within the join key (a stock planner
                      with that key declared would know the right side unique);
       conditional    only a scoped test does, and every conjunct of its scope occurs in the join's
                      scope (the prover's case; textual match, so a lower bound);
       current        the scope selects current / undeleted rows (is_current, valid_to IS NULL, ...)
                      whether or not a test exists;
       dedup          the right CTE keeps one row per key (QUALIFY ROW_NUMBER() ... = 1);
     and whether the join is removable in shape: no column of the right side is used outside its
     ON clause (unqualified columns are matched against the right side's known output columns;
     if those are unknown and unqualified columns occur, the shape is 'unknown').
Writes dbt_scopes_<name>.json. Usage: python dbt_scopes.py NAME PROJECT_DIR DIALECT"""
import glob, json, os, re, sys
from collections import Counter
import yaml
import sqlglot
from sqlglot import exp

HERE = os.path.dirname(os.path.abspath(__file__))
CURRENT = re.compile(r'(is_current|_is_latest|is_latest|is_most_recent|valid_to\s+is\s+null|'
                     r'valid_until\s+is\s+null|end_date\s+is\s+null|deleted_at\s+is\s+null|'
                     r'is_deleted\s*(=\s*false|is\s+false)|not\s+\w*is_deleted|is_active)', re.I)
SAMPLE = re.compile(r'(sampled|current_date|current_timestamp|date_sub|timestamp_diff|'
                    r'interval|>=\s*timestamp\(|>=\s*date\()', re.I)


def norm(e):
    return re.sub(r'\s+', ' ', e.sql(dialect=DIALECT).lower()).replace('"', "'").replace('`', '')


def conjuncts(e):
    if e is None: return []
    e = e.unnest() if isinstance(e, exp.Paren) else e
    if isinstance(e, exp.And): return conjuncts(e.left) + conjuncts(e.right)
    return [e]


# ---------- 1. tests ----------
def tests(project):
    out = {}                                  # model -> [(frozenset cols, where or None)]
    def add(model, cols, where):
        out.setdefault(model, []).append((frozenset(c.lower() for c in cols), where))
    def where_of(t):
        if not isinstance(t, dict): return None
        for k in ('config', 'arguments'):
            w = (t.get(k) or {}).get('where') if isinstance(t.get(k), dict) else None
            if w: return str(w)
        return t.get('where')
    for f in glob.glob(os.path.join(project, 'models', '**', '*.yml'), recursive=True) + \
             glob.glob(os.path.join(project, 'models', '**', '*.yaml'), recursive=True):
        try: doc = yaml.safe_load(open(f))
        except Exception: continue
        for m in (doc or {}).get('models', []) or []:
            if not isinstance(m, dict) or 'name' not in m: continue
            for t in (m.get('data_tests') or m.get('tests') or []):
                if isinstance(t, dict):
                    for k, v in t.items():
                        if k.endswith('unique_combination_of_columns') and isinstance(v, dict):
                            cols = v.get('combination_of_columns') or (v.get('arguments') or {}).get('combination_of_columns')
                            if cols: add(m['name'], cols, where_of(v))
            for c in m.get('columns') or []:
                if not isinstance(c, dict) or 'name' not in c: continue
                for t in (c.get('data_tests') or c.get('tests') or []):
                    if t == 'unique': add(m['name'], [c['name']], None)
                    elif isinstance(t, dict) and 'unique' in t: add(m['name'], [c['name']], where_of(t['unique']))
    return out


# ---------- 2. SQL ----------
def strip_jinja(s):
    s = re.sub(r'\{#.*?#\}', ' ', s, flags=re.S)
    s = re.sub(r'\{\{-?\s*config\(.*?\)\s*-?\}\}', ' ', s, flags=re.S)
    s = re.sub(r"\{\{\s*ref\(\s*['\"]([\w]+)['\"]\s*(?:,\s*[^)]*)?\)\s*\}\}", r'\1', s)
    s = re.sub(r"\{\{\s*ref\(\s*['\"][\w]+['\"]\s*,\s*['\"]([\w]+)['\"]\s*\)\s*\}\}", r'\1', s)
    s = re.sub(r"\{\{\s*source\(\s*['\"]([\w]+)['\"]\s*,\s*['\"]([\w]+)['\"]\s*\)\s*\}\}", r'\1__\2', s)
    s = re.sub(r'\{%-?\s*(set|macro|call|filter)\b.*?(end\1)\s*-?%\}', ' ', s, flags=re.S)
    s = re.sub(r'\{%.*?%\}', ' ', s, flags=re.S)
    s = re.sub(r'\{\{-?\s*(?:\w+\.)?type_\w+\([^}]*\)\s*-?\}\}', ' varchar ', s)   # cast(x as {{ dbt.type_string() }})
    s = re.sub(r'\{\{.*?\}\}', ' jinja_expr ', s, flags=re.S)
    return s


def outputs(sel):
    """output column names of a SELECT, or None if it has a star"""
    names = set()
    for p in sel.expressions:
        if isinstance(p, exp.Star) or (isinstance(p, exp.Column) and isinstance(p.this, exp.Star)): return None
        if p.alias_or_name: names.add(p.alias_or_name.lower())
    return names


def simple(sel):
    return (isinstance(sel, exp.Select) and not sel.args.get('joins') and not sel.args.get('group')
            and not sel.args.get('distinct') and sel.args.get('from') is not None
            and isinstance(sel.args['from'].this, exp.Table))


def resolve(name, ctes, scope, depth=0):
    """follow simple CTEs; returns (base relation, scope conjuncts, dedup flag, right output cols)"""
    sel = ctes.get(name)
    if sel is None or depth > 6: return name, scope, False, None
    outs = outputs(sel)
    if not simple(sel): return name, scope, bool(sel.args.get('qualify')), outs
    scope = scope + [norm(c) for c in conjuncts(sel.args['where'].this if sel.args.get('where') else None)]
    dedup = bool(sel.args.get('qualify'))
    base, scope, d2, o2 = resolve(sel.args['from'].this.name, ctes, scope, depth + 1)
    return base, scope, dedup or d2, outs if outs is not None else o2


def analyse(project, catalog, model_outputs):
    joins, fails, nmodels = [], 0, 0
    for f in sorted(glob.glob(os.path.join(project, 'models', '**', '*.sql'), recursive=True)):
        nmodels += 1
        model = os.path.splitext(os.path.basename(f))[0]
        try:
            tree = sqlglot.parse_one(strip_jinja(open(f).read()), read=DIALECT)
        except Exception:
            fails += 1; continue
        if tree is None: fails += 1; continue
        ctes = {c.alias_or_name: c.this for c in tree.find_all(exp.CTE)}
        for sel in tree.find_all(exp.Select):
            for j in sel.args.get('joins') or []:
                if (j.args.get('side') or '').upper() != 'LEFT' or not isinstance(j.this, exp.Table): continue
                alias = j.this.alias_or_name
                key, scope, other = set(), [], 0
                for c in conjuncts(j.args.get('on')):
                    cols = list(c.find_all(exp.Column))
                    right = [x for x in cols if x.table == alias]
                    if isinstance(c, exp.EQ) and isinstance(c.left, exp.Column) and isinstance(c.right, exp.Column) \
                            and (c.left.table == alias) != (c.right.table == alias):
                        key.add((c.left if c.left.table == alias else c.right).name.lower())
                    elif cols and len(right) == len(cols):
                        scope.append(norm(c).replace(f'{alias.lower()}.', ''))
                    else:
                        other += 1
                for u in j.args.get('using') or []:
                    key.add(u.name.lower())
                base, scope, dedup, rout = resolve(j.this.name, ctes, scope)
                if rout is None: rout = model_outputs.get(base)
                # removable shape: right alias unused outside its ON
                used, unknown = False, False
                for node in sel.walk():
                    if node is j or j in [a for a in node.iter_expressions()]: pass
                for e in [*sel.expressions, sel.args.get('where'), sel.args.get('group'), sel.args.get('having'),
                          sel.args.get('qualify'), sel.args.get('order'),
                          *[x.args.get('on') for x in sel.args.get('joins') or [] if x is not j]]:
                    if e is None: continue
                    for col in e.find_all(exp.Column):
                        if col.table == alias: used = True
                        elif not col.table:
                            if isinstance(col.this, exp.Star): used = True
                            elif rout is None: unknown = True
                            elif col.name.lower() in rout: used = True
                    if isinstance(e, exp.Star) or any(isinstance(s, exp.Star) and not isinstance(s.parent, exp.Column) for s in e.find_all(exp.Star)):
                        used = True
                shape = 'used' if used else ('unknown' if unknown else 'removable')
                tests_b = catalog.get(base, [])
                unc = any(w is None and K and K <= key for K, w in tests_b)
                cond = [w for K, w in tests_b if w is not None and K and K <= key and
                        all(norm(c) in scope for c in conjuncts(sqlglot.parse_one(w, read=DIALECT)))] if not unc else []
                joins.append(dict(model=model, right=j.this.name, base=base, key=sorted(key), scope=scope,
                                  other_on=other, dedup=dedup, shape=shape,
                                  unconditional=unc, conditional=bool(cond), cond_scopes=cond,
                                  current=any(CURRENT.search(s) for s in scope)))
    return joins, fails, nmodels


def main():
    global DIALECT
    name, project, DIALECT = sys.argv[1], sys.argv[2], sys.argv[3]
    catalog = tests(project)
    model_outputs = {}
    for f in glob.glob(os.path.join(project, 'models', '**', '*.sql'), recursive=True):
        try:
            t = sqlglot.parse_one(strip_jinja(open(f).read()), read=DIALECT)
            if isinstance(t, exp.Select): model_outputs[os.path.splitext(os.path.basename(f))[0]] = outputs(t)
        except Exception: pass
    joins, fails, nmodels = analyse(project, catalog, model_outputs)
    st = Counter()
    st['models'] = nmodels; st['models not parsed'] = fails
    st['models with uniqueness tests'] = len(catalog)
    for K, w in (x for v in catalog.values() for x in v):
        st['uniqueness tests'] += 1
        if w is not None:
            st['uniqueness tests with where'] += 1
            st['... sample/time-window scopes' if SAMPLE.search(w) else '... semantic scopes'] += 1
    for j in joins:
        st['left joins'] += 1
        for k in ('unconditional', 'conditional', 'current', 'dedup'):
            if j[k]: st[f'left joins: {k}'] += 1; st[f'left joins: {k}, shape {j["shape"]}'] += 1
        st[f'left joins: shape {j["shape"]}'] += 1
        if j['current'] and not j['unconditional']: st['left joins: current scope, not unconditionally unique'] += 1
        if j['current'] and not j['unconditional'] and j['shape'] == 'removable':
            st['left joins: current scope, not unconditionally unique, removable shape'] += 1
    print(json.dumps(dict(sorted(st.items())), indent=1))
    json.dump(dict(project=project, stats=st, tests={k: [(sorted(K), w) for K, w in v] for k, v in catalog.items()},
                   joins=joins), open(os.path.join(HERE, f'dbt_scopes_{name}.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
