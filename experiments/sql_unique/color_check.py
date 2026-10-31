# Brute-force check of the 3-colouring reduction: NOT NULL columns A_u (per vertex) and B;
# goal {<>}:U(B); per edge uv and colour c a premise {<A_u: notin{c}, A_v: notin{c}>}:U(B).
# Sigma |= goal iff no violating pair, i.e. iff G is not 3-colourable.
import itertools, random
def colourable(n, E):
    return any(all(col[u]!=col[v] for u,v in E) for col in itertools.product(range(3), repeat=n))
def violating_pair_exists(n, E, dom=range(5)):
    # pair shares B; A_u values from dom (0..2 colours, 3,4 fresh)
    for a in itertools.product(dom, repeat=n):
        for b in itertools.product(dom, repeat=n):
            # premise {A_u notin c, A_v notin c}:U(B) violated iff both records avoid c on A_u and A_v
            ok = all(not (a[u]!=c and b[u]!=c and a[v]!=c and b[v]!=c) for u,v in E for c in range(3))
            if ok: return True
    return False
random.seed(1)
for n in range(2,5):
    for _ in range(40):
        E=[(u,v) for u in range(n) for v in range(u+1,n) if random.random()<0.7]
        assert colourable(n,E) == violating_pair_exists(n,E), (n,E)
print('ok')
