"""Summarise results_e6b.json into results_e6b.md (per table and per query kind)."""
import json, os, statistics
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, 'results_e6b.json')))
L = ['# E6b: rewrites decided by implication from a catalog of filtered indexes', '',
     '| table | rows | catalog | queries | full | full wrong | single | UNIQUE | UNIQUE wrong | correct, not licensed | impl. ms (median/max) | speed-up DISTINCT / LEFT JOIN (median) |',
     '|---|---|---|---|---|---|---|---|---|---|---|---|']
tot = defaultdict(int); allms = []; kinds = defaultdict(lambda: defaultdict(int)); sp = defaultdict(list)
for name, t in R.items():
    rs = t['results']
    f = [r for r in rs if r['full']]
    ms = [r['ms'] for r in rs]; allms += ms
    s = {tm: [r['orig_ms'] / max(r['rew_ms'], 1e-6) for r in f if r['template'] == tm] for tm in ('DISTINCT', 'LEFTJOIN')}
    for tm, v in s.items(): sp[tm] += v
    row = dict(queries=len(rs), full=len(f), full_wrong=sum(not r['correct'] for r in f),
               single=sum(r['single'] for r in rs), unique=sum(r['unique'] for r in rs),
               unique_wrong=sum(r['unique'] and not r['correct'] for r in rs),
               missed=sum(r['correct'] and not r['full'] for r in rs))
    for k, v in row.items(): tot[k] += v
    for r in rs:
        k = kinds[(r['kind'], r['template'])]
        k['n'] += 1; k['full'] += r['full']; k['single'] += r['single']; k['unique'] += r['unique']
        k['unique_wrong'] += r['unique'] and not r['correct']; k['correct'] += r['correct']
    md = lambda v: f'{statistics.median(v):.1f}x' if v else '-'
    L.append(f"| {name} | {t['rows']} | {t['catalog']} | {row['queries']} | {row['full']} | {row['full_wrong']} | {row['single']} | "
             f"{row['unique']} | {row['unique_wrong']} | {row['missed']} | {statistics.median(ms):.1f} / {max(ms):.1f} | "
             f"{md(s['DISTINCT'])} / {md(s['LEFTJOIN'])} |")
L += ['', 'Totals: ' + ', '.join(f'{k} {v}' for k, v in tot.items()) +
      f". Implication time over all queries: median {statistics.median(allms):.1f} ms, max {max(allms):.1f} ms. "
      f"Median speed-up of licensed rewrites: DISTINCT {statistics.median(sp['DISTINCT']):.1f}x, LEFT JOIN {statistics.median(sp['LEFTJOIN']):.1f}x.", '',
      '## By query kind', '', '| kind | template | queries | correct | full | single | UNIQUE | UNIQUE wrong |', '|---|---|---|---|---|---|---|---|']
for (kd, tm), v in sorted(kinds.items()):
    L.append(f"| {kd} | {tm} | {v['n']} | {v['correct']} | {v['full']} | {v['single']} | {v['unique']} | {v['unique_wrong']} |")
open(os.path.join(HERE, 'results_e6b.md'), 'w').write('\n'.join(L) + '\n')
print('\n'.join(L))
