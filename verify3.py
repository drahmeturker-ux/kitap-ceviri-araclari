#!/usr/bin/env python3
"""Check an original-layout build: translated text present, no leftover source text.
Usage: verify3.py LE.pdf layout.json tr.json out.pdf"""
import json, re, sys, subprocess, collections
src_pdf, lay, trf, out = sys.argv[1:5]
L = json.load(open(lay)); T = json.load(open(trf))
pns = sorted(int(p) for p in L['pages'])
txt = lambda f, a, b: subprocess.run(['pdftotext', '-f', str(a), '-l', str(b), f, '-'], capture_output=True, text=True).stdout
import pdfplumber
pp = pdfplumber.open(out)
o = ''
for pg in pp.pages:
    W = pg.width
    for a, b in ((0, W / 2 + 7), (W / 2 + 7, W)):
        o += (pg.crop((a, 0, b, pg.height)).extract_text() or '') + '\n'
import unicodedata
norm = lambda s: re.sub(r'[^a-z0-9çğıöşü]', '', unicodedata.normalize('NFKD', re.sub(r'<[^>]+>|\*\*', '', s).replace('İ', 'i').replace('I', 'ı').lower()).replace('\u0307', ''))
on = norm(o.replace('-\n', '').replace('\xad', ''))
miss = []
for it in L['items']:
    t = norm(T[it['id']])
    if t and t[-15:] not in on: miss.append(it['id'])
words = lambda s: set(w.lower() for w in re.findall(r'[A-Za-z]{5,}', s))
srcw = set()
for it in L['items']: srcw |= words(it['src'])
for p in L['pages'].values():
    for c in p['captions']: srcw |= words(c['rest'])
    for c in p['cells']: srcw |= words(c['src'])
trw = set()
for v in T.values(): trw |= words(v if isinstance(v, str) else ' '.join(v))
outw = collections.Counter(w.lower() for w in re.findall(r'[A-Za-z]{5,}', o))
left = {w: n for w, n in outw.items() if w in srcw and w not in trw}
print('items whose ending is missing in output:', miss)
print('source words left in output (may be references/authors):', sorted(left.items(), key=lambda x: -x[1])[:40])
