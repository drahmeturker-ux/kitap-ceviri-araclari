#!/usr/bin/env python3
"""Extract a Thieme two-column textbook (Essentials of Septorhinoplasty style) page range.

Usage: extract2.py book.pdf FIRST LAST out_dir
Variant of extract.py for books with mirrored margins (even pages shifted),
superscript citations, italic body words, gray boxes, vector figure labels and
a chapter-opener page with a table of contents.
Writes out_dir/layout.json and out_dir/source.md.
"""
import json, re, sys, collections
import pdfplumber

RED = (0.161, 1.0, 0.869, 0.064)

def col4(w):
    c = w.get('non_stroking_color')
    return isinstance(c, (tuple, list)) and len(c) == 4

def ROLE(w, top):
    f, s = w['fontname'], w['size']
    if top < 75 and s < 11: return 'runhead'
    if 'Gulliver' in f and s > 100: return 'deco'
    if 'Argo' in f and abs(s - 12.5) < .2 or ('Argo' in f and 'Bold' in f and abs(s - 16) < .2): return 'toc'
    if 'Argo' in f and 'Bold' in f and s > 17: return 'h1'
    if 'Argo' in f and 'Bold' in f and abs(s - 15) < .3: return 'h2'
    if 'Argo' in f and 'Bold' in f and abs(s - 13) < .3: return 'h3'
    if 'Argo' in f and 'Bold' in f and abs(s - 12) < .3: return 'h4'
    if 'Argo' in f and 'Bold' in f and abs(s - 11) < .3: return 'h5'
    if 'Argo' in f and 'BoldItalic' in f and abs(s - 10) < .3: return 'h6'
    if 'LightItalic' in f and abs(s - 9) < .3: return 'author'
    if 'Argo' in f and abs(s - 9) < .3: return 'box'
    if 'Argo' in f and col4(w) and s < 10: return 'label'
    if 'Argo' in f and s < 8.5: return 'caption'
    if 'Gulliver' in f and 6.2 <= s < 6.8: return 'ref'      # reference entries: kept as in the source
    if 'Gulliver' in f and (s < 6 or 6.8 <= s < 7.5): return 'sup'
    return 'body'

BOLD = lambda f: 'Bold' in f
ITAL = lambda f: 'Italic' in f
LETTERS = lambda t: len(re.findall(r'[^\W\d_]', re.sub(r'<[^>]+>', '', t)))

def join_words(ws, role_body=True):
    out = ''
    for i, w in enumerate(ws):
        t = w['text']
        if w.get('issup'):
            out += '<sup>' + t + '</sup>'; continue
        if role_body and BOLD(w['fontname']) and 'Gulliver' in w['fontname']: t = '**' + t + '**'
        elif ITAL(w['fontname']) and 'Gulliver' in w['fontname']: t = '<i>' + t + '</i>'
        out += ('' if i == 0 else ' ') + t
    return out

def clean(t):
    t = t.replace('', '').replace('', ' ')
    t = re.sub(r'\*\* \*\*', ' ', t)
    t = re.sub(r'</i> <i>', ' ', t)
    t = re.sub(r'</i><i>', '', t)
    t = re.sub(r'</sup><sup>', '', t)
    t = re.sub(r'(\w)-\*\* \*\*(\w)', r'\1\2', t)
    t = re.sub(r'(\S) +([,.;:])(?= |$)', r'\1\2', t)
    t = re.sub(r'\( ([a-zA-Z])', r'(\1', t)
    t = re.sub(r'\(\s+\*\*', '(**', t); t = re.sub(r'\*\*\s+\)', '**)', t)
    t = re.sub(r'“ <i>', '“<i>', t); t = re.sub(r'</i> ([.,;:)”])', r'</i>\1', t)
    t = re.sub(r'\b([B-HJ-Z]) ([a-z]{2,})', r'\1\2', t)      # split kerned capitals (G uillaume)
    t = re.sub(r'(?<![\w<>/])([b-hj-oq-wyz]) ([a-z]{2,})', r'\1\2', t)   # split kerned lowercase (r hinoplasty)
    t = re.sub(r'(\d)– (\d)', r'\1–\2', t)
    t = re.sub(r'(\w) ?\b(ffi|ffl|fi|fl|ff) (?=\w)', r'\1\2', t)   # split ligatures (super fi cial)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def join_lines(prev, nxt):
    m = re.search(r'(\w)-(</i>|\*\*)?$', prev)
    if m and re.match(r'(<i>|\*\*)?[a-z]', nxt):
        tag = m.group(2) or ''
        nx = nxt
        if tag and nx.startswith(tag.replace('/', '')): nx = nx[len(tag.replace('/', '')):]; tag = ''
        return prev[:m.start() + 1] + tag + nx if not tag else prev[:m.start() + 1] + nx
    return prev + ' ' + nxt

def lines_of(ws, tol=2.5):
    lines = []
    for w in sorted(ws, key=lambda w: (w['top'], w['x0'])):
        for l in lines:
            if abs(l['bottom'] - w['bottom']) < tol:
                l['words'].append(w); l['bottom'] = max(l['bottom'], w['bottom']); break
        else:
            lines.append({'bottom': w['bottom'], 'words': [w]})
    for l in lines:
        l['words'].sort(key=lambda w: w['x0'])
        l['x0'] = l['words'][0]['x0']; l['x1'] = max(w['x1'] for w in l['words'])
        l['top'] = min(w['top'] for w in l['words'])
    lines.sort(key=lambda l: l['top'])
    return lines

def attach_sups(main, sups):
    """Attach superscript words to the line whose top is closest (they sit at the line top)."""
    for s in sups:
        best = None
        for w in main:
            if abs(w['top'] - s['top']) < 3 and w['x1'] <= s['x0'] + 2:
                if best is None or w['x1'] > best['x1']: best = w
        if best is None:
            continue
        s['issup'] = True; s['role'] = best['role']
        s['bottom'] = best['bottom']; s['top'] = best['top']
        main.append(s)

def main(pdf_path, first, last, out):
    pdf = pdfplumber.open(pdf_path)
    pages, items = {}, []
    cur = None
    for pn in range(first, last + 1):
        page = pdf.pages[pn - 1]
        W = page.width
        off = 14.2 if pn % 2 == 0 else 0.0
        mid = 348 + off
        colr = [341.2 + off, 613.6 + off]
        words = page.extract_words(x_tolerance=1, extra_attrs=['fontname', 'size', 'non_stroking_color'])
        for w in words:
            w['role'] = ROLE(w, w['top'])
            c = w.get('non_stroking_color')
            w['color'] = list(c) if isinstance(c, (tuple, list)) else None
        info = {'w': float(W), 'h': float(page.height), 'off': off, 'colr': colr, 'frames': [], 'captions': [],
                'runhead': [], 'h1': [], 'author': [], 'labels': [], 'boxes': [], 'toc': [], 'deco': [], 'items': []}
        sups = [w for w in words if w['role'] == 'sup']
        capsup = [w for w in words if w['role'] == 'caption' and w['size'] < 6]
        for w in capsup: w['role'] = 'capsup'
        attach_sups([w for w in words if w['role'] in ('body',)], sups)
        attach_sups([w for w in words if w['role'] == 'caption'], capsup)
        words = [w for w in words if w['role'] not in ('sup', 'capsup') or w.get('issup')]
        def geom(lw):
            return {'x0': lw[0]['x0'], 'x1': lw[-1]['x1'], 'top': lw[0]['top'], 'bottom': lw[0]['bottom'],
                    'size': lw[0]['size'], 'font': lw[0]['fontname'], 'color': lw[0]['color'],
                    'text': clean(' '.join(x['text'] for x in lw)),
                    'parts': [{'t': x['text'], 'x0': x['x0'], 'font': x['fontname'], 'size': x['size']} for x in lw]}
        for role in ('runhead', 'h1', 'author', 'toc', 'deco'):
            for l in lines_of([w for w in words if w['role'] == role]):
                if role != 'toc':
                    info[role].append(geom(l['words'])); continue
                grp = [l['words'][0]]
                for w in l['words'][1:]:
                    if w['x0'] - grp[-1]['x1'] < 40: grp.append(w)
                    else: info[role].append(geom(grp)); grp = [w]
                info[role].append(geom(grp))
        # vector figure labels: group words on one line that are close together
        for l in lines_of([w for w in words if w['role'] == 'label'], tol=1.5):
            grp = [l['words'][0]]
            for w in l['words'][1:]:
                if w['x0'] - grp[-1]['x1'] < 6: grp.append(w)
                else: info['labels'].append(geom(grp)); grp = [w]
            info['labels'].append(geom(grp))
        # gray boxes
        rects = [r for r in page.rects if isinstance(r['non_stroking_color'], (tuple, list)) and len(r['non_stroking_color']) == 4
                 and abs(r['non_stroking_color'][1] - 0.1) < 0.02 and r['width'] > 100]
        for w in words:
            if 'Symbol' in w['fontname'] and any(r['x0'] - 2 <= w['x0'] <= r['x1'] and r['top'] - 2 <= w['top'] <= r['bottom'] for r in rects):
                w['role'] = 'box'
        bwords = [w for w in words if w['role'] == 'box']
        for bi, r in enumerate(rects):
            inside = [w for w in bwords if r['x0'] - 2 <= w['x0'] and w['x1'] <= r['x1'] + 2 and r['top'] - 2 <= w['top'] <= r['bottom'] + 2]
            if not inside: continue
            lines = []
            for l in lines_of(inside):
                ws = l['words']
                bullet = ws[0]['text'].startswith('•') or ws[0]['text'].startswith('')
                t = clean(' '.join(x['text'] for x in ws)).lstrip('•').strip()
                if BOLD(ws[0]['fontname']): lines.append({'k': 'h', 't': t, 'x0': l['x0'], 'top': l['top']})
                elif bullet or not lines: lines.append({'k': 'li', 't': t, 'x0': l['x0'], 'top': l['top']})
                else: lines[-1]['t'] = join_lines(lines[-1]['t'], t)
            info['boxes'].append({'id': f'p{pn}_box{bi+1}', 'x0': r['x0'], 'x1': r['x1'], 'top': r['top'], 'bottom': r['bottom'],
                                  'lines': lines})
        # captions: cluster by proximity
        cw = [w for w in words if w['role'] == 'caption']
        blocks = []
        for w in sorted(cw, key=lambda w: (w['top'], w['x0'])):
            for b in blocks:
                if w['top'] - b['bottom'] < 6 and w['x0'] < b['x1'] + 14 and w['x1'] > b['x0'] - 6:
                    b['words'].append(w); b['bottom'] = max(b['bottom'], w['bottom'])
                    b['x0'] = min(b['x0'], w['x0']); b['x1'] = max(b['x1'], w['x1']); break
            else:
                blocks.append({'words': [w], 'top': w['top'], 'bottom': w['bottom'], 'x0': w['x0'], 'x1': w['x1']})
        for i, b in enumerate(blocks):
            L = lines_of(b['words'])
            ws = [w for l in L for w in l['words']]
            n = 0
            while n < len(ws) and BOLD(ws[n]['fontname']) and not ws[n].get('issup') and (n < 2 or not ws[n]['text'].startswith('(')): n += 1
            bold = ' '.join(w['text'] for w in ws[:n])
            # rebuild rest line by line to keep list items (1. 2. ...) and hyphen joins
            rest = ''
            first = True
            for l in L:
                lw = [w for w in l['words'] if w not in ws[:n]]
                if not lw: continue
                seg = ''
                for j, w in enumerate(lw):
                    t = w['text']
                    if w.get('issup'): seg += '<sup>' + t + '</sup>'; continue
                    if BOLD(w['fontname']): t = '**' + t + '**'
                    elif ITAL(w['fontname']): t = '<i>' + t + '</i>'
                    seg += ('' if j == 0 else ' ') + t
                if first: rest = seg; first = False
                elif re.match(r'\d+\.$', lw[0]['text']) or lw[0]['text'] in ('•', ''): rest += '\n' + seg
                else: rest = join_lines(rest, seg)
            right = min([e for e in colr if e >= b['x1'] - 3] or [b['x1']])
            info['captions'].append({'id': f'p{pn}_cap{i+1}', 'x0': b['x0'], 'x1': b['x1'], 'right': right, 'top': b['top'], 'bottom': b['bottom'],
                                     'size': 8.0, 'bold': clean(bold),
                                     'rest': '\n'.join(clean(x) for x in rest.split('\n'))})
        # body + headings per column
        bw = [w for w in words if w['role'] in ('body', 'h2', 'h3', 'h4', 'h5', 'h6')]
        cols = [[w for w in bw if w['x0'] < mid], [w for w in bw if w['x0'] >= mid]]
        for ci, cwords in enumerate(cols):
            if not cwords: continue
            L = lines_of(cwords)
            for l in L:
                main_w = [w for w in l['words'] if not w.get('issup')]
                l['role'] = main_w[0]['role'] if main_w else 'body'
            cx0 = 83 + off + (272.5 if ci else 0)
            cx1 = colr[ci]
            run = [L[0]]
            def close(run):
                info['frames'].append({'col': ci, 'x0': cx0, 'x1': cx1, 'top': run[0]['top'], 'bottom': run[-1]['bottom'], 'items': []})
                for l in run: l['frame'] = len(info['frames']) - 1
            for l in L[1:]:
                if l['top'] - run[-1]['bottom'] > 30:
                    close(run); run = [l]
                else:
                    run.append(l)
            close(run)
            prev = None
            for l in L:
                ws = l['words']
                text = clean(join_words(ws))
                new_frame = prev is not None and l['frame'] != prev['frame']
                gap = 0.0 if (prev is None or new_frame) else max(0.0, l['top'] - prev['bottom'] - 2.0)
                indent = l['x0'] - cx0
                bullet = ws[0]['text'].startswith('') or ws[0]['text'] == '•'
                role = l['role']
                start = None
                dash = ws[0]['text'] == '–' and len(ws) > 1 and 8 < indent < 13
                if role.startswith('h'):
                    if cur and cur['kind'] == role and prev is not None and prev['role'] == role and l['top'] - prev['bottom'] < 8:
                        start = None
                    else:
                        start = {'kind': role, 'indent': False}
                elif dash:
                    text = text.split(' ', 1)[1]
                    start = {'kind': 'li2', 'indent': False}
                elif cur and cur['kind'] == 'li2' and 17 < indent < 24:
                    start = None
                elif bullet:
                    text = text.strip()
                    start = {'kind': 'li', 'indent': False}
                elif cur and cur['kind'] == 'li' and 8 < indent < 12.5:
                    start = None
                elif (cur and cur['kind'] in ('p', 'li') and prev is not None and not new_frame and prev['role'] == 'body'
                      and prev['x1'] >= cx1 - 12 and gap < 4 and not re.match(r'\d+[a-z]?\.$', ws[0]['text'])
                      and not re.sub(r'<sup>[^<]*</sup>|<[^>]+>|\*\*', '', join_words(prev['words'])).rstrip().endswith(('.', '!', '?', ':', '”', '.)'))):
                    start = None          # previous line is full width: hanging-indent continuation, not a new paragraph
                elif 12.5 <= indent < 20:
                    start = {'kind': 'p', 'indent': True}
                elif cur is None or cur['kind'] not in ('p',):
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
            if info['h1']: f.write(f'<<p{pn}_h1>> {" ".join(r["text"] for r in info["h1"])}\n')
            for i, r in enumerate(info['toc']): f.write(f'<<p{pn}_toc{i+1}>> {r["text"]}\n')
            for c in info['captions']: f.write(f'<<{c["id"]}>> **{c["bold"]}** {c["rest"]}\n')
            for b in info['boxes']: f.write(f'<<{b["id"]}>> ' + ' | '.join(f'[{x["k"]}] {x["t"]}' for x in b['lines']) + '\n')
            labs = [x['text'] for x in info['labels'] if LETTERS(x['text']) > 1]
            if labs: f.write(f'<<p{pn}_labels>> ' + ' | '.join(labs) + '\n')
        f.write('\n## BODY\n')
        for it in items:
            f.write(f'<<{it["id"]}>> [{it["kind"]}] {it["src"]}\n\n')
    print(len(items), 'items;', sum(len(p['frames']) for p in pages.values()), 'frames')

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
