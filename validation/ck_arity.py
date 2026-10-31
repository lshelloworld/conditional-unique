"""Exact m-ary closure on small schemas (no constants, NN empty).

A constraint is identified with the set E of abstract pairs/records it forbids; Gamma |= psi iff
E(psi) is covered by the union of E(gamma), gamma in Gamma (keys are pair-local and, without
constants, abstract pairs with fresh values represent all pairs). The m-ary closure of Sigma is the
least set containing Sigma that contains every psi in the language whose E is covered by <= m
members. Languages: 'top' (templates over bottom/top: scopes are upward-closed families of
presence sets), 'null' (bottom/null: downward-closed families) and 'full' (bottom/top/null:
arbitrary families)."""
import itertools, random, sys

TYPES = ['bn', 'eq', 'nv', 'vn', 'dd']
SWAP = {'bn': 'bn', 'eq': 'eq', 'nv': 'vn', 'vn': 'nv', 'dd': 'dd'}

def universe(n):
    pts, seen = [], set()
    for ty in itertools.product(TYPES, repeat=n):
        sw = tuple(SWAP[x] for x in ty)
        if sw in seen: continue
        seen.add(ty); pts.append(('p', ty))
    for r in range(n + 1):
        for X in itertools.combinations(range(n), r):
            pts.append(('s', frozenset(X)))
    return pts

def pres(ty, which):
    ok = ('eq', 'dd', 'vn') if which == 0 else ('eq', 'dd', 'nv')
    return frozenset(i for i, x in enumerate(ty) if x in ok)

def viol(cls, K, ty):
    v = [ty[i] for i in K]
    if cls == 'pos': return all(x == 'eq' for x in v)
    if cls in ('dom', 'cand'): return all(x in ('bn', 'eq') for x in v)
    if cls == 'part':
        return not (any(x in ('vn', 'dd') for x in v) and any(x in ('nv', 'dd') for x in v))
    if cls == 'cert': return all(x != 'dd' for x in v)
    return False

def forbids(S, cls, K, kind, x):
    """does the constraint with scope S forbid the abstract record or pair x? A pair is forbidden
    also when one of its records violates a single-record constraint on its own."""
    single = lambda X: X in S and cls in ('cand', 'nn') and not set(K) <= X
    if kind == 's': return single(x)
    a, b = pres(x, 0), pres(x, 1)
    return (a in S and b in S and viol(cls, K, x)) or single(a) or single(b)

def families(n, lang):
    sets = [frozenset(X) for r in range(n + 1) for X in itertools.combinations(range(n), r)]
    fams = []
    for bits in range(1, 1 << len(sets)):
        F = frozenset(s for i, s in enumerate(sets) if bits >> i & 1)
        if lang == 'top' and any(t not in F for s in F for t in sets if s <= t): continue
        if lang == 'null' and any(t not in F for s in F for t in sets if t <= s): continue
        fams.append(F)
    return fams

def language(n, lang, classes=('pos', 'dom', 'part', 'cert', 'cand', 'nn')):
    U = universe(n); idx = {u: i for i, u in enumerate(U)}
    Ks = [tuple(K) for r in range(n + 1) for K in itertools.combinations(range(n), r)]
    L = {}
    for S in families(n, lang):
        for cls in classes:
            for K in Ks:
                m = 0
                for i, (kind, x) in enumerate(U):
                    if forbids(S, cls, K, kind, x): m |= 1 << i
                L.setdefault(m, (S, cls, K))
    return U, L

def covered(c, D, m):
    """is bitmask c covered by the union of at most m members of D?"""
    if c == 0: return True
    R = {d & c for d in D if d & c}
    R = [r for r in R if not any(r != s and r | s == s for s in R)]
    def go(rem, k):
        if rem == 0: return True
        if k == 0: return False
        low = rem & -rem
        return any(go(rem & ~r, k - 1) for r in R if r & low)
    return go(c, m)

def closure(L, Sigma, m, target=None):
    D = set(Sigma) | {0}
    cand = [e for e in L if e not in D]
    changed = True
    while changed:
        changed = False
        rest = []
        for e in cand:
            if covered(e, D, m): D.add(e); changed = True
            else: rest.append(e)
        cand = rest
        if target is not None and target in D: return D
    return D

def min_arity(L, Sigma, target, mmax=6):
    for m in range(1, mmax + 1):
        if target in closure(L, Sigma, m, target): return m
    return None
