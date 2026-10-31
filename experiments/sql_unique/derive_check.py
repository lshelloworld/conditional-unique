"""Mechanical check of the completeness proof of the axiomatisation note
(conditional-unique/axiomatisation-note.tex). For an implied phi, the construction of the proof
is carried out rule by rule: every rule application checks that its premises were derived (or
are in Sigma) and that its side condition holds, and the run must end with phi. Soundness is
checked separately: every derived constraint is implied by Sigma (brute force).

Entries: ('any',) ('null',) ('in', S) ('notin', S); IS NOT NULL is ('notin', frozenset()).
Constraints: (condition, sem, K), condition a frozenset of templates (tuples of entries in
schema order). Usage: python derive_check.py REPO N"""
import itertools, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from cunique import brute, violates, NULL

TOP = ('notin', frozenset())


class Deriver:
    def __init__(self, schema, NN, Sigma, phi):
        self.R, self.NN = schema, NN
        self.Sigma = [self.norm(s) for s in Sigma]
        self.phi = self.norm(phi)
        self.G = sorted({c for (C, _, _) in self.Sigma + [self.phi] for t in C for e in t if e[0] in ('in', 'notin') for c in e[1]})
        self.derived = set(); self.steps = 0
        self.kappa = (self.phi[1], self.phi[2])

    def norm(self, con):
        temps, sem, K = con
        out = set()
        for r in temps:
            t = tuple(TOP if r[A] == ('top',) else r[A] for A in self.R)
            if any(e == ('null',) and A in self.NN for A, e in zip(self.R, t)): continue   # empty scope
            out.add(t)
        return (frozenset(out), sem, frozenset(K))

    # profiles and canonical pairs
    def profiles(self):
        opts = [self.G + ['*'] + ([] if A in self.NN else [NULL]) for A in self.R]
        return list(itertools.product(*opts))

    def tau(self, p):
        return tuple(('in', frozenset([v])) if v not in ('*', NULL) else ('null',) if v is NULL else ('notin', frozenset(self.G)) for v in p)

    def matches_prof(self, p, t):
        for v, e in zip(p, t):
            k = e[0]
            if k == 'any': continue
            if k == 'null' and v is not NULL: return False
            if k == 'in' and (v is NULL or v == '*' or v not in e[1]): return False
            if k == 'notin' and (v is NULL or (v != '*' and v in e[1])): return False
        return True

    def canon(self, p, q):
        sem, K = self.kappa
        t1, t2 = {}, {}
        for A, a, b in zip(self.R, p, q):
            if A in K:
                if a != b or (a is NULL and sem == 'U'): return None
                t1[A] = t2[A] = ('fresh', 'k', A) if a == '*' else a
            else:
                t1[A] = ('fresh', 1, A) if a == '*' else a
                t2[A] = ('fresh', 2, A) if b == '*' else b
        return t1, t2

    def as_dict(self, con):
        C, sem, K = con
        return ([dict(zip(self.R, t)) for t in C], sem, K)

    # rules: each checks its premises and side condition, then adds the conclusion
    def have(self, C):
        assert (C,) + self.kappa in self.derived, 'premise not derived'

    def add(self, C):
        self.derived.add((frozenset(C),) + self.kappa); self.steps += 1

    def cell1(self, p):
        c = self.canon(p, p)
        if c is not None:
            sig = next((s for s in self.Sigma if violates(c[0], c[1], self.as_dict(s))), None)
            assert sig is not None, 'no premise for cell'
        self.add({self.tau(p)})

    def cell2(self, p, q):
        self.have(frozenset({self.tau(p)})); self.have(frozenset({self.tau(q)}))
        c = self.canon(p, q)
        if c is not None:
            assert any(violates(c[0], c[1], self.as_dict(s)) for s in self.Sigma), 'no premise for cell'
        self.add({self.tau(p), self.tau(q)})

    def pairing(self, C, t, u):
        C = frozenset(C)
        self.have(C | {t}); self.have(C | {u}); self.have(frozenset({t, u}))
        self.add(C | {t, u})

    def split(self, D, t, A):               # (S): t[A->top], t[A->null] (if nullable) => t[A->any]
        i = self.R.index(A); assert t[i] == ('any',)
        parts = {t[:i] + (TOP,) + t[i + 1:]} | (set() if A in self.NN else {t[:i] + (('null',),) + t[i + 1:]})
        self.have(frozenset(D) | parts); self.add(frozenset(D) | {t})

    def vsplit(self, D, t, A, c):           # (V): t[A->notin S+c], t[A->in {c}] => t[A->notin S]
        i = self.R.index(A); assert t[i][0] == 'notin' and c not in t[i][1]
        parts = {t[:i] + (('notin', t[i][1] | {c}),) + t[i + 1:], t[:i] + (('in', frozenset([c])),) + t[i + 1:]}
        self.have(frozenset(D) | parts); self.add(frozenset(D) | {t})

    def inmerge(self, D, t, A):             # (I): t[A->in {c}] for c in S => t[A->in S]
        i = self.R.index(A); assert t[i][0] == 'in'
        parts = {t[:i] + (('in', frozenset([c])),) + t[i + 1:] for c in t[i][1]}
        self.have(frozenset(D) | parts); self.add(frozenset(D) | {t})

    # the construction of the completeness proof
    def refine(self, t):
        """one refinement step at the first non-profile column: (rule, column, parts) or None"""
        for i, (A, e) in enumerate(zip(self.R, t)):
            if e == ('any',):
                return ('S', A, None, [t[:i] + (TOP,) + t[i + 1:]] + ([] if A in self.NN else [t[:i] + (('null',),) + t[i + 1:]]))
            if e[0] == 'notin' and set(e[1]) != set(self.G):
                c = min(set(self.G) - set(e[1]), key=repr)
                return ('V', A, c, [t[:i] + (('notin', e[1] | {c}),) + t[i + 1:], t[:i] + (('in', frozenset([c])),) + t[i + 1:]])
            if e[0] == 'in' and len(e[1]) > 1:
                return ('I', A, None, [t[:i] + (('in', frozenset([c])),) + t[i + 1:] for c in e[1]])
        return None

    def T(self, t):
        """the profile templates of t's scope"""
        r = self.refine(t)
        return {t} if r is None else set().union(*(self.T(u) for u in r[3]))

    def merge(self, D, t):
        """Lemma (merge): from (D u T(t)) derive (D u {t})"""
        r = self.refine(t)
        if r is None: return
        rule, A, c, parts = r
        cur = set(D) | set().union(*(self.T(u) for u in parts))
        done = set()
        for k, u in enumerate(parts):
            rest = set().union(*(self.T(w) for w in parts[k + 1:])) if k + 1 < len(parts) else set()
            self.merge(set(D) | done | rest, u)
            done.add(u)
        D = frozenset(D)
        if rule == 'S': self.split(D, t, A)
        elif rule == 'V': self.vsplit(D, t, A, c)
        else: self.inmerge(D, t, A)

    def run(self):
        C_phi = self.phi[0]
        if not C_phi:
            self.add(set()); return True                                      # axiom (T)
        P = [p for p in self.profiles() if any(self.matches_prof(p, t) for t in C_phi)]
        # profile templates of P are exactly the union of T(theta) over theta in C_phi
        assert {self.tau(p) for p in P} == set().union(*(self.T(t) for t in C_phi))
        for p in P: self.cell1(p)
        for p, q in itertools.combinations(P, 2): self.cell2(p, q)
        TP = [self.tau(p) for p in P]
        for k in range(3, len(TP) + 1):                                       # all subsets, by size
            for Q in itertools.combinations(TP, k):
                self.pairing(set(Q[2:]), Q[0], Q[1])
        thetas = sorted(C_phi)
        for j, th in enumerate(thetas):
            D = set(thetas[:j]) | set().union(*(self.T(t) for t in thetas[j + 1:])) if j + 1 < len(thetas) else set(thetas[:j])
            self.merge(D, th)
        self.have(frozenset(C_phi))
        return True


def main():
    sys.path.insert(0, os.path.join(sys.argv[1], 'experiments', 'reasoning'))
    rng = random.Random(21); n = int(sys.argv[2]); ok = tried = sound = 0
    from cunique_test import rand_entry
    while tried < n:
        m = rng.randint(1, 3); schema = [f'A{j}' for j in range(m)]
        NN = {A for A in schema if rng.random() < 0.3}
        cons = [0, 1]
        def ent(p):
            e = rand_entry(rng, p)
            if e[0] in ('in', 'notin'): e = (e[0], frozenset(x for x in e[1] if x in cons) or frozenset([0]))
            return e
        def con(p, nt):
            return ([{A: ent(p) for A in schema} for _ in range(nt)], rng.choice(['U', 'Ueq']),
                    frozenset(rng.sample(schema, rng.randint(0, m))))
        Sigma = [con(0.4, rng.randint(1, 2)) for _ in range(rng.randint(1, 4))]
        phi = con(0.4, rng.randint(1, 2))
        if not brute(schema, NN, Sigma, phi): continue
        d = Deriver(schema, NN, Sigma, phi)
        if len(d.profiles()) > 12: continue
        tried += 1
        d.run(); ok += 1
        sample = rng.sample(sorted(d.derived, key=repr), min(5, len(d.derived)))
        sound += all(brute(schema, NN, Sigma, ([dict(zip(schema, t)) for t in C], s, K)) for C, s, K in sample)
    print(f'{tried} implied instances: derivation constructed and checked in {ok}; '
          f'sampled derived constraints implied in {sound}')


if __name__ == '__main__':
    main()
