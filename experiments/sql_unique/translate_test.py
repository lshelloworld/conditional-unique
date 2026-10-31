"""C:dom(K) is equivalent to {C & p_N : pos(K - N) : N subset of the nullable columns of K}, where
p_N puts IS NULL on N and IS NOT NULL on the other nullable key columns (one partial
nulls-distinct index per null pattern). Checked both ways with implies_sat on random instances,
including multi-template C. Usage: python translate_test.py REPO N"""
import itertools, os, random, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'experiments', 'reasoning'))
from implication import implies_sat


def translate(schema, NN, phi):
    temps, cls, K = phi
    free = sorted(A for A in K if A not in NN)
    out = []
    for r in range(len(free) + 1):
        for Nset in itertools.combinations(free, r):
            ts = []
            for t in temps:
                t2, ok = dict(t), True
                for A in free:
                    want = 'N' if A in Nset else 'T'
                    if t2[A] == '_': t2[A] = want
                    elif want == 'N' and t2[A] != 'N': ok = False
                    elif want == 'T' and t2[A] == 'N': ok = False
                if ok: ts.append(t2)
            if ts: out.append((ts, 'pos', frozenset(K) - set(Nset)))
    return out


def main():
    rng = random.Random(3); n = int(sys.argv[2]); bad = 0
    for _ in range(n):
        m = rng.randint(2, 5); schema = [f'A{j}' for j in range(m)]
        NN = {A for A in schema if rng.random() < 0.3}
        temps = [{A: (rng.choice(['T', 'N', 1, 2]) if rng.random() < 0.3 else '_') for A in schema} for _ in range(rng.randint(1, 3))]
        phi = (temps, 'dom', frozenset(rng.sample(schema, rng.randint(0, min(3, m)))))
        T = translate(schema, NN, phi)
        fwd = all(implies_sat(schema, NN, [phi], s) for s in T)
        bwd = implies_sat(schema, NN, T, phi)
        bad += not (fwd and bwd)
    print(f'{n} instances, {bad} not equivalent')


if __name__ == '__main__':
    main()
