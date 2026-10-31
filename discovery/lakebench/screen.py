"""Screen zip members for conditional-key structure from their first bytes only.
For a random sample of members, fetch the first 32 KB of the compressed stream, inflate what it
holds, parse the CSV header and rows, and score: a low-cardinality scope column (2-20 values,
e.g. status/type/flag), NULLs present but not dominant, an identifier-like column (nearly all
values distinct), estimated rows >= 1,000 and uncompressed size <= 60 MB.
Usage: screen.py URL LISTING.json N SEED OUT.json"""
import csv, io, json, random, struct, sys, zlib
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from remotezip import fetch

NULLS = {'', 'na', 'n/a', 'null', 'none', 'nan', '-'}


def head(url, e, nbytes=32768):
    h = fetch(url, e['offset'], e['offset'] + 29)
    nlen, xlen = struct.unpack('<HH', h[26:30])
    start = e['offset'] + 30 + nlen + xlen
    raw = fetch(url, start, start + min(nbytes, e['csize']) - 1)
    if e['method'] == 0: return raw
    return zlib.decompressobj(-15).decompress(raw)


def score(e, text):
    lines = text.decode('utf-8', 'replace').splitlines()[:-1]          # last line may be cut
    if len(lines) < 30: return None
    try:
        rows = list(csv.reader(io.StringIO('\n'.join(lines))))
    except csv.Error:
        return None
    hdr, body = rows[0], [r for r in rows[1:] if len(r) == len(rows[0])]
    if len(hdr) < 4 or len(body) < 30: return None
    n = len(body)
    cols = list(zip(*body))
    nullfr = [sum(v.strip().lower() in NULLS for v in c) / n for c in cols]
    distinct = [len({v for v in c if v.strip().lower() not in NULLS}) for c in cols]
    scope = [hdr[i] for i in range(len(hdr)) if 2 <= distinct[i] <= 20 and nullfr[i] < 0.5]
    ident = [hdr[i] for i in range(len(hdr)) if distinct[i] >= 0.95 * n * (1 - nullfr[i]) and nullfr[i] < 0.5]
    partial_null = sum(0.05 <= f <= 0.8 for f in nullfr)
    est_rows = int(e['usize'] / max(1, len(text) / max(1, n + 1)))
    ok = scope and ident and partial_null >= 1 and est_rows >= 1000 and e['usize'] <= 60e6
    s = (len(scope) > 0) + (len(ident) > 0) + min(partial_null, 3) / 3 + (len(hdr) >= 8)
    return dict(name=e['name'], cols=len(hdr), est_rows=est_rows, usize=e['usize'], scope=scope[:6],
                ident=ident[:4], partial_null_cols=partial_null, ok=bool(ok), score=round(s, 2), header=hdr[:30])


def main():
    url = open(sys.argv[1]).read().strip()
    es = [e for e in json.load(open(sys.argv[2])) if e['name'].lower().endswith('.csv') and e['usize'] > 0]
    random.Random(int(sys.argv[4])).shuffle(es)
    es = es[:int(sys.argv[3])]
    def one(e):
        try: return score(e, head(url, e))
        except Exception as ex: return dict(name=e['name'], error=str(ex)[:100])
    with ThreadPoolExecutor(12) as ex:
        res = [r for r in ex.map(one, es) if r]
    json.dump(res, open(sys.argv[5], 'w'), indent=1)
    good = [r for r in res if r.get('ok')]
    print(len(es), 'screened,', len(res), 'parsed,', len(good), 'promising,', sum('error' in r for r in res), 'errors')


if __name__ == '__main__':
    main()
