#!/usr/bin/env python3
"""Extract an Elsevier two-column textbook page range (Lower Extremity Soft Tissue &
Cutaneous Plastic Surgery style: Giovanni body 8.5 pt, Frutiger headings/captions/tables,
mirrored margins, heading bands, side tab on odd pages, chapter-opener page with contents box).

Usage: extract3.py book.pdf FIRST LAST out_dir
Writes out_dir/layout.json and out_dir/source.md.
Text is split into: body items (<<iNNN>>), captions (<<pN_capK>> bold | rest), table/figure
cells (<<pN_cK>>), running heads, chapter title and contents box. Reference entries
(Giovanni 8 pt), page numbers, author line and copyright stay in the source glyphs.
"""
import json, re, sys
import pdfplumber

LETTERS = lambda t: len(re.findall(r'[^\W\d_]', re.sub(r'<[^>]+>|\*\*', '', t)))
FN = lambda w: w['fontname'].split('+')[-1]
BOLD = lambda f: 'Bold' in f or 'Black' in f
ITAL = lambda f: 'Italic' in f

def is_white(c):
    return isinstance(c, (tuple, list)) and ((len(c) == 4 and max(c) < .01) or (len(c) == 1 and c[0] > .99 and False))

def ROLE(w, opener):
    f, s, top = FN(w), w['size'], w['top']
    if w['text'] in ('|', '||', '| |'): return 'keep'
    if 'Giovanni' in f and abs(s - 9) < .2 and top < 50: return 'runhead'
    if 'Giovanni' in f and abs(s - 13) < .3 and top < 90: return 'tab'
    if 'Frutiger-Black' in f and abs(s - 9) < .2 and (top < 50 or top > 740): return 'keep'      # page/chapter numbers
    if 'Frutiger' in f and s < 7.5 and top > 740: return 'keep'                                 # copyright line
    if 'Giovanni' in f and abs(s - 8.0) < .05: return 'keep'                                    # reference entries
    if 'Frutiger-Italic' in f and abs(s - 12) < .3: return 'keep'                               # author line
    if s > 40: return 'keep'                                                                    # big chapter number
    if 'Giovanni' in f and abs(s - 29) < .5: return 'chap'
    if 'Giovanni' in f and abs(s - 23) < .5: return 'h1'
    if 'Frutiger-Black' in f and abs(s - 9) < .2 and is_white(w.get('non_stroking_color')): return 'tochead'
    if opener and 'Frutiger' in f and abs(s - 9) < .2 and w['x0'] < 330 and 300 < top < 480: return 'toc'
    if 'Frutiger-Black' in f and abs(s - 11) < .3: return 'h2'
    if 'Frutiger-Bold' in f and abs(s - 10) < .3: return 'h4'
    if 'Frutiger' in f and 'Italic' in f and abs(s - 10) < .3: return 'h5'
    if 'Frutiger-Light' in f and abs(s - 10) < .3 and w['text'].startswith('•'): return 'body'
    if ('Giovanni' in f or 'Symbol' in f or 'Minion' in f) and 8.3 < s < 8.8: return 'body'
    if 'Giovanni' in f and (s < 6.5 or abs(s - 10) < .3): return 'sup'
    return 'cell'

def clean(t):
    t = t.replace('­', '')
    t = re.sub(r'\*\* \*\*', ' ', t)
    t = re.sub(r'</i> <i>', ' ', t); t = re.sub(r'</i><i>', '', t)
    t = re.sub(r'</sup><sup>', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    t = re.sub(r'([(\[]) (\*\*|<i>)', r'\1\2', t); t = re.sub(r'(\*\*|</i>) ([)\];,.])', r'\1\2', t)
    return t

def join_lines(prev, nxt):
    m = re.search(r'(\w)-(</i>|\*\*)?$', prev)
    if m and re.match(r'(<i>|\*\*)?[a-z]', nxt):
        tag = m.group(2) or ''
        nx = nxt
        if tag and nx.startswith(tag.replace('/', '')): return prev[:m.start() + 1] + nx[len(tag.replace('/', '')):]
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

def word_text(w, blue_ok=True):
    t = w['text']
    if w.get('issup'): return '<sup>' + t + '</sup>'
    f = FN(w)
    c = w.get('non_stroking_color')
    if blue_ok and isinstance(c, (tuple, list)) and len(c) == 4 and c[0] > .9 and c[1] > .9 and c[3] < .1: t = '**' + t + '**'
    elif ITAL(f) and 'Giovanni' in f: t = '<i>' + t + '</i>'
    elif 'Giovanni-Bold' in f: t = '<b>' + t + '</b>'
    return t

def join_words(ws):
    out = ''
    for i, w in enumerate(ws):
        t = word_text(w)
        out += t if (i == 0 or w.get('issup') or (w.get('frac') and ws[i - 1]['x1'] > w['x0'] - 1.5)) else ' ' + t
    return out

def attach_sups(main, sups):
    for s in sups:
        best = None
        for w in main:
            if s['top'] - 4 < w['top'] < s['top'] + 4 and w['x1'] <= s['x0'] + 2 and s['x0'] - w['x1'] < 6:
                if best is None or w['x1'] > best['x1']: best = w
        if best is None: continue
        s['issup'] = True; s['role'] = best['role']
        s['bottom'] = best['bottom']; s['top'] = best['top']
        main.append(s)

def first_pos(w):
    ch = w['chars'][0]
    return [round(ch['matrix'][4], 1), round(ch['matrix'][5], 1)]

def main(pdf_path, first, last, out):
    pdf = pdfplumber.open(pdf_path)
    pages, items = {}, []
    cur = prev = None
    for pn in range(first, last + 1):
        page = pdf.pages[pn - 1]
        W, H = float(page.width), float(page.height)
        words = page.extract_words(x_tolerance=1, extra_attrs=['fontname', 'size', 'non_stroking_color'], return_chars=True)
        opener = any('Giovanni' in FN(w) and abs(w['size'] - 29) < .5 for w in words)
        pnum = [w for w in words if 'Frutiger-Black' in FN(w) and abs(w['size'] - 9) < .2 and w['top'] > 740]
        if pnum: off = 0.0 if pnum[0]['x0'] < 200 else 28.35
        else:
            bx = [w['x0'] for w in words if 'Giovanni' in FN(w) and abs(w['size'] - 8.5) < .2]
            off = 28.35 if bx and min(bx) > 50 else 0.0
        mid = 296 + off
        cx0 = [34 + off, 303.3 + off]; cx1 = [289.2 + off, 558.5 + off]
        for w in words:
            w['role'] = ROLE(w, opener)
            c = w.get('non_stroking_color')
            w['color'] = list(c) if isinstance(c, (tuple, list)) else None
        info = {'w': W, 'h': H, 'off': off, 'cx0': cx0, 'cx1': cx1, 'frames': [], 'captions': [], 'cells': [],
                'runhead': [], 'tab': [], 'chap': [], 'h1': [], 'tochead': [], 'toc': [], 'items': [], 'drop': []}
        sups = [w for w in words if w['role'] == 'sup']
        attach_sups([w for w in words if w['role'] in ('body', 'cell')], sups)
        FR = {('1', '2'): '½', ('1', '4'): '¼', ('3', '4'): '¾'}
        for s2 in sups:             # vulgar fractions: superscript numerator + lowered denominator
            if s2.get('issup'): continue
            for s1 in sups:
                if s1.get('issup') and 0 <= s2['x0'] - s1['x1'] < 3 and 0 < s2['bottom'] - s1['bottom'] < 9:
                    s1['text'] = FR.get((s1['text'], s2['text']), s1['text'] + '/' + s2['text'])
                    s1['issup'] = False; s1['frac'] = True
                    s2['consumed'] = True; s2['role'] = 'gone'
                    break
        drawn = [w for w in words if w.get('consumed')]
        words = [w for w in words if (w['role'] != 'sup' or w.get('issup') or w.get('frac')) and not w.get('consumed')]
        def geom(lw):
            return {'x0': lw[0]['x0'], 'x1': lw[-1]['x1'], 'top': min(x['top'] for x in lw), 'bottom': max(x['bottom'] for x in lw),
                    'size': lw[0]['size'], 'font': FN(lw[0]), 'color': lw[0]['color'],
                    'text': clean(' '.join(x['text'] for x in lw)),
                    'parts': [{'t': x['text'], 'x0': x['x0'], 'x1': x['x1'], 'font': FN(x), 'size': x['size']} for x in lw]}
        for role in ('runhead', 'tab', 'chap', 'h1', 'tochead', 'toc'):
            rw = [w for w in words if w['role'] == role]
            drawn += rw
            for l in lines_of(rw):
                info[role].append(geom(l['words']))
        # ---- captions: fragments per line, a bold "Figure/Table/Box" starts a block
        capw = [w for w in words if w['role'] == 'cell' and 'Frutiger' in FN(w) and w['size'] < 8.6]
        frags = []
        for l in lines_of(capw, tol=1.5):
            grp = [l['words'][0]]
            for w in l['words'][1:]:
                starts = BOLD(FN(w)) and re.match(r'(Figure|Table|Box)$', w['text']) and not BOLD(FN(grp[-1]))
                if w['x0'] - grp[-1]['x1'] > 8 or starts: frags.append(grp); grp = [w]
                else: grp.append(w)
            frags.append(grp)
        blocks = []
        for fr in sorted(frags, key=lambda g: (g[0]['top'], g[0]['x0'])):
            x0, x1, top, bot = fr[0]['x0'], max(w['x1'] for w in fr), min(w['top'] for w in fr), max(w['bottom'] for w in fr)
            if BOLD(FN(fr[0])) and re.match(r'(Figure|Table|Box)$', fr[0]['text']) and len(fr) > 1 and re.match(r'\d', fr[1]['text']):
                blocks.append({'frags': [fr], 'x0': x0, 'x1': x1, 'top': top, 'bottom': bot}); continue
            best = None
            for b in blocks:
                if 0 <= top - b['bottom'] < 5.5 and x0 >= b['x0'] - 2 and x0 < b['x1'] and (FN(fr[0]) != 'Frutiger-Bold' or ITAL(FN(fr[0]))):
                    if best is None or b['bottom'] > best['bottom']: best = b
            if best is not None:
                best['frags'].append(fr); best['bottom'] = bot; best['x1'] = max(best['x1'], x1)
        capset = set()
        for i, b in enumerate(blocks):
            ws = [w for fr in b['frags'] for w in fr]
            capset.update(id(w) for w in ws)
            n = 0
            while n < len(ws) and BOLD(FN(ws[n])) and n < 2: n += 1
            bold = ' '.join(w['text'] for w in ws[:n])
            rest, prevfr = '', None
            for fr in b['frags']:
                lw = [w for w in fr if w not in ws[:n]]
                if not lw: continue
                seg = ''
                for j, w in enumerate(lw):
                    t = w['text']
                    if w.get('issup'): seg += '<sup>' + t + '</sup>'; continue
                    if ITAL(FN(w)): t = '<i>' + t + '</i>'
                    elif BOLD(FN(w)): t = '**' + t + '**'
                    seg += ('' if j == 0 else ' ') + t
                if not rest: rest = seg
                elif ITAL(FN(lw[0])) and prevfr is not None and not ITAL(FN(prevfr[-1])): rest += '\n' + seg
                elif lw[0]['text'] in ('•', '–'): rest += '\n' + seg
                else: rest = join_lines(rest, seg)
                prevfr = lw
            full = b['x0'] < mid - 40 and b['x1'] > mid + 20
            right = cx1[1] if (full or b['x0'] >= mid - 5) else cx1[0]
            if b['x0'] >= mid - 5: right = cx1[1]
            info['captions'].append({'id': f'p{pn}_cap{i+1}', 'x0': b['x0'], 'x1': b['x1'], 'right': max(right, b['x1']), 'top': b['top'],
                                     'bottom': b['bottom'], 'size': ws[-1]['size'], 'bold': clean(bold),
                                     'rest': '\n'.join(clean(x) for x in rest.split('\n'))})
            drawn += ws
        # ---- cells (tables, figure labels): fragments merged vertically
        cw = [w for w in words if w['role'] == 'cell' and id(w) not in capset]
        frs = []
        for l in lines_of(cw, tol=1.5):
            grp = [l['words'][0]]
            gaps = sorted(b['x0'] - a['x1'] for a, b in zip(l['words'], l['words'][1:]))
            med = gaps[len(gaps) // 2] if gaps else 0
            for w in l['words'][1:]:
                g = w['x0'] - grp[-1]['x1']
                if g > 8.5 or BOLD(FN(w)) != BOLD(FN(grp[-1])) or abs(w['size'] - grp[-1]['size']) > .3:
                    frs.append(grp); grp = [w]
                else: grp.append(w)
            frs.append(grp)
        cells = []
        for fr in sorted(frs, key=lambda g: (min(w['top'] for w in g), g[0]['x0'])):
            x0, x1 = fr[0]['x0'], max(w['x1'] for w in fr)
            top, bot = min(w['top'] for w in fr), max(w['bottom'] for w in fr)
            best = None
            for c in cells:
                if (0 <= top - c['bottom'] < 4.0 and abs(x0 - c['x0']) < 2.5 and c['bold'] == BOLD(FN(fr[0]))
                        and abs(c['size'] - fr[0]['size']) < .3 and not fr[0]['text'].startswith('•')):
                    best = c
            if best: best['lines'].append(fr); best['bottom'] = bot; best['x1'] = max(best['x1'], x1)
            else: cells.append({'lines': [fr], 'x0': x0, 'x1': x1, 'top': top, 'bottom': bot, 'bold': BOLD(FN(fr[0])),
                                'size': fr[0]['size'], 'font': FN(fr[0]), 'color': fr[0]['color']})
        k = 0
        for c in cells:
            txt = ''
            for fr in c['lines']:
                seg = join_words(fr)
                txt = seg if not txt else (txt + '\n' + seg if re.match(r'(•|–|_{2,}|\d+\.\s)', seg) else join_lines(txt, seg))
            txt = clean(txt) if '\n' not in txt else '\n'.join(clean(x) for x in txt.split('\n'))
            ws = [w for fr in c['lines'] for w in fr]
            if LETTERS(txt) < 2:            # numbers, panel letters: keep source glyphs (redrawn only if their text op is removed)
                info.setdefault('fixed', []).append({'x0': c['x0'], 'x1': c['x1'], 'top': c['top'], 'bottom': c['bottom'], 'size': c['size'],
                                      'font': c['font'], 'bold': c['bold'], 'color': c['color'], 'src': txt,
                                      'lines': [{'pos': first_pos(fr[0]), 'text': clean(' '.join(w['text'] for w in fr))} for fr in c['lines']]})
                continue
            k += 1
            info['cells'].append({'id': f'p{pn}_c{k}', 'x0': c['x0'], 'x1': c['x1'], 'top': c['top'], 'bottom': c['bottom'],
                                  'size': c['size'], 'font': c['font'], 'bold': c['bold'], 'color': c['color'],
                                  'nlines': len(c['lines']), 'src': txt})
            drawn += ws
        # ---- body + headings per column
        bw = [w for w in words if w['role'] in ('body', 'h2', 'h4', 'h5')]
        drawn += bw
        bands = [l['top'] - 11 for l in page.lines if (l.get('linewidth') or 0) > 15 and l['x1'] - l['x0'] > 400]
        split = min(bands) if bands else 1e9
        cols = [[w for w in bw if w['x0'] < mid and w['top'] < split], [w for w in bw if w['x0'] >= mid and w['top'] < split],
                [w for w in bw if w['x0'] < mid and w['top'] >= split], [w for w in bw if w['x0'] >= mid and w['top'] >= split]]
        for ci, cwords in enumerate(cols):
            if not cwords: continue
            ci = ci % 2
            L = lines_of(cwords)
            for l in L:
                main_w = [w for w in l['words'] if not w.get('issup')]
                l['role'] = main_w[0]['role'] if main_w else 'body'
                if l['role'] == 'h2' and LETTERS(l['words'][0]['text']) and not re.sub(r'[^\w]', '', ' '.join(w['text'] for w in main_w)).isupper():
                    l['role'] = 'h3'
            c0, c1 = cx0[ci], cx1[ci]
            run = [L[0]]
            def close(run):
                info['frames'].append({'col': ci, 'x0': c0, 'x1': c1, 'top': run[0]['top'], 'bottom': run[-1]['bottom'], 'items': []})
                for l in run: l['frame'] = len(info['frames']) - 1; l['fid'] = (pn, l['frame'])
            for l in L[1:]:
                head = l['role'] != 'body' and not (run[-1]['role'] == l['role'] and l['top'] - run[-1]['bottom'] < 8)
                if l['top'] - run[-1]['bottom'] > 30 or head:
                    close(run); run = [l]
                else:
                    run.append(l)
            close(run)
            for l in L:
                ws = l['words']
                text = clean(join_words(ws))
                new_frame = prev is not None and l['fid'] != prev['fid']
                gap = 0.0 if (prev is None or new_frame) else max(0.0, l['top'] - prev['bottom'] - 2.5)
                indent = l['x0'] - c0
                bullet = ws[0]['text'].startswith('•')
                role = l['role']
                prevtxt = re.sub(r'<sup>[^<]*</sup>|<[^>]+>|\*\*', '', join_words(prev['words'])).rstrip() if prev else ''
                prevfull = prev is not None and prev['x1'] >= c1 - 14
                start = None
                if role.startswith('h'):
                    if cur and cur['kind'] == role and prev is not None and prev['role'] == role and l['top'] - prev['bottom'] < 8:
                        start = None
                    else:
                        start = {'kind': role, 'indent': False}
                elif bullet:
                    text = text.lstrip('•').strip()
                    start = {'kind': 'li', 'indent': False}
                elif cur and cur['kind'] == 'li' and 3 < indent < 18 and not new_frame:
                    start = None
                elif cur and cur['kind'] == 'li' and new_frame and indent > 3:
                    start = None
                elif 12 < indent < 18:
                    if cur and cur['kind'] == 'q' and (prevfull or new_frame) and gap < 4: start = None
                    else: start = {'kind': 'q', 'indent': False}
                elif 6 < indent <= 12:
                    start = {'kind': 'p', 'indent': True}
                elif cur is None or cur['kind'] not in ('p', 'q', 'li'):
                    start = {'kind': 'p', 'indent': False}
                elif new_frame:
                    start = None if (cur['kind'] == 'p' and not prevtxt.endswith(('.', ':', '?', '!')) or cur['kind'] == 'p') else {'kind': 'p', 'indent': False}
                elif gap > 4 or not prevfull:
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
        info['drop'] = sorted({(round(ch['matrix'][4], 1), round(ch['matrix'][5], 1)) for w in drawn for ch in w['chars']})
        pages[pn] = info
    for it in items:
        it['src'] = clean(it['src'])
    empty = {it['id'] for it in items if not re.sub(r'<[^>]+>|\*\*|\s', '', it['src'])}
    items = [it for it in items if it['id'] not in empty]
    for info in pages.values():
        for fr in info['frames']: fr['items'] = [x for x in fr['items'] if x[0] not in empty]
        info['items'] = [x for x in info['items'] if x not in empty]
    with open(f'{out}/layout.json', 'w') as f:
        json.dump({'pages': pages, 'items': items}, f, ensure_ascii=False)
    with open(f'{out}/source.md', 'w') as f:
        for pn, info in pages.items():
            f.write(f'\n## PAGE {pn}\n')
            for r in info['runhead']: f.write(f'<<p{pn}_rh>> {r["text"]}\n')
            if info['h1']: f.write(f'<<p{pn}_h1>> {" ".join(r["text"] for r in info["h1"])}\n')
            for i, r in enumerate(info['toc']): f.write(f'<<p{pn}_toc{i+1}>> {r["text"]}\n')
            for c in info['captions']: f.write(f'<<{c["id"]}>> **{c["bold"]}** | {c["rest"]}\n')
            for c in info['cells']: f.write(f'<<{c["id"]}>> {c["src"]}\n')
        f.write('\n## BODY\n')
        for it in items:
            f.write(f'<<{it["id"]}>> [{it["kind"]}] {it["src"]}\n\n')
    print(len(items), 'items;', sum(len(p['frames']) for p in pages.values()), 'frames;',
          sum(len(p['cells']) for p in pages.values()), 'cells;', sum(len(p['captions']) for p in pages.values()), 'captions')

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
