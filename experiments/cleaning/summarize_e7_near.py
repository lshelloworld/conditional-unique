"""Summarise results_e7_near.json: per error kind, macro-averages over keys of precision (keys on
which all detectors flag something), recall, and false positives per error found."""
import json, os, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, 'results_e7_near.json')))
D = ['CK', 'UK', 'CFD']
L = ['# E7 with near-holding keys, errors anywhere (3 seeds)', '',
     '| errors | keys (common) | ' + ' | '.join(f'{d} P / R / FP per error found' for d in D) + ' |', '|---|---|---|---|---|']
for kind in ('dup', 'mixed'):
    rows = [r for r in R if r['kind'] == kind]
    com = [r for r in rows if all(r['results'][d]['P'] is not None for d in D)]
    cells = []
    for d in D:
        P = statistics.mean(r['results'][d]['P'] for r in com)
        Rc = statistics.mean(r['results'][d]['R'] for r in rows)
        fp = sum(r['results'][d]['flagged'] - r['results'][d]['ok'] for r in rows)
        hit = sum(r['results'][d]['hit'] for r in rows)
        cells.append(f'{P:.2f} / {Rc:.2f} / {fp / hit:.3f}')
    L.append(f'| {kind} | {len(rows)} ({len(com)}) | ' + ' | '.join(cells) + ' |')
better = [r for r in R if r['kind'] == 'dup' and r['results']['CK']['P'] - r['results']['UK']['P'] >= 0.05]
L += ['', f"Keys where the condition raises precision by at least 0.05 (duplicates): {len(better)} of "
      f"{sum(r['kind'] == 'dup' for r in R)}: " + ', '.join(f"{r['case']} {r['results']['UK']['P']:.2f}->{r['results']['CK']['P']:.2f}" for r in better), '',
      '## Per key', '', '| key | class | condition | errors | CK P/R | UK P/R | CFD P/R |', '|---|---|---|---|---|---|---|']
for r in R:
    g = lambda d: f"{r['results'][d]['P'] if r['results'][d]['P'] is not None else '-'}/{r['results'][d]['R']}"
    L.append(f"| {r['case']} ({', '.join(r['K'])}) | {r['cls']} | `{r['sql']}` | {r['kind']} | {g('CK')} | {g('UK')} | {g('CFD')} |")
open(os.path.join(HERE, 'results_e7_near.md'), 'w').write('\n'.join(L) + '\n')
print('\n'.join(L[:8]))
