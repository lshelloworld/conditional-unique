"""Extract the SQL that ListenBrainz runs against a MusicBrainz database, statically.

Reads the Python sources of listenbrainz-server (mbid_mapping/, listenbrainz/db/) with the ast
module -- nothing is imported or executed -- and keeps every string or f-string literal that
contains SELECT and a musicbrainz.* table. f-string fields are filled without evaluating them:
  module-level names bound to a plain string literal  -> that literal;
  a field inside IN ( ... )                              -> NULL;
  any other field (optional CTEs, joins, filters)        -> empty.
psycopg placeholders (%s, %(name)s) become NULL. Writes lb_queries.json with file and line.
Usage: python extract_lb.py LISTENBRAINZ_SOURCE_DIR"""
import ast, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def literals(tree):
    """module-level NAME = 'string' assignments"""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node.value.value
    return out


def render(node, names):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = ''
        for v in node.values:
            if isinstance(v, ast.Constant):
                out += v.value
            else:
                expr = v.value
                name = expr.id if isinstance(expr, ast.Name) else None
                if name in names:
                    out += names[name]
                elif re.search(r'\bIN\s*\(\s*$', out, re.I):
                    out += 'NULL'
                else:
                    out += ''
        return out
    return None


def main():
    src = sys.argv[1]
    found = []
    for root, _, files in os.walk(src):
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(root, f)
            tree = ast.parse(open(path, encoding='utf-8').read())
            names = literals(tree)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Constant, ast.JoinedStr)):
                    s = render(node, names)
                    if s and re.search(r'\bselect\b', s, re.I) and 'musicbrainz.' in s:
                        sql = re.sub(r'%\(\w+\)s|%s', 'NULL', s).strip().rstrip(';')
                        found.append(dict(file=os.path.relpath(path, src), line=node.lineno, sql=sql))
    # drop literals nested in a larger kept literal (f-string parts)
    found = [q for q in found if not any(q is not o and q['file'] == o['file'] and q['sql'] in o['sql']
                                         and len(o['sql']) > len(q['sql']) for o in found)]
    json.dump(found, open(os.path.join(HERE, 'lb_queries.json'), 'w'), indent=1)
    print(len(found), 'queries from', len({q['file'] for q in found}), 'files')


if __name__ == '__main__':
    main()
