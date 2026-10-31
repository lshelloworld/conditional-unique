"""Odd cycles of binary partial keys: (1) a 4-ary derivation of the certain key on all columns
through conditions with top entries; (2) the facts used in the non-axiomatisability proof for
conditions built from bottom and constants only."""
import sys, itertools; sys.path.insert(0, sys.argv[1])
from ck import *
def implies(sch, NN, S, p): return canonical_counterexample(sch, NN, S, p) is None  # validated = brute force

def cycle(n):
    V = ['A%d' % i for i in range(n)]
    E = [frozenset([V[i], V[(i + 1) % n]]) for i in range(n)]
    one = {A: '_' for A in V}
    return V, [([one], 'part', e) for e in E], one

def top(V, *cols):
    t = {A: '_' for A in V}; t.update({c: 'T' for c in cols}); return t

if __name__ == "__main__":
  for n in (5, 7, 9):
      V, Sig, one = cycle(n); NN = set(); ok = True
      pk = lambda i: Sig[i % n]
      full = frozenset(V)
      # start: two edges imply {(A_j:T)}:cert(V)
      for j in range(n):
          ok &= implies(V, NN, [pk(j - 1), pk(j)], ([top(V, V[j])], 'cert', full))
      # chain: three edges and {(A_{i+2}:T),(A_j:T)}:cert(V) imply {(A_i:T),(A_j:T)}:cert(V)
      for i in range(n):
          for j in range(n):
              prem = [pk(i - 1), pk(i), pk(i + 1),
                      ([top(V, V[(i + 2) % n]), top(V, V[j])], 'cert', full)]
              ok &= implies(V, NN, prem, ([top(V, V[i]), top(V, V[j])], 'cert', full))
      # final: delta* and one edge imply the unconditional certain key
      delta = ([top(V, A) for A in V], 'cert', full)
      ok &= implies(V, NN, [delta, pk(0)], ([one], 'cert', full))
      # sanity: no proper subset of the cycle implies the target
      ok &= not implies(V, NN, Sig[1:], ([one], 'cert', full))
      # facts for the constants-only proof: unconditional keys implied by the cycle
      for r in range(n + 1):
          for K in itertools.combinations(V, r):
              K = frozenset(K); has_edge = any(e <= K for e in [s[2] for s in Sig])
              for cls in ('pos', 'dom', 'part'):
                  ok &= implies(V, NN, Sig, ([one], cls, K)) == has_edge
              ok &= implies(V, NN, Sig, ([one], 'cert', K)) == (K == full)
              for cls in ('cand', 'nn'):
                  ok &= implies(V, NN, Sig, ([one], cls, K)) == (cls == 'nn' and not K)  # nn(empty) is valid
      print('n =', n, 'all checks pass:', ok)
