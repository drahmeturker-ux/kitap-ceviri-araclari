#!/usr/bin/env python3
"""Checks for extract3/layout3 books. Usage: checks3.py layout.json tr.json [glossary.json]"""
import json, re, sys, collections
def nums(t):
    t = re.sub(r'\[kaynakta:[^\]]*\]', '', t)
    return collections.Counter(n.replace(',', '.') for n in re.findall(r'\d+(?:[.,]\d+)?', re.sub(r'(?<=\d)[.,](?=\d{3}\b)', '', t)))
def abbrs(t): return set(re.findall(r'\b[A-Z][A-Z&]{1,5}\d*\b', t))
def caps(t):
    L = re.findall(r'[^\W\d_]', t); return L and sum(ch.isupper() for ch in L) / len(L) > .6
def cites(t): return re.findall(r'\([^()]*\b(?:1[89]|20)\d\d[a-z]?[^()]*\)', t)
def low(t): return t.replace('İ', 'i').replace('I', 'ı').lower()
def text_of(v): return v if isinstance(v, str) else ' '.join(v)
def main(layout, trf, glossf=None):
    L = json.load(open(layout)); T = json.load(open(trf))
    G = json.load(open(glossf))['terms'] if glossf else []
    src = {it['id']: it['src'] for it in L['items']}
    for pn, p in L['pages'].items():
        for c in p['captions']: src[c['id']] = c['bold'] + ' ' + c['rest']
        for c in p['cells']: src[c['id']] = c['src']
        for r in p['runhead']: src[f'p{pn}_rh'] = r['text']
        if p['h1']: src[f'p{pn}_h1'] = ' '.join(x['text'] for x in p['h1'])
        for i, t in enumerate(p['toc']): src[f'p{pn}_toc{i+1}'] = t['text']
    probs, notes, gl = [], [], []
    for k, s in src.items():
        if k not in T: probs.append(f'{k}: missing'); continue
        t = text_of(T[k])
        if not t.strip(): probs.append(f'{k}: empty'); continue
        ns, nt = nums(s), nums(t)
        if ns != nt and not k.endswith('_rh'): probs.append(f'{k}: numbers -{dict(ns - nt)} +{dict(nt - ns)}')
        if not caps(s):
            miss = abbrs(s) - abbrs(t)
            if miss: probs.append(f'{k}: abbreviations missing {sorted(miss)}')
            extra = abbrs(t) - abbrs(s) - {'MÖ', 'MS'}
            if extra and not caps(t): probs.append(f'{k}: new capitals {sorted(extra)}')
        for c in cites(s):
            if c[1:-1] not in t: probs.append(f'{k}: citation changed {c}')
        if re.findall(r'<sup>[^<]*</sup>', s) != re.findall(r'<sup>[^<]*</sup>', t): probs.append(f'{k}: superscripts differ')
        if s.count('<i>') != t.count('<i>'): probs.append(f'{k}: italics {s.count("<i>")} vs {t.count("<i>")}')
        if s.count('**') != t.count('**'): probs.append(f'{k}: link markers {s.count("**")} vs {t.count("**")}')
        for g in G:
            if re.search(r'\b' + re.escape(g['source']) + r'\b', s, re.I):
                tg = re.sub(r'\s*\(.*?\)', '', g['target'])
                stem = low(tg[:max(4, len(tg) - 3)])
                if stem not in low(t): gl.append(f'{k}: "{g["source"]}" -> "{g["target"]}"')
        notes += [f'{k}: {n}' for n in re.findall(r'\[kaynakta:[^\]]*\]', t)]
    print(f'{len(src)} items checked, {len(probs)} problems, {len(gl)} glossary misses')
    for p in probs: print('  PROBLEM', p)
    for p in gl: print('  GLOSS', p)
    for n in notes: print('  NOTE', n)
    sys.exit(1 if probs else 0)
if __name__ == '__main__': main(*sys.argv[1:])
