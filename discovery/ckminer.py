"""Discovery of conditional keys over incomplete relations.

Design (see the paper and the session notes):
  1. profile columns; build condition atoms: A=c (frequent constants of low-cardinality
     columns), A present (top), A missing (null), each with a row bitset;
  2. for every candidate key K (|K| <= kmax) compute, once, the pairs of records that are
     compatible on K (these violate cert(K)); classify each pair for the weaker classes
     (subsumed: part, equal with null=null: dom, equal and total: pos);
  3. a template (set of atoms) makes class C hold on K iff no C-violating pair has both
     records in its scope.  For each (K, C) the invalid templates are the subsets of the atom
     sets shared by the two records of a violating pair, so all valid templates with at most
     two atoms are found in one pass over the violating pairs;
  4. single-constant templates on the same column are merged into IN-lists when the cross
     pairs are violation-free (multi-template conditions);
  5. the strongest class per (K, condition) is kept, collapses (C1, C3, C4) are applied,
     non-minimal results and results implied by the unconditional keys are removed (the
     implication test of ck.py), and the rest is ranked.
Approximate conditional keys (a few violating pairs inside the scope) are reported separately
as data-cleaning candidates, with the offending rows.
"""
import base64, glob, itertools, json, math, os, struct, sys, time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'validation'))
import ck  # implication test (canonical counterexamples)

CLASSES = ['pos', 'dom', 'part', 'cert', 'cand']          # increasing strength
RANK = {c: i for i, c in enumerate(CLASSES)}

# --------------------------------------------------------------------------- loading
def load_export(path):
    """8-byte hashed cells, row-major, all-zero cell = NULL (format of the One Cover artifacts)."""
    d = json.load(open(path))[0]
    raw = base64.b64decode(d['rowData'])
    cols = [c['name'] for c in d['columns']]
    n, m = d['rowCount'], len(cols)
    vals = struct.unpack(f'<{n * m}q', raw)
    rows = [tuple(None if v == 0 else v for v in vals[r * m:(r + 1) * m]) for r in range(n)]
    return d['table'], cols, rows

# --------------------------------------------------------------------------- profiling
class Table:
    def __init__(self, name, cols, rows, P):
        self.name, self.cols, self.rows, self.P = name, cols, rows, P
        self.n = n = len(rows)
        self.col = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
        self.nulls = {c: sum(v is None for v in self.col[c]) for c in cols}
        self.freq = {c: Counter(v for v in self.col[c] if v is not None) for c in cols}
        self.NN = {c for c in cols if self.nulls[c] == 0}
        self.minsup = max(P['minsup_rows'], math.ceil(P['minsup_frac'] * n))
        # null bitset per column
        self.nullbits = {c: sum(1 << i for i, v in enumerate(self.col[c]) if v is None) for c in cols}
        self.ALL = (1 << n) - 1
        self._atoms()

    def _atoms(self):
        P, n = self.P, self.n
        self.atoms = []            # (col, kind, value)
        self.abits = []
        for c in self.cols:
            dist = len(self.freq[c])
            card = P['max_const_card_narrow'] if len(self.cols) <= P['narrow_cols'] else P['max_const_card']
            if 2 <= dist <= card:
                for rank, (v, f) in enumerate(self.freq[c].most_common()):
                    if f >= self.minsup and f <= n - self.minsup:
                        self.atoms.append((c, 'const', v, rank + 1, f / n))
                        self.abits.append(sum(1 << i for i, x in enumerate(self.col[c]) if x == v))
            nr = self.nulls[c] / n
            if self.minsup <= self.nulls[c] <= n - self.minsup:
                self.atoms.append((c, 'top', None, 0, 1 - nr)); self.abits.append(self.ALL & ~self.nullbits[c])
                self.atoms.append((c, 'null', None, 0, nr)); self.abits.append(self.nullbits[c])
        # atoms selecting identical rows are one condition (e.g. co-null columns): keep the
        # first, remember the others as aliases
        seen, keep, self.alias = {}, [], defaultdict(list)
        for a, b in enumerate(self.abits):
            if b in seen: self.alias[seen[b]].append(a)
            else: seen[b] = len(keep); keep.append(a)
        self.alias = {keep.index(k) if False else k: v for k, v in self.alias.items()}
        old_atoms = self.atoms
        self.alias_names = {i: [old_atoms[a] for a in self.alias.get(i, [])] for i in range(len(keep))}
        self.atoms = [old_atoms[a] for a in keep]; self.abits = [self.abits[a] for a in keep]
        self.row_atoms = [[] for _ in range(n)]
        for a, b in enumerate(self.abits):
            x = b
            while x:
                low = x & -x; i = low.bit_length() - 1; self.row_atoms[i].append(a); x ^= low
        self.row_atoms = [frozenset(s) for s in self.row_atoms]

    def key_columns(self):
        P = self.P
        if P.get('key_cols'): return [c for c in P['key_cols'] if c in self.cols]
        return [c for c in self.cols if self.nulls[c] / self.n <= P['max_key_null'] and len(self.freq[c]) >= 2]

# --------------------------------------------------------------------------- pairs
class Capped(Exception):
    pass

def compatible_pairs(T, K, cap):
    """all pairs (i<j) compatible on K (null or equal on every column of K)."""
    idx = [T.cols.index(c) for c in K]
    pat = defaultdict(list)
    for i, r in enumerate(T.rows):
        pat[tuple(r[k] is None for k in idx)].append(i)
    pats = list(pat)
    out = []
    for a in range(len(pats)):
        for b in range(a, len(pats)):
            P1, P2 = pats[a], pats[b]
            on = [k for t, k in enumerate(idx) if not P1[t] and not P2[t]]
            R1, R2 = pat[P1], pat[P2]
            if not on:
                cnt = len(R1) * (len(R1) - 1) // 2 if a == b else len(R1) * len(R2)
                if len(out) + cnt > cap: raise Capped
                if a == b: out += [(R1[x], R1[y]) for x in range(len(R1)) for y in range(x + 1, len(R1))]
                else: out += [(min(i, j), max(i, j)) for i in R1 for j in R2]
                continue
            g = defaultdict(list)
            for j in R2: g[tuple(T.rows[j][k] for k in on)].append(j)
            for i in R1:
                for j in g.get(tuple(T.rows[i][k] for k in on), ()):
                    if a == b and j <= i: continue
                    out.append((min(i, j), max(i, j)))
                    if len(out) > cap: raise Capped
    return out

def classify(T, K, pairs):
    """strongest class each compatible pair violates: cert / part / dom / pos (pos violators
    also violate all others, etc.)"""
    idx = [T.cols.index(c) for c in K]
    res = []
    for i, j in pairs:
        ri, rj = T.rows[i], T.rows[j]
        vi = [ri[k] for k in idx]; vj = [rj[k] for k in idx]
        if all(x is not None and x == y for x, y in zip(vi, vj)): res.append('pos')
        elif all(x == y for x, y in zip(vi, vj)): res.append('dom')
        elif all(x is None or x == y for x, y in zip(vi, vj)) or all(y is None or x == y for x, y in zip(vi, vj)):
            res.append('part')
        else: res.append('cert')
    return res
# a pair labelled L violates class C iff RANK[C] >= RANK[L] for C in pos..cert (pos-violators violate every class)

def violators(labels, C):
    if C == 'cand': C = 'cert'
    return [k for k, L in enumerate(labels) if RANK[C] >= RANK[L]]

# --------------------------------------------------------------------------- condition search
def consistent(T, atoms):
    cols = [T.atoms[a][0] for a in atoms]
    return len(set(cols)) == len(cols)

def condition_search(T, K, C, pairs, labels):
    """valid templates (<= 2 atoms) and approximate ones for class C on K."""
    P = T.P
    vio = violators(labels, C)
    Kset = set(K)
    usable = [a for a, (c, kind, *_ ) in enumerate(T.atoms)
              if not (c in Kset and kind in ('const', 'null'))]          # C3, C4
    usable_set = set(usable)
    shared = Counter()
    for k in vio:
        i, j = pairs[k]
        shared[T.row_atoms[i] & T.row_atoms[j] & usable_set] += 1
    bad1, bad2 = Counter(), Counter()
    for S, mult in shared.items():
        for a in S: bad1[a] += mult
        for a, b in itertools.combinations(sorted(S), 2): bad2[(a, b)] += mult
    eps = max(P['approx_pairs'], 0)
    exact, approx = [], []
    sup = lambda bits: bin(bits).count('1')
    for a in usable:
        s = sup(T.abits[a])
        if s < T.minsup: continue
        if bad1[a] == 0: exact.append(((a,), T.abits[a]))
        elif bad1[a] <= eps: approx.append(((a,), T.abits[a], bad1[a]))
    valid1 = {t[0][0] for t in exact}
    for a, b in itertools.combinations(usable, 2):
        if a in valid1 or b in valid1 or not consistent(T, (a, b)): continue
        bits = T.abits[a] & T.abits[b]
        if sup(bits) < T.minsup: continue
        v = bad2[(a, b)]
        if v == 0: exact.append(((a, b), bits))
        elif v <= eps and bad1[a] > eps and bad1[b] > eps: approx.append(((a, b), bits, v))
    return exact, approx, vio

def merge_constants(T, K, C, pairs, vio, exact):
    """IN-list conditions: single-constant templates on one column whose cross pairs are clean."""
    bycol = defaultdict(list)
    for (atoms, bits) in exact:
        if len(atoms) == 1 and T.atoms[atoms[0]][1] == 'const':
            bycol[T.atoms[atoms[0]][0]].append((atoms[0], bits))
    merged = []
    for col, lst in bycol.items():
        if len(lst) < 2: continue
        lst.sort(key=lambda x: -bin(x[1]).count('1'))
        cross_bad = set()
        for k in vio:
            i, j = pairs[k]
            ai = [a for a, _ in lst if (T.abits[a] >> i) & 1]
            aj = [a for a, _ in lst if (T.abits[a] >> j) & 1]
            for x in ai:
                for y in aj:
                    if x != y: cross_bad.add(frozenset((x, y)))
        chosen = [lst[0]]
        for a, bits in lst[1:]:
            if all(frozenset((a, b)) not in cross_bad for b, _ in chosen): chosen.append((a, bits))
        if len(chosen) >= 2:
            bits = 0
            for _, b in chosen: bits |= b
            merged.append(([(a,) for a, _ in chosen], bits))
    return merged

# --------------------------------------------------------------------------- main mining loop
def mine_table(T):
    P = T.P
    keycols = T.key_columns()
    uncond = {}            # K -> strongest unconditional class (or None)
    found = []             # dicts
    approx_found = []
    pair_cache = {}
    t0 = time.time()
    for size in range(1, P['kmax'] + 1):
        for K in itertools.combinations(keycols, size):
            subs = [S for r in range(1, size) for S in itertools.combinations(K, r)]
            if any(uncond.get(S) == 'cand' for S in subs): continue
            pairs = None
            for parent in itertools.combinations(K, size - 1):
                if parent in pair_cache and pair_cache[parent] is not None and size > 1:
                    extra = [c for c in K if c not in parent][0]; k = T.cols.index(extra)
                    pairs = [(i, j) for i, j in pair_cache[parent]
                             if T.rows[i][k] is None or T.rows[j][k] is None or T.rows[i][k] == T.rows[j][k]]
                    break
            if pairs is None:
                try: pairs = compatible_pairs(T, K, P['pair_cap'])
                except Capped: pairs = None
            pair_cache[K] = pairs
            total = all(T.nulls[c] == 0 for c in K)
            if pairs is None:
                # too many compatible pairs for certain/partial keys; possible and domain keys
                # are still decided (and searched) by grouping
                idx = [T.cols.index(c) for c in K]
                gpos, gdom = defaultdict(list), defaultdict(list)
                for i, r in enumerate(T.rows):
                    v = tuple(r[k] for k in idx)
                    gdom[v].append(i)
                    if None not in v: gpos[v].append(i)
                npairs = lambda g: sum(len(x) * (len(x) - 1) // 2 for x in g.values())
                if npairs(gdom) == 0: uncond[K] = 'dom'
                elif npairs(gpos) == 0: uncond[K] = 'pos'
                else: uncond[K] = None
                if npairs(gdom) <= P['pair_cap']:
                    pairs = [(x[a], x[b]) for x in gdom.values() for a in range(len(x)) for b in range(a + 1, len(x))]
                    labels = classify(T, K, pairs)
                    involved = len({i for p in pairs for i in p})
                    if involved <= P['max_involved'] * T.n:
                        for C in ['dom', 'pos']:
                            if uncond[K] and RANK[uncond[K]] >= RANK[C]: break
                            if any(uncond.get(S) and RANK[uncond[S]] >= RANK[C] for S in subs): continue
                            exact, approx, vio = condition_search(T, K, C, pairs, labels)
                            for atoms, bits in exact: found.append(dict(K=K, C=C, cond=[atoms], bits=bits))
                            for cond, bits in merge_constants(T, K, C, pairs, vio, exact):
                                found.append(dict(K=K, C=C, cond=cond, bits=bits))
                            for atoms, bits, v in approx:
                                bad = [pairs[k] for k in vio if (bits >> pairs[k][0]) & 1 and (bits >> pairs[k][1]) & 1]
                                approx_found.append(dict(K=K, C=C, cond=[atoms], bits=bits, violations=bad))
                continue
            labels = classify(T, K, pairs)
            strongest = None
            for C in ['cand', 'cert', 'part', 'dom', 'pos']:
                if C == 'cand' and not total: continue
                if not violators(labels, C): strongest = C; break
            uncond[K] = strongest
            involved = len({i for p in pairs for i in p})
            if involved > P['max_involved'] * T.n: continue
            for C in ['cert', 'part', 'dom', 'pos']:
                if strongest is not None and RANK[strongest] >= RANK[C]: break
                # skip if a proper subset already is an unconditional key of class >= C
                if any(uncond.get(S) and RANK[uncond[S]] >= RANK[C] for S in subs):
                    continue
                exact, approx, vio = condition_search(T, K, C, pairs, labels)
                for atoms, bits in exact:
                    found.append(dict(K=K, C=C, cond=[atoms], bits=bits))
                for cond, bits in merge_constants(T, K, C, pairs, vio, exact):
                    found.append(dict(K=K, C=C, cond=cond, bits=bits))
                for atoms, bits, v in approx:
                    bad = [pairs[k] for k in vio
                           if (bits >> pairs[k][0]) & 1 and (bits >> pairs[k][1]) & 1]
                    approx_found.append(dict(K=K, C=C, cond=[atoms], bits=bits, violations=bad))
        if time.time() - t0 > P['time_budget']: break
    return uncond, found, approx_found

# --------------------------------------------------------------------------- post-processing
def scope_total(T, K, bits):
    nb = 0
    for c in K: nb |= T.nullbits[c]
    return nb & bits == 0

def to_ck(T, cond, C, K):
    temps = []
    for atoms in cond:
        t = {c: '_' for c in T.cols}
        for a in atoms:
            c, kind, v, *_ = T.atoms[a]
            t[c] = v if kind == 'const' else 'T' if kind == 'top' else 'N'
        temps.append(t)
    return (temps, C, frozenset(K))

def postprocess(T, uncond, found):
    # strongest class per (K, condition); upgrade to cand when the scope is K-total
    best = {}
    for f in found:
        key = (f['K'], tuple(sorted(f['cond'])))
        C = f['C']
        if scope_total(T, f['K'], f['bits']): C = 'cand'      # (C1): all classes coincide
        f = dict(f, C=C, total=scope_total(T, f['K'], f['bits']))
        if key not in best or RANK[C] > RANK[best[key]['C']]: best[key] = f
    res = list(best.values())
    # minimality: drop if a less precise condition with a subset key and >= class exists
    def atomset(f): return [set(a) for a in f['cond']]
    def less_precise(g, f):   # every template of f contains some template of g, and g's scope >= f's
        return all(any(sa <= ta for sa in atomset(g)) for ta in atomset(f)) and (f['bits'] | g['bits']) == g['bits']
    keep = []
    byK = defaultdict(list)
    for g in res: byK[tuple(sorted(g['K']))].append(g)
    for f in res:
        Ks = sorted(f['K'])
        subs = [S for r in range(1, len(Ks) + 1) for S in itertools.combinations(Ks, r)]
        fid = (f['K'], tuple(map(tuple, f['cond'])))
        dominated = any(g is not f and RANK[g['C']] >= RANK[f['C']] and less_precise(g, f)
                        and (g['K'], tuple(map(tuple, g['cond']))) != fid
                        for S in subs for g in byK.get(S, ()))
        if not dominated: keep.append(f)
    # not implied by the unconditional keys (with NOT NULL columns)
    Sigma = [([{c: '_' for c in T.cols}], C, frozenset(K)) for K, C in uncond.items() if C]
    Sigma = [s for s in Sigma if not any(set(s[2]) > set(t[2]) and RANK[t[1]] >= RANK[s[1]] for t in Sigma)]
    out = []
    for f in keep:
        phi = to_ck(T, f['cond'], f['C'], f['K'])
        rel = set(f['K']) | {T.atoms[a][0] for atoms in f['cond'] for a in atoms}
        cols = sorted(rel | {c for s in Sigma for c in s[2] if set(s[2]) <= rel})
        Sig = [(([{c: '_' for c in cols}]), s[1], s[2]) for s in Sigma if set(s[2]) <= set(cols)]
        ph = ([{c: t[c] for c in cols} for t in phi[0]], phi[1], phi[2])
        if ck.canonical_counterexample(cols, T.NN & set(cols), Sig, ph) is None: continue
        out.append(f)
    return out

def verify(T, f, limit=300):
    """independent check on the data: ck.sat_key (all pairs) on the scope; for large scopes a
    direct test per null-pattern pair written independently of compatible_pairs."""
    sch = T.cols
    temps, C, K = to_ck(T, f['cond'], f['C'], f['K'])
    q = lambda t, tau: all(s == '_' or (s == 'T' and t[c] is not None) or (s == 'N' and t[c] is None)
                           or (s not in ('_', 'T', 'N') and t[c] == s) for c, s in tau.items())
    scope = [t for t in (dict(zip(sch, r)) for r in T.rows) if any(q(t, tau) for tau in temps)]
    if len(scope) <= limit:
        return ck.sat_key(scope, ([{c: '_' for c in sch}], C, K))
    Ks = sorted(K)
    if C == 'cand' and any(t[c] is None for t in scope for c in Ks): return False
    groups = defaultdict(list)
    for t in scope: groups[frozenset(c for c in Ks if t[c] is not None)].append(t)
    for P1, P2 in itertools.combinations_with_replacement(list(groups), 2):
        M = sorted(P1 & P2); idx = defaultdict(list)
        for t in groups[P2]: idx[tuple(t[c] for c in M)].append(t)
        for t in groups[P1]:
            for u in idx.get(tuple(t[c] for c in M), ()):
                if u is t: continue
                if ck.pair_violates('dom' if C == 'cand' else C, K, t, u): return False
    return True

# --------------------------------------------------------------------------- reporting
def describe_atom(T, a):
    c, kind, v, rank, share = T.atoms[a]
    if kind == 'top': d = f'{c} present'
    elif kind == 'null': d = f'{c} missing'
    elif isinstance(v, str): d = f'{c} = "{v}" ({share:.0%})'
    else: d = f'{c} = v{rank} ({share:.0%})'
    al = T.alias_names.get(a, [])
    if al:
        d += ' [same rows: ' + ', '.join(f'{x[0]} {x[1] if x[1] != "const" else "=v" + str(x[3])}'.replace(' top', ' present').replace(' null', ' missing') for x in al[:3]) + (' ...' if len(al) > 3 else '') + ']'
    return d

ID_LIKE = __import__('re').compile(r'(id$|ID|[Nn]ame|year|[Dd]ate|[Nn]umber|^number|stint|code|abbrev|_no$|nr$|^no$|place|chamber|ship|boat|voyage|master|ncid|_num$|addr|phone|_dt$|_lic$|accession|checksum|gene_|locus|orf$|sequence$)', 0)

def id_like(T, c):
    return bool(ID_LIKE.search(c)) or len(T.freq[c]) >= 0.9 * (T.n - T.nulls[c])

def describe_cond(T, cond):
    if len(cond) > 1 and all(len(a) == 1 for a in cond):
        col = T.atoms[cond[0][0]][0]
        vals = [T.atoms[a[0]][2] for a in cond]
        if all(isinstance(v, str) for v in vals):
            return f'{col} in {{' + ', '.join(f'"{v}"' for v in vals) + '}'
        return f'{col} in {{' + ', '.join(f'v{T.atoms[a[0]][3]}' for a in cond) + '}'
    return ' or '.join('(' + ', '.join(describe_atom(T, a) for a in atoms) + ')' for atoms in cond)

def sql_pred(T, cond):
    def atom(a):
        c, kind, v, rank, _ = T.atoms[a]
        if kind == 'const' and isinstance(v, str): return f"{c} = '{v}'"
        return f'{c} IS NOT NULL' if kind == 'top' else f'{c} IS NULL' if kind == 'null' else f"{c} = :v{rank}"
    return ' OR '.join('(' + ' AND '.join(atom(a) for a in atoms) + ')' for atoms in cond)

def score(T, f, uncond):
    sup = bin(f['bits']).count('1') / T.n
    base = uncond.get(f['K'])
    gain = RANK[f['C']] - (RANK[base] if base else -1)
    natoms = sum(len(a) for a in f['cond'])
    simplicity = 1 / (1 + 0.5 * (natoms - 1))
    # null-awareness: does the key carry nulls inside the scope (null semantics matter)?
    nb = 0
    for c in f['K']: nb |= T.nullbits[c]
    nulls_in_scope = bin(nb & f['bits']).count('1') / max(1, bin(f['bits']).count('1'))
    measures = sum(not id_like(T, c) for c in f['K'])
    orth = 1.0 if measures == 0 else 0.5 if measures == 1 else 0.25
    s = math.sqrt(sup) * (1 + 0.5 * gain) * simplicity * (1 + 0.3 * (nulls_in_scope > 0)) * orth * (1 - 0.1 * (len(f['K']) - 1))
    return s, sup, gain, nulls_in_scope

def tags(T, f, uncond):
    t = []
    sup = bin(f['bits']).count('1') / T.n
    if 0.05 <= sup <= 0.95: t.append('QO')
    if f['C'] == 'pos':
        # GROUP BY trap: possible key holds, domain key fails in the scope
        t.append('GROUP-BY-trap')
    if f['C'] in ('part', 'cert') and not f['total']: t.append('null-semantics')
    if any(not id_like(T, c) for c in f['K']): t.append('accidental?')
    t.append('cleaning-rule')
    return t
