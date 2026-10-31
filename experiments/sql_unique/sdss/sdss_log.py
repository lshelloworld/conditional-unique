"""Collect the SQL that people typed into SkyServer's SQL search form (access
'Skyserver.Search.SQL', error = 0) from the public SkyServer log WebLog..SqlLog, through the
public SQL search web service of DR18 (no login). Only the statement text, its database and
counts are fetched, never client addresses. One request per month, 5 s apart, cached in CACHE.
Statements are de-duplicated across months. Writes sdss_log.json.
Usage: python sdss_log.py CACHE FIRST_MONTH LAST_MONTH   (months as YYYY-MM)"""
import hashlib, json, os, sys, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
URL = 'https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch'
UA = 'conditional-unique-research/1.0'


def fetch(cache, cmd):
    path = os.path.join(cache, hashlib.sha1(cmd.encode()).hexdigest())
    if os.path.exists(path): return open(path, encoding='utf-8').read()
    url = URL + '?' + urllib.parse.urlencode(dict(cmd=cmd, format='json'))
    body = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=600).read().decode('utf-8', 'replace')
    time.sleep(5)
    open(path, 'w', encoding='utf-8').write(body)
    return body


def months(a, b):
    y, m = map(int, a.split('-'))
    while f'{y:04d}-{m:02d}' <= b:
        yield f'{y:04d}-{m:02d}-01', (f'{y + (m == 12):04d}-{m % 12 + 1:02d}-01')
        y, m = y + (m == 12), m % 12 + 1


def main():
    cache, first, last = sys.argv[1:4]
    os.makedirs(cache, exist_ok=True)
    seen = {}
    for a, b in months(first, last):
        body = fetch(cache, f"select sql, dbname, count(*) n from WebLog..SqlLog where access = 'Skyserver.Search.SQL' "
                            f"and error = 0 and theTime >= '{a}' and theTime < '{b}' group by sql, dbname")
        rows = json.loads(body)[0]['Rows']
        for r in rows:
            k = ' '.join(r['sql'].split()).lower()
            e = seen.setdefault(k, dict(sql=r['sql'], dbname=r['dbname'], runs=0, first=a[:7]))
            e['runs'] += r['n']
        print(a[:7], len(rows), 'rows,', len(seen), 'distinct so far', flush=True)
    json.dump(list(seen.values()), open(os.path.join(HERE, 'sdss_log.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
