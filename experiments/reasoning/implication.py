"""Implication of conditional keys: Algorithm 1 (canonical counterexamples) and a SAT baseline.

Constraints use the representation of validation/ck.py: a template maps every column to '_'
(bottom), 'T' (top), 'N' (null) or an int constant; a constraint is (condition, class, K) with
the condition a list of templates. implies_canonical and implies_sat return True iff
Sigma |= phi; both are exact (the SAT encoding searches all one- and two-record instances,
which suffice by the pairing lemma)."""
import itertools
from pysat.solvers import Cadical153


# ---------------------------------------------------------------- Algorithm 1
def _relevant(schema, Sigma, K):
    rel = set(K)
    for cond, _, _ in Sigma:
        for tau in cond:
            for A in schema:
                if tau[A] in ('T', 'N'): rel.add(A)
    return rel


def _refinements(tau, schema, NN, rel):
    opts = []
    for A in schema:
        s = tau[A]
        if A in NN:
            if s == 'N': return []
            opts.append(('T',) if s == '_' else (s,))
        elif s == '_':
            opts.append(('N', 'T') if A in rel else ('T',))
        else:
            opts.append((s,))
    return [dict(zip(schema, c)) for c in itertools.product(*opts)]


class Checker:
    """Sigma compiled for fast evaluation on canonical objects."""

    def __init__(self, schema, Sigma):
        self.schema = schema
        self.S = []
        for cond, cls, K in Sigma:
            temps = [[(A, s) for A, s in tau.items() if s != '_'] for tau in cond]
            self.S.append((temps, cls, tuple(K)))

    @staticmethod
    def _q(t, temps):
        for atoms in temps:
            for A, s in atoms:
                v = t[A]
                if (v is None) if s == 'T' else (v is not None) if s == 'N' else (v != s): break
            else:
                return True
        return False

    def sat(self, inst):
        for temps, cls, K in self.S:
            sc = [t for t in inst if self._q(t, temps)]
            if not sc: continue
            if cls in ('cand', 'nn') and any(t[A] is None for t in sc for A in K): return False
            if len(sc) == 2 and _pair_violates(cls, K, sc[0], sc[1]): return False
        return True


def _pair_violates(cls, K, t, u):
    if cls == 'pos': return all(t[A] is not None and t[A] == u[A] for A in K)
    if cls in ('dom', 'cand'): return all(t[A] == u[A] for A in K)
    if cls == 'part':
        return all(t[A] is None or t[A] == u[A] for A in K) or all(u[A] is None or u[A] == t[A] for A in K)
    if cls == 'cert': return all(t[A] is None or u[A] is None or t[A] == u[A] for A in K)
    return False


def _canon(rho, rho2, schema, K):
    t, u = {}, {}
    f = itertools.count(10 ** 9)
    for A in schema:
        x, y = rho[A], rho2[A]
        tn, un = x == 'N', y == 'N'
        if tn: t[A] = None
        if un: u[A] = None
        if tn and un: continue
        if tn: u[A] = y if isinstance(y, int) else next(f); continue
        if un: t[A] = x if isinstance(x, int) else next(f); continue
        xc, yc = isinstance(x, int), isinstance(y, int)
        if A in K:
            if xc and yc: t[A], u[A] = x, y
            elif xc: t[A] = u[A] = x
            elif yc: t[A] = u[A] = y
            else: t[A] = u[A] = next(f)
        else:
            t[A] = x if xc else next(f)
            u[A] = y if yc else next(f)
    return t, u


def _compatible(t1, t2, NN=()):
    """can some record qualify for both templates?"""
    for A, x in t1.items():
        y = t2[A]
        if x == '_' or y == '_': 
            if A in NN and 'N' in (x, y): return False
            continue
        if x == y: continue
        if 'N' in (x, y): return False           # null vs top or constant
        if x != 'T' and y != 'T': return False   # two different constants
    return True


def restrict(Sigma, temps, NN=()):
    """the premises as seen by records that qualify for one of temps: templates incompatible with
    all of temps are dropped, and premises left without templates are dropped (exact: no record
    of the target's scope can qualify for a dropped template)"""
    out = []
    for cond, cls, K in Sigma:
        c = [p for p in cond if any(_compatible(p, t, NN) for t in temps)]
        if c: out.append((c, cls, K))
    return out


def dominated(schema, NN, Sigma, K):
    """columns whose best choice in a counterexample is known, for A outside K: if A is in no key
    of Sigma and Sigma's templates never require A missing, a null escapes every template a value
    qualifies for (choose null); if they never require it present, choose a value; and if every
    template that requires a value on A belongs to a possible, domain, partial or certain key
    containing A, choose a value.
    Returns {A: 'N' or 'T'}; exact because satisfaction of a key is monotone in its scope when
    the key does not contain A, and the target's violation does not depend on A."""
    inkeys = set(K)
    for _, _, L in Sigma: inkeys |= set(L)
    out = {}
    for A in schema:
        if A in K or A in NN: continue
        if A not in inkeys:
            syms = {tau[A] for cond, _, _ in Sigma for tau in cond} - {'_'}
            if 'N' not in syms: out[A] = 'N'
            elif not (syms - {'N'}): out[A] = 'T'
        elif all(A in L and c not in ('cand', 'nn') for cond, c, L in Sigma for tau in cond
                 if tau[A] not in ('_', 'N')):
            # every template that admits only values on A belongs to a key without single-record
            # part whose columns include A: distinct fresh values on A satisfy it (type dd
            # satisfies every pair condition) and escape the templates that require A missing,
            # so a value is always at least as good
            out[A] = 'T'
    return out


def _refinements_dom(tau, schema, NN, rel, forced):
    opts = []
    for A in schema:
        s = tau[A]
        if A in NN:
            if s == 'N': return []
            opts.append(('T',) if s == '_' else (s,))
        elif s == '_':
            opts.append((forced[A],) if A in forced else ('N', 'T') if A in rel else ('T',))
        else:
            opts.append((s,))
    return [dict(zip(schema, c)) for c in itertools.product(*opts)]


def open_positions(schema, NN, Sigma, phi, prune=True):
    """b of Theorem 7, with or without pruning by compatibility"""
    cond, cls, K = phi
    b = 0
    for i in range(len(cond)):
        for j in range(i, len(cond)):
            S = restrict(Sigma, [cond[i], cond[j]], NN) if prune else Sigma
            rel = _relevant(schema, S, set(K))
            forced = dominated(schema, NN, S, K) if prune else {}
            b = max(b, sum(1 for t in (cond[i], cond[j]) for A in rel
                           if t[A] == '_' and A not in NN and A not in forced))
    return b


def implies_pruned(schema, NN, Sigma, phi, stats=None):
    """Algorithm 1 run per template pair against the premises restricted to that pair"""
    cond, cls, K = phi
    K = set(K)
    n = 0
    if cls in ('cand', 'nn'):
        for tau in cond:
            S = restrict(Sigma, [tau], NN); chk = Checker(schema, S); rel = _relevant(schema, S, K)
            forced = dominated(schema, NN, S, K)
            for rho in _refinements_dom(tau, schema, NN, rel, forced):
                t, _ = _canon(rho, rho, schema, set()); n += 1
                if any(t[A] is None for A in K) and chk.sat([t]):
                    if stats is not None: stats['objects'] = n
                    return False
    for i in range(len(cond)):
        for j in range(i, len(cond)):
            S = restrict(Sigma, [cond[i], cond[j]], NN); chk = Checker(schema, S); rel = _relevant(schema, S, K)
            forced = dominated(schema, NN, S, K)
            for rho in _refinements_dom(cond[i], schema, NN, rel, forced):
                for rho2 in _refinements_dom(cond[j], schema, NN, rel, forced):
                    t, u = _canon(rho, rho2, schema, K); n += 1
                    if _pair_violates(cls, K, t, u) and chk.sat([t, u]):
                        if stats is not None: stats['objects'] = n
                        return False
    if stats is not None: stats['objects'] = n
    return True


def implies_canonical(schema, NN, Sigma, phi, chk=None, stats=None):
    cond, cls, K = phi
    K = set(K)
    chk = chk or Checker(schema, Sigma)
    rel = _relevant(schema, Sigma, K)
    refs = [_refinements(tau, schema, NN, rel) for tau in cond]
    n = 0
    if cls in ('cand', 'nn'):
        for R in refs:
            for rho in R:
                t, _ = _canon(rho, rho, schema, set())
                n += 1
                if any(t[A] is None for A in K) and chk.sat([t]):
                    if stats is not None: stats['objects'] = n
                    return False
    for i in range(len(cond)):
        for j in range(i, len(cond)):
            for rho in refs[i]:
                for rho2 in refs[j]:
                    t, u = _canon(rho, rho2, schema, K)
                    n += 1
                    if _pair_violates(cls, K, t, u) and chk.sat([t, u]):
                        if stats is not None: stats['objects'] = n
                        return False
    if stats is not None: stats['objects'] = n
    return True


# ---------------------------------------------------------------- SAT baseline
class _Enc:
    def __init__(self):
        self.n = 0; self.cl = []

    def var(self):
        self.n += 1; return self.n

    def AND(self, lits):
        lits = list(lits)
        if not lits: return self.TRUE
        if len(lits) == 1: return lits[0]
        v = self.var()
        for l in lits: self.cl.append([-v, l])
        self.cl.append([v] + [-l for l in lits])
        return v

    def OR(self, lits):
        lits = list(lits)
        if not lits: return -self.TRUE
        if len(lits) == 1: return lits[0]
        v = self.var()
        for l in lits: self.cl.append([v, -l])
        self.cl.append([-v] + lits)
        return v


def implies_sat(schema, NN, Sigma, phi, stats=None):
    keys = list(Sigma) + [phi]
    E = _Enc()
    E.TRUE = E.var(); E.cl.append([E.TRUE])
    consts = {A: sorted({tau[A] for c, _, _ in keys for tau in c if isinstance(tau[A], int)}) for A in schema}
    N = {(r, A): E.var() for r in (0, 1) for A in schema}
    C = {(r, A, c): E.var() for r in (0, 1) for A in schema for c in consts[A]}
    D = {A: E.var() for A in schema}           # t[A] == u[A] (null == null counts as equal)
    P = E.var()                                # second record present
    for A in schema:
        for r in (0, 1):
            if A in NN: E.cl.append([-N[r, A]])
            cs = [C[r, A, c] for c in consts[A]]
            for x, y in itertools.combinations(cs, 2): E.cl.append([-x, -y])
            for x in cs: E.cl.append([-x, -N[r, A]])
        n0, n1 = N[0, A], N[1, A]
        E.cl += [[-n0, -n1, D[A]], [-n0, n1, -D[A]], [n0, -n1, -D[A]]]
        for c in consts[A]:
            a, b = C[0, A, c], C[1, A, c]
            E.cl += [[-a, -b, D[A]], [-a, b, -D[A]], [a, -b, -D[A]]]
    def lit(r, A, s): return -N[r, A] if s == 'T' else N[r, A] if s == 'N' else C[r, A, s]
    def scope(r, cond): return E.OR(E.AND(lit(r, A, s) for A, s in tau.items() if s != '_') for tau in cond)
    def pviol(cls, K):
        if cls == 'pos': return E.AND(E.AND([-N[0, A], D[A]]) for A in K)
        if cls in ('dom', 'cand'): return E.AND(D[A] for A in K)
        if cls == 'part':
            return E.OR([E.AND(E.OR([N[0, A], D[A]]) for A in K), E.AND(E.OR([N[1, A], D[A]]) for A in K)])
        if cls == 'cert': return E.AND(E.OR([N[0, A], N[1, A], D[A]]) for A in K)
        return -E.TRUE
    def violated(key):
        cond, cls, K = key
        s0, s1 = scope(0, cond), E.AND([scope(1, cond), P])
        parts = [E.AND([s0, s1, pviol(cls, K)])]
        if cls in ('cand', 'nn'):
            parts += [E.AND([s0, E.OR(N[0, A] for A in K)]), E.AND([s1, E.OR(N[1, A] for A in K)])]
        return E.OR(parts)
    for s in Sigma: E.cl.append([-violated(s)])
    E.cl.append([violated(phi)])
    with Cadical153(bootstrap_with=E.cl) as S:
        res = S.solve()
    if stats is not None: stats['vars'], stats['clauses'] = E.n, len(E.cl)
    return not res
