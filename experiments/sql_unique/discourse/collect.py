"""X11: collect Discourse Data Explorer queries (read only, throttled).

Sources: the built-in queries of discourse-data-explorer (lib/discourse_data_explorer/queries.rb);
meta.discourse.org topics tagged sql-query and topics of the data-reporting category (148),
whose posts are read as markdown through /raw/<topic_id>; SidVal's collected list (querys.md and the .sql files it links).
From every source the fenced code blocks that look like SQL are kept, with their origin URL.
Writes queries_raw.json (cache: the fetched pages in CACHE). Usage: python collect.py CACHE"""
import hashlib, json, os, re, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
META = 'https://meta.discourse.org'
UA = 'conditional-unique-research-crawler/1.0'
CACHE = sys.argv[1]


def get(url):
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())
    if os.path.exists(path): return open(path, encoding='utf-8').read()
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
            body = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
            break
        except urllib.error.HTTPError as ex:
            if ex.code == 429: time.sleep(30 * (attempt + 1)); continue
            if ex.code in (403, 404, 410): body = ''; break
            raise
    time.sleep(1.5)
    open(path, 'w', encoding='utf-8').write(body)
    return body


def topic_ids(first):
    ids, url = {}, META + first
    while url:
        d = json.loads(get(url) or '{}').get('topic_list', {})
        for t in d.get('topics', []): ids[t['id']] = t['title']
        nxt = d.get('more_topics_url')
        url = META + nxt.replace('?', '.json?', 1) if nxt and '.json' not in nxt else (META + nxt if nxt else None)
    return ids


SQLISH = re.compile(r'^\s*(--|with\b|select\b|\(?\s*select\b)', re.I | re.S)


def blocks(md):
    for m in re.finditer(r'```[ \t]*(\w*)[^\n]*\n(.*?)```', md, re.S):
        lang, code = m.group(1).lower(), m.group(2)
        if lang in ('sql', 'pgsql', 'postgresql', 'psql') or (lang in ('', 'text') and SQLISH.match(code) and re.search(r'\bselect\b', code, re.I)):
            yield code.strip()


def main():
    os.makedirs(CACHE, exist_ok=True)
    out = []
    rb = get('https://raw.githubusercontent.com/discourse/discourse-data-explorer/main/lib/discourse_data_explorer/queries.rb')
    for m in re.finditer(r'queries\["([\w-]+)"\]\["sql"\]\s*=\s*<<~SQL\n(.*?)\n\s*SQL', rb, re.S):
        out.append(dict(source='builtin', origin=f'queries.rb#{m.group(1)}', sql=m.group(2).strip()))
    sid = get('https://raw.githubusercontent.com/SidVal/discourse-data-explorer/queries/querys.md')
    for i, b in enumerate(blocks(sid)):
        out.append(dict(source='sidval', origin=f'querys.md#{i}', sql=b))
    for f in sorted(set(re.findall(r'github\.com/SidVal/discourse-data-explorer/blob/queries/(queries/[\w./-]+\.sql)', sid))):
        code = get(f'https://raw.githubusercontent.com/SidVal/discourse-data-explorer/queries/{f}')
        if code.strip(): out.append(dict(source='sidval', origin=f, sql=code.strip()))
    ids = topic_ids('/tag/sql-query.json')
    ids.update(topic_ids('/c/148.json'))
    print(len(ids), 'topics', flush=True)
    for n, (tid, title) in enumerate(sorted(ids.items())):
        md = get(f'{META}/raw/{tid}')
        for i, b in enumerate(blocks(md)):
            out.append(dict(source='meta', origin=f'{META}/t/{tid}', title=title, sql=b))
        if n % 50 == 0: print(n, len(out), flush=True)
    json.dump(out, open(os.path.join(HERE, 'queries_raw.json'), 'w'), indent=1)
    from collections import Counter
    print(Counter(q['source'] for q in out), flush=True)


if __name__ == '__main__':
    main()
