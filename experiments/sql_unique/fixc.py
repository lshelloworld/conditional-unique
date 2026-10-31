"""Discovery of conditional UNIQUE constraints with a fixed condition, and over all templates of
a bounded condition language (Section VI of conditional-unique.tex).

FixC(r, C, sem, kmax): the minimal keys K such that C : U(K) (sem 'U') or C : U=(K) (sem 'Ueq')
holds on r, of at most kmax columns if given.
  1. scope: the rows matching C;
  2. null encoding: for 'U' every null becomes a value of its own (row, column), for 'Ueq' all
     nulls become one value -- agreement is then plain equality, and FixC is UCC discovery on
     the encoded scope;
  3. hybrid search: position list indexes (PLIs) per column restricted to the scope; seed
     disagreement sets from neighbouring rows in PLI clusters; candidates = minimal
     transversals of the disagreement sets (incremental Berge); validate each candidate by PLI
     intersection; a violating pair adds its disagreement set and the candidates are updated;
     stop when all candidates are valid.
DiscA(r, a, kmax): FixC for every template with at most a atoms (= c, <> c, IS NULL, IS NOT
NULL over the active domains), from wide to narrow scopes: a template inherits the
disagreement sets of its parent (one atom fewer) whose witness rows lie in its scope.
Rows are dicts column -> value (None = null); conditions use cunique.py's template format."""
import itertools
from cunique import matches

NULLV = ('__null__',)


def encode(rows, idx, cols, sem):
    enc = {}
    for i in idx:
        enc[i] = tuple((('__null__', i, A) if sem == 'U' else NULLV) if rows[i][A] is None else rows[i][A] for A in cols)
    return enc


def plis(enc, idx, ncols):
    out = []
    for j in range(ncols):
        g = {}
        for i in idx: g.setdefault(enc[i][j], []).append(i)
        out.append([c for c in g.values() if len(c) > 1])
    return out


def disagree(enc, i, k):
    a, b = enc[i], enc[k]
    return frozenset(j for j in range(len(a)) if a[j] != b[j])


def validate(enc, P, K):
    """None if K is a key of the encoded scope, else a violating pair (i, k)"""
    if not K:
        idx = list(enc)
        return (idx[0], idx[1]) if len(idx) > 1 else None
    K = sorted(K)
    clusters = P[K[0]]
    for j in K[1:]:
        nxt = []
        for c in clusters:
            g = {}
            for i in c: g.setdefault(enc[i][j], []).append(i)
            nxt += [x for x in g.values() if len(x) > 1]
        clusters = nxt
        if not clusters: return None
    return (clusters[0][0], clusters[0][1]) if clusters else None


def minimize(sets):
    sets = sorted(set(sets), key=len)
    out = []
    for s in sets:
        if not any(t <= s for t in out): out.append(s)
    return out


def berge_add(T, E, kmax):
    """minimal transversals after adding edge E to a hypergraph whose minimal transversals are T"""
    keep = [t for t in T if t & E]
    new = [t | {e} for t in T if not (t & E) for e in E]
    if kmax is not None: new = [t for t in new if len(t) <= kmax]
    return minimize(keep + new)


def fixc(rows, cols, C, sem, kmax=None, seed_edges=(), stats=None):
    idx = [i for i, r in enumerate(rows) if any(matches(r, t) for t in C)]
    if len(idx) < 2: return [frozenset()], []
    enc = encode(rows, idx, cols, sem)
    P = plis(enc, idx, len(cols))
    S = set(idx)
    edges = {}                                      # disagreement set -> witness pair
    for D, (i, k) in seed_edges:
        if i in S and k in S: edges.setdefault(D, (i, k))
    for clusters in P:                              # neighbours in PLI clusters
        for c in clusters:
            for i, k in zip(c, c[1:]):
                edges.setdefault(disagree(enc, i, k), (i, k))
    if frozenset() in edges: return [], list(edges.items())     # two rows agree everywhere
    H = minimize(edges)
    T = [frozenset()]
    for E in H: T = berge_add(T, E, kmax)
    valid = set(); checks = 0
    while True:
        todo = [t for t in T if t not in valid]
        if not todo: break
        for t in todo:
            checks += 1
            w = validate(enc, P, t)
            if w is None: valid.add(t); continue
            D = disagree(enc, *w)
            if not D: return [], list(edges.items())
            edges.setdefault(D, w)
            T = berge_add(T, D, kmax)
            break
    if stats is not None:
        stats['checks'] = stats.get('checks', 0) + checks
        stats['edges'] = stats.get('edges', 0) + len(edges)
    names = [frozenset(cols[j] for j in t) for t in T]
    return sorted(names, key=lambda k: (len(k), sorted(k))), list(edges.items())


def atoms(rows, cols):
    out = []
    for A in cols:
        vals = sorted({r[A] for r in rows if r[A] is not None}, key=repr)
        out += [(A, ('in', frozenset([v]))) for v in vals] + [(A, ('notin', frozenset([v]))) for v in vals]
        out += [(A, ('null',)), (A, ('notin', frozenset()))]
    return out


def disca(rows, cols, a, sem, kmax=None, stats=None):
    """{template (frozenset of atoms): minimal keys}; templates over distinct columns"""
    AT = atoms(rows, cols)
    res, edges_of = {}, {}
    for n in range(a + 1):
        for combo in itertools.combinations(AT, n):
            if len({A for A, _ in combo}) < n: continue
            key = frozenset(combo)
            tpl = {A: ('any',) for A in cols}
            for A, e in combo: tpl[A] = e
            seed = edges_of[key - {combo[-1]}] if n else ()
            ks, edges = fixc(rows, cols, [tpl], sem, kmax, seed, stats)
            res[key], edges_of[key] = ks, edges
    return res
