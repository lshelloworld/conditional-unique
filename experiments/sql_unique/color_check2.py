# IN-list variant: goal entries A_u in {0,1,2}; premise per edge uv, colour c: {A_u in S_c, A_v in S_c}:U(B), S_c={0,1,2}\{c}
import itertools, random
def colourable(n, E):
    return any(all(col[u]!=col[v] for u,v in E) for col in itertools.product(range(3), repeat=n))
def viol(n, E):
    for a in itertools.product(range(3), repeat=n):          # goal forces values in {0,1,2}
        for b in itertools.product(range(3), repeat=n):
            if all(not all(x!=c for x in (a[u],b[u],a[v],b[v])) for u,v in E for c in range(3)): return True
    return False
random.seed(2)
for n in range(2,5):
    for _ in range(40):
        E=[(u,v) for u in range(n) for v in range(u+1,n) if random.random()<0.7]
        assert colourable(n,E)==viol(n,E),(n,E)
print('ok')
