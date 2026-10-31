"""Convert MediaWiki SQL dumps (dumps.wikimedia.org, <wiki>-latest-<table>.sql.gz: MySQL
CREATE TABLE plus INSERT ... VALUES (...),(...)) to CSV files, one per table, with a header from
the CREATE TABLE. Values are read by a small tokenizer (quoted strings with backslash escapes,
numbers, NULL); nothing in the dump is executed. Binary strings are decoded as UTF-8, with
replacement. Usage: python wiki_convert.py DUMPDIR CSVDIR"""
import csv, gzip, os, re, sys

ESC = {'0': '\0', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a', 'b': '\b'}


def tuples(s, i):
    """yield the value tuples of one INSERT's VALUES list starting at s[i]"""
    n = len(s)
    while i < n:
        while i < n and s[i] in ' ,\n': i += 1
        if i >= n or s[i] == ';': return
        assert s[i] == '(', s[i:i + 40]
        i += 1; row, buf = [], None
        while True:
            c = s[i]
            if c == "'":
                i += 1; out = []
                while True:
                    c = s[i]
                    if c == '\\': out.append(ESC.get(s[i + 1], s[i + 1])); i += 2
                    elif c == "'":
                        if s[i + 1] == "'": out.append("'"); i += 2
                        else: i += 1; break
                    else: out.append(c); i += 1
                buf = ''.join(out)
            elif c in ',)':
                row.append(buf); buf = None; i += 1
                if c == ')': yield row; break
            else:
                j = i
                while s[j] not in ',)': j += 1
                tok = s[i:j].strip(); i = j
                buf = None if tok == 'NULL' else tok


def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    for f in sorted(os.listdir(src)):
        m = re.match(r'\w+-latest-(\w+)\.sql\.gz$', f)
        if not m: continue
        t = m.group(1)
        text = gzip.open(os.path.join(src, f), 'rb').read().decode('utf-8', 'replace')
        ct = re.search(r'CREATE TABLE `%s` \((.*?)\n\)' % t, text, re.S)
        cols = re.findall(r'^\s*`(\w+)`', ct.group(1), re.M)
        n = 0
        with open(os.path.join(dst, t + '.csv'), 'w', newline='') as out:
            w = csv.writer(out); w.writerow(cols)
            for im in re.finditer(r'INSERT INTO `%s` VALUES\s*' % t, text):
                for row in tuples(text, im.end()):
                    w.writerow(['' if v is None else v for v in row]); n += 1
        print(t, len(cols), 'columns', n, 'rows', flush=True)


if __name__ == '__main__':
    main()
