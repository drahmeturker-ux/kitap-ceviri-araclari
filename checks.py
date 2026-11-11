#!/usr/bin/env python3
"""Consistency checks between source items (layout.json) and translation (tr.json).

Usage: checks.py layout.json tr.json [glossary.json]
Checks per item: numbers (decimal comma allowed), abbreviations kept, parenthetical
citations kept verbatim, bold Fig. markers kept, glossary targets used,
and collects [kaynakta: ...] notes. Exit code 1 if any problem is found.
"""
import json, re, sys, collections

def nums(t):
    t = re.sub(r'\[kaynakta:[^\]]*\]', '', t)
    return collections.Counter(n.replace(',', '.') for n in re.findall(r'\d+(?:[.,]\d+)?', t))

def abbrs(t):
    return set(re.findall(r'\b[A-Z]{2,6}\d*\b', t))

def cites(t):
    return [c for c in re.findall(r'\([^()]*\b(?:1[89]|20)\d\d[a-z]?[^()]*\)', t)]

def trlower(t):
    return t.replace('İ', 'i').replace('I', 'ı').lower()

def text_of(v):
    return v if isinstance(v, str) else ' '.join(v)

def main(layout, trf, glossf=None):
    L = json.load(open(layout)); T = json.load(open(trf))
    G = json.load(open(glossf))['terms'] if glossf else []
    src = {it['id']: it['src'] for it in L['items']}
    for pn, p in L['pages'].items():
        for c in p['captions']:
            src[c['id']] = c['bold'] + ' ' + c['rest']
    probs, notes = [], []
    for k, s in src.items():
        if k not in T:
            probs.append(f'{k}: missing translation'); continue
        t = text_of(T[k])
        if not t.strip(): probs.append(f'{k}: empty')
        ns, nt = nums(s), nums(t)
        if ns != nt:
            probs.append(f'{k}: numbers differ: -{dict(ns - nt)} +{dict(nt - ns)}')
        miss = abbrs(s) - abbrs(t)
        if miss: probs.append(f'{k}: abbreviations missing {sorted(miss)}')
        extra = abbrs(t) - abbrs(s)
        if extra: probs.append(f'{k}: new capitals (invented abbreviation?) {sorted(extra)}')
        for c in cites(s):
            if '(' + c[1:-1] + ')' not in t and c[1:-1] not in t:
                probs.append(f'{k}: citation changed: {c}')
        if s.count('**') != t.count('**'):
            probs.append(f'{k}: bold markers differ')
        for g in G:
            if re.search(r'\b' + re.escape(g['source']) + r'\b', s, re.I):
                stem = trlower(g['target'][:max(4, len(g['target']) - 3)])
                if stem not in trlower(t):
                    probs.append(f'{k}: glossary "{g["source"]}" -> "{g["target"]}" not used')
        notes += [f'{k}: {n}' for n in re.findall(r'\[kaynakta:[^\]]*\]', t)]
    print(f'{len(src)} items checked, {len(probs)} problems')
    for p in probs: print('  PROBLEM', p)
    for n in notes: print('  NOTE', n)
    sys.exit(1 if probs else 0)

if __name__ == '__main__':
    main(*sys.argv[1:])
