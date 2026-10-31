"""Summarise results_qo_x*.json into results.md."""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = {'pos': 'possible', 'dom': 'domain', 'part': 'partial', 'cert': 'certain', 'cand': 'candidate'}

def load(f): return json.load(open(os.path.join(HERE, f)))

def main():
    L = ['# Query optimisation with discovered conditional keys (PostgreSQL 18.6)', '']
    runs = [(f, f.split('_x')[1].split('.')[0]) for f in sorted(os.listdir(HERE))
            if f.startswith('results_qo_x') and f.endswith('.json')]
    # correctness: the real-size runs (x1 for Hockey/VOC, xreal for NCVoter/UniProt)
    base = [r for f, sc in runs if sc in ('1', 'real') for r in load(f)]
    L += ['## Cases', '', '| case | table | conditional key | scope predicate |', '|---|---|---|---|']
    seen = set()
    for r in base:
        if r['case'] in seen: continue
        seen.add(r['case'])
        L.append(f"| {r['case']} | {r['table']} | {NAME[r['cls']]}({', '.join(r['K'])}) | `{r['P']}` |")
    L += ['', '## Correctness', '',
          'A rewrite is *licensed* when the class of the conditional key justifies it (DISTINCT and '
          'GROUP BY need a domain key, joins a possible key). *Correct* compares the result multisets '
          'of original and rewritten query; *without P* applies the same rewrite to the query without '
          'the scope predicate, where the key does not hold.', '',
          '| case | class | template | licensed | correct | correct without P |', '|---|---|---|---|---|---|']
    for r in base:
        L.append(f"| {r['case']} | {r['cls']} | {r['template']} | {'yes' if r['licensed'] else 'no'} | "
                 f"{'yes' if r['rewrite_correct'] else '**no**'} | {'yes' if r['rewrite_correct_without_P'] else 'no'} |")
    lic = [r for r in base if r['licensed']]
    L += ['', f"Licensed rewrites correct: {sum(r['rewrite_correct'] for r in lic)}/{len(lic)}. "
          f"Unlicensed (GROUP BY trap) rewrites correct: "
          f"{sum(r['rewrite_correct'] for r in base if not r['licensed'])}/{sum(not r['licensed'] for r in base)}. "
          f"Rewrites still correct without the scope predicate: "
          f"{sum(r['rewrite_correct_without_P'] for r in lic)}/{len(lic)}.", '']
    for f, sc in runs:
        R = load(f)
        title = 'real scale (NCVoter 1,023,993 rows, UniProt 24,173 rows)' if sc == 'real' else f'scale x{sc}'
        L += [f'## Execution time, {title} (median ms; original -> rewritten)', '',
              '| case | template | none | idx | uq (conditional key enforced) | speed-up (uq) | PG avoids it itself (none/idx/uq) |',
              '|---|---|---|---|---|---|---|']
        sp = {}
        for r in R:
            if not r['licensed']: continue
            c = r['configs']
            s = c['uq']['orig_ms'] / max(c['uq']['rew_ms'], 1e-9)
            sp.setdefault(r['template'], []).append(s)
            L.append(f"| {r['case']} | {r['template']} | {c['none']['orig_ms']:.2f} -> {c['none']['rew_ms']:.2f} | "
                     f"{c['idx']['orig_ms']:.2f} -> {c['idx']['rew_ms']:.2f} | {c['uq']['orig_ms']:.2f} -> {c['uq']['rew_ms']:.2f} | "
                     f"{s:.1f}x | {'/'.join('yes' if c[k]['pg_already_removes'] else 'no' for k in ('none', 'idx', 'uq'))} |")
        L += ['', 'Median speed-up of the licensed rewrite with the key enforced (uq), by template: ' +
              ', '.join(f'{k} {statistics.median(v):.1f}x' for k, v in sp.items()) + '.', '']
    open(os.path.join(HERE, 'results.md'), 'w').write('\n'.join(L) + '\n')
    print('wrote results.md')

if __name__ == '__main__':
    main()
