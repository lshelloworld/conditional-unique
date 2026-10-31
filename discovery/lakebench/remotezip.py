"""Read a zip archive over HTTP byte ranges: list its central directory, and extract chosen
members without downloading the archive. Handles zip64. Standard library only.
Usage: remotezip.py list URL OUT.json
       remotezip.py get URL LIST.json NAMES.txt OUTDIR"""
import json, os, struct, sys, urllib.request, zlib


def fetch(url, start, end):
    req = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def size(url):
    req = urllib.request.Request(url, headers={'Range': 'bytes=0-0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers['Content-Range'].split('/')[1])


def central_directory(url):
    n = size(url)
    tail = fetch(url, max(0, n - 70000), n - 1)
    base = max(0, n - 70000)
    i = tail.rfind(b'PK\x05\x06')
    cd_size, cd_off = struct.unpack('<II', tail[i + 12:i + 20])
    entries = struct.unpack('<H', tail[i + 10:i + 12])[0]
    j = tail.rfind(b'PK\x06\x06')                      # zip64 end of central directory
    if j >= 0:
        entries, cd_size, cd_off = struct.unpack('<QQQ', tail[j + 32:j + 56])
    cd = fetch(url, cd_off, cd_off + cd_size - 1)
    out, p = [], 0
    while p < len(cd) and cd[p:p + 4] == b'PK\x01\x02':
        method, = struct.unpack('<H', cd[p + 10:p + 12])
        csize, usize = struct.unpack('<II', cd[p + 20:p + 28])
        nlen, xlen, clen = struct.unpack('<HHH', cd[p + 28:p + 34])
        off, = struct.unpack('<I', cd[p + 42:p + 46])
        name = cd[p + 46:p + 46 + nlen].decode('utf-8', 'replace')
        extra = cd[p + 46 + nlen:p + 46 + nlen + xlen]
        q = 0
        while q + 4 <= len(extra):                      # zip64 extended information
            hid, hlen = struct.unpack('<HH', extra[q:q + 4])
            if hid == 1:
                vals, r = [], q + 4
                for v in (usize, csize, off):
                    if v == 0xFFFFFFFF:
                        vals.append(struct.unpack('<Q', extra[r:r + 8])[0]); r += 8
                    else:
                        vals.append(v)
                usize, csize, off = vals
            q += 4 + hlen
        out.append(dict(name=name, method=method, csize=csize, usize=usize, offset=off))
        p += 46 + nlen + xlen + clen
    return out


def extract(url, e):
    head = fetch(url, e['offset'], e['offset'] + 29)
    nlen, xlen = struct.unpack('<HH', head[26:30])
    start = e['offset'] + 30 + nlen + xlen
    data = fetch(url, start, start + e['csize'] - 1) if e['csize'] else b''
    if e['method'] == 0: return data
    if e['method'] == 8: return zlib.decompress(data, -15)
    raise ValueError(f"compression method {e['method']}")


if __name__ == '__main__':
    if sys.argv[1] == 'list':
        es = central_directory(sys.argv[2])
        json.dump(es, open(sys.argv[3], 'w'))
        print(len(es), 'entries,', sum(e['usize'] for e in es) / 1e9, 'GB uncompressed')
    else:
        url, es = sys.argv[2], {e['name']: e for e in json.load(open(sys.argv[3]))}
        names = [l.strip() for l in open(sys.argv[4]) if l.strip()]
        os.makedirs(sys.argv[5], exist_ok=True)
        for k, nm in enumerate(names):
            dst = os.path.join(sys.argv[5], os.path.basename(nm))
            if os.path.exists(dst): continue
            open(dst, 'wb').write(extract(url, es[nm]))
            if k % 50 == 0: print(k, nm, flush=True)
        print('done', len(names))
