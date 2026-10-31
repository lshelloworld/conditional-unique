"""Collect the SQL that users of a MusicBrainz database copy post on the MetaBrainz community forum
(community.metabrainz.org, a Discourse forum), read only and throttled.

Topics come from Discourse searches for SQL over the MusicBrainz schema (SEARCHES, all result
pages); each topic is read as markdown through /raw/<id>, and its fenced code blocks that look like
a SELECT over MusicBrainz tables are kept with their URL. Requests carry a generic crawler name,
1.5 s apart, cached in CACHE. Writes forum_queries.json. Usage: python mb_forum.py CACHE"""
import hashlib, json, os, re, sys, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://community.metabrainz.org'
UA = 'conditional-unique-research-crawler/1.0'
SEARCHES = ['select from artist', 'select from release', 'select from recording', 'artist_alias',
            'release_group_alias', 'primary_for_locale', 'musicbrainz sql query', 'select count musicbrainz',
            'join artist_credit_name', 'psql musicbrainz select', 'select distinct musicbrainz',
            'group by musicbrainz', 'left join musicbrainz', 'l_artist_artist', 'select from work']
TABLES = re.compile(r'\b(artist|artist_alias|artist_credit|artist_credit_name|release|release_group|recording|'
                    r'track|medium|label|work|area|place|event|instrument|series|url|l_\w+|link|link_type|'
                    r'\w+_alias|\w+_tag|isrc|iswc|release_label|release_country)\b', re.I)


def get(cache, url):
    path = os.path.join(cache, hashlib.sha1(url.encode()).hexdigest())
    if os.path.exists(path): return open(path, encoding='utf-8').read()
    body = ''
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
            body = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace'); break
        except urllib.error.HTTPError as ex:
            if ex.code == 429: time.sleep(30 * (attempt + 1)); continue
            if ex.code in (403, 404, 410): break
            raise
    time.sleep(1.5)
    open(path, 'w', encoding='utf-8').write(body)
    return body


def blocks(md):
    for m in re.finditer(r'```[ \t]*(\w*)[^\n]*\n(.*?)```', md, re.S):
        code = m.group(2)
        if re.search(r'\bselect\b', code, re.I) and re.search(r'\bfrom\b', code, re.I) and TABLES.search(code):
            yield code.strip()


def main():
    cache = sys.argv[1]
    os.makedirs(cache, exist_ok=True)
    topics = {}
    for q in SEARCHES:
        for page in range(1, 11):
            d = json.loads(get(cache, f'{SITE}/search.json?q={urllib.parse.quote(q)}&page={page}') or '{}')
            for t in d.get('topics', []): topics[t['id']] = t['title']
            if not d.get('grouped_search_result', {}).get('more_full_page_results'): break
    print(len(topics), 'topics', flush=True)
    out = []
    for tid, title in sorted(topics.items()):
        for b in blocks(get(cache, f'{SITE}/raw/{tid}')):
            out.append(dict(origin=f'{SITE}/t/{tid}', title=title, sql=b))
    json.dump(out, open(os.path.join(HERE, 'forum_queries.json'), 'w'), indent=1)
    print(len(out), 'SQL blocks from', len({q['origin'] for q in out}), 'topics', flush=True)


if __name__ == '__main__':
    main()
