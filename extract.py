#!/usr/bin/env python3
"""Extract a two-column textbook page range into translation items + layout info.

Usage: extract.py book.pdf FIRST LAST out_dir   (1-based PDF page numbers)

Writes:
  out_dir/layout.json  - items (reading order, per-page letter shares), frames,
                         captions, running heads, chapter title, author line
  out_dir/source.md    - items as "<<id>> text" blocks, for translation

Font roles are decided by ROLE() below; adapt it per book (fontname/size).
"""
import json, re, sys, collections
import pdfplumber

def ROLE(w, top):
    f, s = w['fontname'], w['size']
    if top < 60:
        return 'runhead'
    if 'Black' in f and s > 14: return 'h1'
    if 'Black' in f and 11 < s < 13: return 'h2'
    if 'LightBold' in f and 9.5 < s < 10.5: return 'h3'
    if 'LightBold' in f and 8.8 < s < 9.4: return 'h4'   # run-in subheads (Stable / Elastic ...)
    if 'LightItalic' in f and 8 < s < 8.6: return 'author'
    if s < 7.8: return 'caption'
    return 'body'

BOLD = lambda f: 'Bold' in f
LETTERS = lambda t: len(re.findall(r'[^\W\d_]', t))

def join_words(ws):
    out = ''
    for i, w in enumerate(ws):
        t = w['text']
        if BOLD(w['fontname']) and w.get('role') == 'body':
            t = '**' + t + '**'
        out += ('' if i == 0 else ' ') + t
    out = out.replace('** **', ' ')
    return out

def clean(t):
    t = re.sub(r'\s*–\s*', '–', t)               # en dash never spaced in this book
    t = re.sub(r'Fig\.(\d)', r'Fig. \1', t)
    t = re.sub(r'\s*’\s*', '’', t)                # split apostrophes
    t = re.sub(r'(\w) ([äöüÄÖÜéèàç]) (\w)', r'\1\2\3', t)   # accented glyphs drawn separately
    t = re.sub(r'(\w)- (?=[a-z])', r'\1', t)       # hyphenated line breaks inside captions
    t = re.sub(r'(\w)-\*\* \*\*(\w)', r'\1\2', t)   # hyphen break inside bold
    t = t.replace('** **', ' ')                     # adjacent bold runs across lines
    t = re.sub(r'(\d)-? ?([μµ]) ?m\b', r'\1 \2m', t)
    t = re.sub(r'(\S) +([,.;:])(?= |$)', r'\1\2', t)        # stray space before punctuation
    t = re.sub(r'\(\s+\*\*', '(**', t); t = re.sub(r'\*\*\s+\)', '**)', t)
    return t

def join_lines(prev, nxt):
    if prev.endswith('-') and nxt[:1].islower():
        return prev[:-1] + nxt
    return prev + ' ' + nxt

def main(pdf_path, first, last, out):
    pdf = pdfplumber.open(pdf_path)
    pages, items = {}, []
    cur = None
    for pn in range(first, last + 1):
        page = pdf.pages[pn - 1]
        W = page.width
        mid = W / 2
        words = page.extract_words(x_tolerance=1, extra_attrs=['fontname', 'size', 'non_stroking_color'])
        for w in words:
            w['role'] = ROLE(w, w['top'])
        info = {'w': float(W), 'h': float(page.height), 'frames': [], 'captions': [], 'runhead': [], 'h1': [], 'author': [], 'items': []}
        # running head / h1 / author: keep line geometry
        for role in ('runhead', 'h1', 'author'):
            ws = sorted([w for w in words if w['role'] == role], key=lambda w: (round(w['top']), w['x0']))
            lines = collections.OrderedDict()
            for w in ws:
                lines.setdefault(round(w['bottom']), []).append(w)
            for b, lw in lines.items():
                info[role].append({'x0': lw[0]['x0'], 'x1': lw[-1]['x1'], 'top': lw[0]['top'], 'bottom': lw[0]['bottom'],
                                   'size': lw[0]['size'], 'font': lw[0]['fontname'], 'text': clean(' '.join(x['text'] for x in lw)),
                                   'parts': [{'t': x['text'], 'x0': x['x0'], 'font': x['fontname']} for x in lw]})
        # captions: cluster by proximity
        cw = [w for w in words if w['role'] == 'caption']
        blocks = []
        for w in sorted(cw, key=lambda w: (w['top'], w['x0'])):
            for b in blocks:
                if w['top'] - b['bottom'] < 6 and w['x0'] < b['x1'] + 6 and w['x1'] > b['x0'] - 6:
                    b['words'].append(w); b['bottom'] = max(b['bottom'], w['bottom'])
                    b['x0'] = min(b['x0'], w['x0']); b['x1'] = max(b['x1'], w['x1']); break
            else:
                blocks.append({'words': [w], 'top': w['top'], 'bottom': w['bottom'], 'x0': w['x0'], 'x1': w['x1']})
        for i, b in enumerate(blocks):
            ws = sorted(b['words'], key=lambda w: (round(w['top']), w['x0']))
            n = 0
            while n < len(ws) and BOLD(ws[n]['fontname']): n += 1
            bold = ' '.join(w['text'] for w in ws[:n])
            rest = ' '.join(('**' + w['text'] + '**') if BOLD(w['fontname']) else w['text'] for w in ws[n:])
            cid = f'p{pn}_cap{i+1}'
            info['captions'].append({'id': cid, 'x0': b['x0'], 'x1': b['x1'], 'top': b['top'], 'bottom': b['bottom'],
                                     'size': ws[0]['size'], 'bold': clean(bold), 'rest': clean(rest)})
        # body + h2/h3 lines per column
        bw = [w for w in words if w['role'] in ('body', 'h2', 'h3', 'h4')]
        cols = [[w for w in bw if w['x0'] < mid], [w for w in bw if w['x0'] >= mid]]
        for ci, cwords in enumerate(cols):
            if not cwords: continue
            lines = collections.OrderedDict()
            for w in sorted(cwords, key=lambda w: (w['top'], w['x0'])):
                key = next((k for k in lines if abs(k - w['bottom']) < 2.5), w['bottom'])
                lines.setdefault(key, []).append(w)
            L = []
            for k, lw in lines.items():
                lw.sort(key=lambda w: w['x0'])
                L.append({'x0': lw[0]['x0'], 'x1': lw[-1]['x1'], 'top': min(w['top'] for w in lw), 'bottom': max(w['bottom'] for w in lw),
                          'role': lw[0]['role'], 'words': lw})
            L.sort(key=lambda l: l['top'])
            body = [l for l in L if l['role'] == 'body']
            cx0 = min(l['x0'] for l in body) if body else min(l['x0'] for l in L)
            cx1 = max(l['x1'] for l in body) if body else max(l['x1'] for l in L)
            # frames = vertical runs
            run = [L[0]]
            def close(run):
                info['frames'].append({'col': ci, 'x0': cx0, 'x1': cx1, 'top': run[0]['top'], 'bottom': run[-1]['bottom'], 'items': []})
                for l in run: l['frame'] = len(info['frames']) - 1
            for l in L[1:]:
                if l['top'] - run[-1]['bottom'] > 45:
                    close(run); run = [l]
                else:
                    run.append(l)
            close(run)
            prev = None
            for l in L:
                ws = l['words']
                text = join_words(ws)
                gap = 0.0 if prev is None else max(0.0, l['top'] - prev['bottom'] - 3.0)
                new_frame = prev is not None and l['top'] - prev['bottom'] > 45
                if new_frame or prev is None: gap = 0.0
                indent = l['x0'] - cx0
                bullet = ws[0]['text'] in ('•', '·') or 'Symbol' in ws[0]['fontname']
                role = l['role']
                start = None
                dash = ws[0]['text'] == '–' and len(ws) > 1
                if role in ('h2', 'h3', 'h4'):
                    if cur and cur['kind'] == role and prev is not None and prev['role'] == role and l['top'] - prev['bottom'] < 6:
                        start = None
                    else:
                        start = {'kind': role, 'indent': False}
                elif dash and 9 < indent < 14:
                    text = text.split(' ', 1)[1]
                    start = {'kind': 'li2', 'indent': False}
                elif cur and cur['kind'] == 'li2' and 20 < indent < 26:
                    start = None
                elif bullet:
                    text = text.split(' ', 1)[1] if ' ' in text else ''
                    start = {'kind': 'li', 'indent': False}
                elif cur and cur['kind'] in ('li', 'lic') and 9 < indent < 14:
                    if prev is not None and prev['role'] == 'body' and prev['x1'] < cx1 - 15 and not new_frame:
                        start = {'kind': 'lic', 'indent': False}
                elif 8 < indent < 14:
                    start = {'kind': 'p', 'indent': True}
                elif cur is None or cur['kind'] in ('h2', 'h3', 'h4', 'li', 'lic', 'li2', 'h1'):
                    start = {'kind': 'p', 'indent': False}
                elif gap > 6 and not new_frame:
                    start = {'kind': 'p', 'indent': False}
                if start:
                    cur = {'id': f'i{len(items)+1:03d}', 'kind': start['kind'], 'indent': start['indent'], 'src': '', 'segs': []}
                    cur['gap'] = round(gap, 1)
                    items.append(cur)
                cur['src'] = text if not cur['src'] else join_lines(cur['src'], text)
                if not cur['segs'] or (cur['segs'][-1]['page'], cur['segs'][-1]['frame']) != (pn, l['frame']):
                    cur['segs'].append({'page': pn, 'frame': l['frame'], 'letters': 0, 'gap': cur['gap'] if not cur['segs'] else 0.0})
                    info['frames'][l['frame']]['items'].append([cur['id'], len(cur['segs']) - 1])
                    if cur['id'] not in info['items']: info['items'].append(cur['id'])
                cur['segs'][-1]['letters'] += LETTERS(text)
                prev = l
        pages[pn] = info
    for it in items:
        it['src'] = clean(it['src'])
    with open(f'{out}/layout.json', 'w') as f:
        json.dump({'pages': pages, 'items': items}, f, ensure_ascii=False, indent=1)
    with open(f'{out}/source.md', 'w') as f:
        for pn, info in pages.items():
            f.write(f'\n## PAGE {pn}\n')
            for r in info['runhead']: f.write(f'<<p{pn}_rh>> {r["text"]}\n')
            for i, r in enumerate(info['h1']): f.write(f'<<p{pn}_h1_{i+1}>> {r["text"]}\n')
            for c in info['captions']: f.write(f'<<{c["id"]}>> **{c["bold"]}** {c["rest"]}\n')
        f.write('\n## BODY\n')
        for it in items:
            f.write(f'<<{it["id"]}>> [{it["kind"]}] {it["src"]}\n\n')
    print(len(items), 'items;', sum(len(p['frames']) for p in pages.values()), 'frames')

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
