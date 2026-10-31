"""Pool results_e7.json (micro-averages over keys and seeds) into results_e7.md and a LaTeX table body."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = sys.argv[1] if len(sys.argv) > 1 else 'results_e7'     # e.g. results_e7_anywhere
R = json.load(open(os.path.join(HERE, NAME + '.json')))
KINDS = ['dup', 'partial', 'missing', 'mixed']
CL = ['pos', 'dom', 'part', 'cert', 'cand']

def pool(rows, det):
    ok = fl = hit = ne = 0
    for r in rows:
        d = r['results'][det(r)]
        ok += d['ok']; fl += d['flagged']; hit += d['hit']; ne += d['errors']
    return (ok / fl if fl else None), (hit / ne if ne else None)

def macro(rows, det):
    """each key counts once: mean of per-key precision (where something was flagged) and recall"""
    ps = [r['results'][det(r)]['P'] for r in rows if r['results'][det(r)]['P'] is not None]
    rs = [r['results'][det(r)]['R'] for r in rows if r['results'][det(r)]['R'] is not None]
    return (sum(ps) / len(ps) if ps else None), (sum(rs) / len(rs) if rs else None)

def f(x): return '--' if x is None else f'{x:.2f}'

lines = [f'# E7: cleaning with discovered conditional keys ({NAME})', '']
lines += ['## Precision over the keys on which CK, UK and CFD all flag something (used in the paper); recall over all keys', '',
          '| error type | keys (common) | CK P/R | UK P/R | CFD P/R |', '|---|---|---|---|---|']
for k in KINDS:
    rows = [r for r in R if r['kind'] == k]
    D = lambda r: ['CK-' + r['cls'], 'UK-' + r['cls'], 'CFD']
    com = [r for r in rows if all(r['results'][d]['P'] is not None for d in D(r))]
    cells = []
    for i in range(3):
        P = sum(r['results'][D(r)[i]]['P'] for r in com) / len(com) if com else None
        Rc = sum(r['results'][D(r)[i]]['R'] for r in rows) / len(rows)
        cells.append(f'{f(P)}/{f(Rc)}')
    lines.append(f'| {k} | {len(rows)} ({len(com)}) | ' + ' | '.join(cells) + ' |')
lines += ['']
lines += ['## Macro-average over keys (each key counts once): discovered class, unconditional, CFD', '',
          '| error type | keys | CK (discovered class) P/R | UK (same class) P/R | CFD P/R |', '|---|---|---|---|---|']
for k in KINDS:
    rows = [r for r in R if r['kind'] == k]
    a = macro(rows, lambda r: 'CK-' + r['cls']); b = macro(rows, lambda r: 'UK-' + r['cls']); c = macro(rows, lambda r: 'CFD')
    lines.append(f'| {k} | {len(rows)} | {f(a[0])}/{f(a[1])} | {f(b[0])}/{f(b[1])} | {f(c[0])}/{f(c[1])} |')
lines += ['', '## Macro-average over keys: class of the conditional key (same condition)', '',
          '| error type | ' + ' | '.join(f'CK-{c} P/R' for c in CL) + ' |', '|---|' + '---|' * len(CL)]
for k in KINDS:
    rows = [r for r in R if r['kind'] == k]
    lines.append(f'| {k} | ' + ' | '.join('/'.join(map(f, macro(rows, lambda r, c=c: 'CK-' + c))) for c in CL) + ' |')
lines += ['', '# Pooled counts (micro-average; dominated by the large NCVoter error sets)', '']
lines += ['## Discovered class: conditional vs. unconditional vs. CFD', '',
          '| error type | keys | CK (discovered class) P/R | UK (same class) P/R | CFD P/R |', '|---|---|---|---|---|']
tex = []
for k in KINDS:
    rows = [r for r in R if r['kind'] == k]
    a = pool(rows, lambda r: 'CK-' + r['cls']); b = pool(rows, lambda r: 'UK-' + r['cls']); c = pool(rows, lambda r: 'CFD')
    lines.append(f'| {k} | {len(rows)} | {f(a[0])}/{f(a[1])} | {f(b[0])}/{f(b[1])} | {f(c[0])}/{f(c[1])} |')
lines += ['', '## Class of the conditional key (same condition), pooled over all keys', '',
          '| error type | ' + ' | '.join(f'CK-{c} P/R' for c in CL) + ' |', '|---|' + '---|' * len(CL)]
for k in KINDS:
    rows = [r for r in R if r['kind'] == k]
    lines.append(f'| {k} | ' + ' | '.join('/'.join(map(f, pool(rows, lambda r, c=c: 'CK-' + c))) for c in CL) + ' |')
lines += ['', '## Unconditional key of each class, pooled', '',
          '| error type | ' + ' | '.join(f'UK-{c} P/R' for c in CL) + ' |', '|---|' + '---|' * len(CL)]
for k in KINDS:
    rows = [r for r in R if r['kind'] == k]
    lines.append(f'| {k} | ' + ' | '.join('/'.join(map(f, pool(rows, lambda r, c=c: 'UK-' + c))) for c in CL) + ' |')
lines += ['', '## Per key (mixed errors)', '', '| key | class | CK P/R | UK P/R | CFD P/R |', '|---|---|---|---|---|']
for r in R:
    if r['kind'] != 'mixed': continue
    g = lambda d: f"{f(r['results'][d]['P'])}/{f(r['results'][d]['R'])}"
    lines.append(f"| {r['case']} {r['table']}({', '.join(r['K'])}) | {r['cls']} | {g('CK-' + r['cls'])} | {g('UK-' + r['cls'])} | {g('CFD')} |")
open(os.path.join(HERE, NAME + '.md'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
