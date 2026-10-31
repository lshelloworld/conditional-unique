"""Tests for fixc.py against brute force: (1) FixC on random tables (nulls, duplicates, both
semantics, random conditions with =, <>, IN, NOT IN, IS [NOT] NULL, one or two templates, with
and without a key-size bound): the minimal keys equal those found by checking every subset of
columns with cunique.violates; (2) DiscA equals FixC run from scratch on every template.
Usage: python fixc_test.py N"""
import itertools, random, sys
from cunique import violates
from fixc import fixc, disca


def holds(rows, con):
    return not any(violates(rows[i], rows[j], con) for i in range(len(rows)) for j in range(len(rows)) if i != j)


def brute(rows, cols, C, sem, kmax):
    keys = [frozenset(K) for k in range(len(cols) + 1) for K in itertools.combinations(cols, k)
            if holds(rows, (C, sem, frozenset(K)))]
    mins = [K for K in keys if not any(L < K for L in keys)]
    return sorted([K for K in mins if kmax is None or len(K) <= kmax], key=lambda k: (len(k), sorted(k)))


def main():
    rng = random.Random(8); n = int(sys.argv[1]); bad = 0; nonempty = 0
    for _ in range(n):
        m = rng.randint(1, 5); cols = [f'A{j}' for j in range(m)]
        dom = [0, 1, 2, None][:rng.randint(2, 4)]
        rows = [{A: rng.choice(dom) for A in cols} for _ in range(rng.randint(0, 12))]
        def ent():
            k = rng.choice(['any', 'any', 'any', 'null', 'in', 'notin'])
            if k in ('any', 'null'): return (k,)
            return (k, frozenset(rng.sample([0, 1, 2], rng.randint(0 if k == 'notin' else 1, 2))))
        C = [{A: ent() for A in cols} for _ in range(rng.randint(1, 2))]
        sem = rng.choice(['U', 'Ueq']); kmax = rng.choice([None, None, 1, 2])
        got, _ = fixc(rows, cols, C, sem, kmax)
        want = brute(rows, cols, C, sem, kmax)
        bad += got != want; nonempty += bool(want) and want != [frozenset()]
    print(f'FixC: {n} instances ({nonempty} with a non-empty minimal key), {bad} mismatches with brute force')
    bad = tot = 0
    for _ in range(max(1, n // 10)):
        m = rng.randint(1, 4); cols = [f'A{j}' for j in range(m)]
        rows = [{A: rng.choice([0, 1, None]) for A in cols} for _ in range(rng.randint(2, 10))]
        sem = rng.choice(['U', 'Ueq'])
        res = disca(rows, cols, 2, sem)
        for key, ks in res.items():
            tpl = {A: ('any',) for A in cols}
            for A, e in key: tpl[A] = e
            tot += 1; bad += ks != fixc(rows, cols, [tpl], sem)[0]
    print(f'DiscA: {tot} templates, {bad} mismatches with FixC from scratch')


if __name__ == '__main__':
    main()
