"""E2: cost of implication. Algorithm 1 (canonical counterexamples) against a SAT baseline.

Schema: 30 columns; c0..c9 are nullable condition columns with four constants each, k0..k19
key columns, half of them nullable. Sigma: random conditional keys whose templates have one or
two atoms (constant, top or null) on condition columns, classes uniform, keys of 1-4 columns.
Targets: half are weakenings of a member of Sigma (weaker class, more precise condition,
superkey), half random; every target template fixes the nullness of the relevant nullable
columns except m of them, so that b = 2m. Varied: |Sigma|, b, and the number of templates |C|
of the target. Writes results_e2.json."""
import json, os, random, statistics, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from implication import Checker, implies_canonical, implies_sat, _relevant

CONDC = ['c%d' % i for i in range(10)]
KEYC = ['k%d' % i for i in range(20)]
SCH = CONDC + KEYC
NN = set(KEYC[::2])
CLS = ['pos', 'dom', 'part', 'cert', 'cand', 'nn']
WEAKER = {'cand': ['cand', 'cert', 'part', 'dom', 'pos'], 'cert': ['cert', 'part', 'dom', 'pos'],
          'part': ['part', 'dom', 'pos'], 'dom': ['dom', 'pos'], 'pos': ['pos'], 'nn': ['nn']}


def rtemplate(rng):
    t = {A: '_' for A in SCH}
    for A in rng.sample(CONDC, rng.choice([1, 2])):
        t[A] = rng.choice(['T', 'N', 0, 1, 2, 3])
    return t


def rkey(rng):
    return ([rtemplate(rng) for _ in range(rng.choice([1, 1, 2, 3]))], rng.choice(CLS),
            frozenset(rng.sample(KEYC, rng.randint(1, 4))))


def close(tau, rel, m, rng):
    """fix the nullness of all open relevant columns of tau except m of them"""
    t = dict(tau)
    open_ = [A for A in SCH if t[A] == '_' and A in rel and A not in NN]
    keep = set(rng.sample(open_, min(m, len(open_))))
    for A in open_:
        if A not in keep: t[A] = rng.choice(['T', 'N'])
    return t


def target(rng, Sig, m, ntemp):
    if rng.random() < .5:
        cond, cls, K = rng.choice(Sig)
        cls = rng.choice(WEAKER[cls])
        K = K | set(rng.sample(KEYC, rng.randint(0, 1))) if cls != 'nn' else K
        base = [dict(rng.choice(cond)) for _ in range(ntemp)]
        for t in base:
            for A in rng.sample(CONDC, 1):
                if t[A] == '_': t[A] = rng.choice(['T', 0, 1])
    else:
        _, cls, K = rkey(rng)
        base = [rtemplate(rng) for _ in range(ntemp)]
    rel = _relevant(SCH, Sig, K)
    return ([close(t, rel, m, rng) for t in base], cls, frozenset(K))


def run(nsig, m, ntemp, n=40, seed=0, sat=True):
    rng = random.Random(hash((nsig, m, ntemp, seed)) & 0xffffffff)
    Sig = [rkey(rng) for _ in range(nsig)]
    chk = Checker(SCH, Sig)
    out = []
    for _ in range(n):
        phi = target(rng, Sig, m, ntemp)
        st = {}
        t0 = time.perf_counter(); a = implies_canonical(SCH, NN, Sig, phi, chk=chk, stats=st)
        ta = time.perf_counter() - t0
        r = dict(implied=a, alg_ms=ta * 1e3, objects=st['objects'])
        if sat:
            st2 = {}
            t0 = time.perf_counter(); s = implies_sat(SCH, NN, Sig, phi, stats=st2)
            r.update(sat_ms=(time.perf_counter() - t0) * 1e3, agree=a == s, clauses=st2['clauses'])
        out.append(r)
    return out


def summary(rs):
    g = lambda k, imp: [r[k] for r in rs if r['implied'] == imp and k in r]
    md = lambda v: round(statistics.median(v), 2) if v else None
    mx = lambda v: round(max(v), 2) if v else None
    return dict(n=len(rs), implied=sum(r['implied'] for r in rs),
                alg_med_impl=md(g('alg_ms', True)), alg_max_impl=mx(g('alg_ms', True)),
                alg_med_non=md(g('alg_ms', False)),
                sat_med_impl=md(g('sat_ms', True)), sat_max_impl=mx(g('sat_ms', True)),
                sat_med_non=md(g('sat_ms', False)),
                objects_max=max(r['objects'] for r in rs),
                agree=all(r.get('agree', True) for r in rs))


if __name__ == '__main__':
    R = {}
    for nsig in (10, 100, 1000, 10000):
        R[f'sigma={nsig}'] = summary(run(nsig, 2, 1)); print('sigma', nsig, R[f'sigma={nsig}'], flush=True)
    for m in (0, 2, 4, 6, 8):
        R[f'b={2 * m}'] = summary(run(100, m, 1)); print('b', 2 * m, R[f'b={2 * m}'], flush=True)
    for nt in (1, 2, 4, 8):
        R[f'C={nt}'] = summary(run(100, 1, nt)); print('C', nt, R[f'C={nt}'], flush=True)
    json.dump(R, open(os.path.join(HERE, 'results_e2.json'), 'w'), indent=1)
