#!/usr/bin/env python3
"""Write a translation onto the original PDF pages (original layout) — variant for Elsevier
books like Lower Extremity Soft Tissue & Cutaneous Plastic Surgery (layout.json from extract3.py).

Usage: layout3.py book.pdf layout.json tr.json out.pdf
Only the text that is redrawn is removed from the page (selective stripping by glyph position);
reference entries, page numbers, author lines, numbers-only labels keep their original glyphs.
"""
import io, json, re, sys, os, math
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream
from reportlab.pdfgen import canvas
from reportlab.lib.colors import CMYKColor, black
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Frame
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

DJ = '/usr/share/fonts/truetype/dejavu/'
CAR = '/usr/share/fonts/truetype/crosextra/'
for name, path in [('Serif', DJ + 'DejaVuSerifCondensed.ttf'), ('Serif-B', DJ + 'DejaVuSerifCondensed-Bold.ttf'),
                   ('Serif-I', DJ + 'DejaVuSerifCondensed-Italic.ttf'), ('Serif-BI', DJ + 'DejaVuSerifCondensed-BoldItalic.ttf'),
                   ('Sans', CAR + 'Carlito-Regular.ttf'), ('Sans-B', CAR + 'Carlito-Bold.ttf'),
                   ('Sans-I', CAR + 'Carlito-Italic.ttf'), ('Sans-BI', CAR + 'Carlito-BoldItalic.ttf')]:
    pdfmetrics.registerFont(TTFont(name, path))
for fam in ('Serif', 'Sans'):
    addMapping(fam, 0, 0, fam); addMapping(fam, 1, 0, fam + '-B'); addMapping(fam, 0, 1, fam + '-I'); addMapping(fam, 1, 1, fam + '-BI')

BLUE = CMYKColor(1, 1, 0, 0)
BODY_SIZE = float(os.environ.get('BODYSIZE', '8.2'))
PITCH, PARA_INDENT, BULLET_INDENT, Q_INDENT = 10.5, 8.5, 9.0, 14.2
VOW = set('aeıioöuüâîûAEIİOÖUÜÂÎÛ')
TEXT_OPS = {b'Tj', b'TJ', b"'", b'"'}
TAGRE = re.compile(r'<(/?)(i|sup|b)>')

def hyph_word(w):
    if len(w) < 7 or not w.isalpha(): return w
    idx = [i for i, ch in enumerate(w) if ch in VOW]
    cuts = []
    for a, b in zip(idx, idx[1:]):
        cut = a + 1 if b - a - 1 == 0 else b - 1
        if 2 <= cut <= len(w) - 2: cuts.append(cut)
    for cut in reversed(cuts): w = w[:cut] + '\xad' + w[cut:]
    return w

def hyphenate(t):
    out, depth = [], 0
    toks = re.split(r'(<[^>]+>|\(|\)|[^\W\d_]+)', t)
    for j, tok in enumerate(toks):
        if tok == '(': depth += 1
        elif tok == ')': depth = max(0, depth - 1)
        nxt = ''.join(toks[j + 1:j + 4]); prv = ''.join(toks[max(0, j - 3):j])
        near_tag = re.match(r'[^\w<*]*(<|\*\*)', nxt) or re.search(r'(>|\*\*)[^\w>*]*$', prv)
        if tok and re.fullmatch(r'[^\W\d_]+', tok) and depth == 0 and not near_tag: tok = hyph_word(tok)
        out.append(tok)
    return ''.join(out)

def cmyk(c):
    if isinstance(c, (list, tuple)) and len(c) == 4: return CMYKColor(*c)
    if isinstance(c, (list, tuple)) and len(c) == 1: return CMYKColor(0, 0, 0, c[0])
    return black

def baseline(line):
    return line['bottom'] - 0.2 * line['size']

def esc(t, link=True):
    t = TAGRE.sub(lambda m: '\x01' + m.group(1) + m.group(2) + '\x02', t)
    t = t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    for tg in ('i', 'b'):
        t = t.replace(f'\x01{tg}\x02', f'<{tg}>').replace(f'\x01/{tg}\x02', f'</{tg}>')
    t = t.replace('\x01sup\x02', '<super rise="2.8" size="5.1">').replace('\x01/sup\x02', '</super>')
    t = re.sub(r'(\d) (?=(mm|cm|μm|µm|mL|ml|mg|kg|g|%|°C)\b)', '\\1\u00a0', t)
    t = t.replace('\n', '<br/>')
    rep = r'<font color="#2e3192">\1</font>' if link else r'<b>\1</b>'
    return re.sub(r'\*\*(.+?)\*\*', rep, t, flags=re.S)

# ---------- selective text removal ----------
def mul(m, n):
    a, b, c, d, e, f = m; a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + b * c2, a * b2 + b * d2, c * a2 + d * c2, c * b2 + d * d2, e * a2 + f * c2 + e2, e * b2 + f * d2 + f2)

def strip_text(writer, page, drop, W):
    """Remove text-showing operators whose glyph run contains a word that will be redrawn.
    A run spans from its start to the next run start on the same baseline."""
    stats = {'drop': 0, 'keep': 0}
    def walk(ops, ctm0):
        res = []; ctm = ctm0; stack = []
        tm = tlm = (1, 0, 0, 1, 0, 0); leading = 0; rise = 0; fsize = 1.0
        for i, (operands, op) in enumerate(ops):
            if op == b'Tf': fsize = float(operands[1])
            if op == b'q': stack.append(ctm)
            elif op == b'Q': ctm = stack.pop() if stack else ctm
            elif op == b'cm': ctm = mul(tuple(float(v) for v in operands), ctm)
            elif op == b'BT': tm = tlm = (1, 0, 0, 1, 0, 0)
            elif op == b'Ts': rise = float(operands[0])
            elif op == b'TL': leading = float(operands[0])
            elif op == b'Tm': tm = tlm = tuple(float(v) for v in operands)
            elif op in (b'Td', b'TD'):
                tx, ty = float(operands[0]), float(operands[1])
                if op == b'TD': leading = -ty
                tlm = mul((1, 0, 0, 1, tx, ty), tlm); tm = tlm
            elif op == b'T*' or op in (b"'", b'"'):
                tlm = mul((1, 0, 0, 1, 0, -leading), tlm); tm = tlm
            if op in TEXT_OPS:
                m = mul(mul((1, 0, 0, 1, 0, rise), tm), ctm)
                x0 = m[4]
                if op == b'TJ' and len(operands[0]) and not isinstance(operands[0][0], (str, bytes)):
                    try: x0 += -float(operands[0][0]) / 1000 * fsize * m[0]
                    except Exception: pass
                res.append((i, x0, m[5]))
                tm = mul((1, 0, 0, 1, 0.01, 0), tm)      # successive runs without positioning: same start, tiny shift
        return res
    cs = ContentStream(page.get_contents(), writer)
    runs = walk(cs.operations, (1, 0, 0, 1, 0, 0))
    spans, dropi = [], set()
    byy = {}
    for dx, dy in drop: byy.setdefault(round(dy), []).append((dx, dy))
    near = lambda y: byy.get(round(y), []) + byy.get(round(y) - 1, []) + byy.get(round(y) + 1, [])
    for i, x, y in runs:
        nxt = [x2 for j, x2, y2 in runs if abs(y2 - y) < 0.8 and x2 > x + 0.5]
        end = min(nxt) if nxt else W + 10
        hit = any(abs(dy - y) < 0.8 and x - 1.0 <= dx < end - 0.5 for dx, dy in near(y))
        if hit: dropi.add(i); spans.append((y, x, end)); stats['drop'] += 1
        else: stats['keep'] += 1
    ops = []
    for i, (operands, op) in enumerate(cs.operations):
        if i in dropi:
            if op in (b"'", b'"'): ops.append(([], b'T*'))
            continue
        ops.append((operands, op))
    cs.operations = ops
    page.replace_contents(cs)
    stats['spans'] = spans
    return stats

# ---------- text splitting across frames ----------
def balance(parts):
    out, carry = [], []
    for p in parts:
        p = ''.join(carry) + p; carry = []
        if p.count('**') % 2: p += '**'; carry.append('**')
        depth = []
        for m in TAGRE.finditer(p):
            if m.group(1):
                if depth: depth.pop()
            else: depth.append(m.group(2))
        for tg in reversed(depth): p += f'</{tg}>'
        carry += [f'<{tg}>' for tg in depth]
        out.append(p)
    return out

def split_share(text, segs):
    if len(segs) == 1: return [text]
    words = text.split(' ')
    letters = [len(re.findall(r'[^\W\d_]', TAGRE.sub('', w))) for w in words]
    total = sum(letters) or 1
    src_total = sum(s['letters'] for s in segs) or 1
    parts, start, acc, cum = [], 0, 0, 0
    for s in segs[:-1]:
        cum += s['letters'] / src_total
        target = cum * total
        i = start
        while i < len(words) and acc + letters[i] / 2 < target:
            acc += letters[i]; i += 1
        parts.append(' '.join(words[start:i])); start = i
    parts.append(' '.join(words[start:]))
    return balance(parts)

def styles(scale, lf=1.0):
    s = scale
    base = ParagraphStyle('p', fontName='Serif', fontSize=BODY_SIZE * s, leading=PITCH * s * lf, alignment=TA_JUSTIFY,
                          splitLongWords=0, allowWidows=1, allowOrphans=1, embeddedHyphenation=1, hyphenationLang='')
    return {
        'p': base,
        'pi': ParagraphStyle('pi', parent=base, firstLineIndent=PARA_INDENT * s),
        'q': ParagraphStyle('q', parent=base, leftIndent=Q_INDENT),
        'li': ParagraphStyle('li', parent=base, leftIndent=BULLET_INDENT, bulletIndent=0, bulletFontName='Sans', bulletFontSize=BODY_SIZE * s * 1.15),
        'lic': ParagraphStyle('lic', parent=base, leftIndent=BULLET_INDENT),
        'h2': ParagraphStyle('h2', fontName='Sans-B', fontSize=11 * s, leading=13 * s, alignment=TA_LEFT, leftIndent=2.8),
        'h3': ParagraphStyle('h3', fontName='Sans-B', fontSize=11 * s, leading=13 * s, alignment=TA_LEFT),
        'h4': ParagraphStyle('h4', fontName='Sans-B', fontSize=10 * s, leading=12 * s, alignment=TA_LEFT),
        'h5': ParagraphStyle('h5', fontName='Sans-I', fontSize=10 * s, leading=12 * s, alignment=TA_LEFT),
    }

def flowables(frame, L, scale, parts, lf=1.0):
    st = styles(scale, lf)
    items = {it['id']: it for it in L['items']}
    fl = []
    for iid, si in frame['items']:
        it = items[iid]
        text = parts[iid][si]
        first = si == 0
        k = it['kind']
        if k == 'p': style = st['pi'] if (it['indent'] and first) else st['p']
        elif k == 'li': style = st['li'] if first else st['lic']
        else: style = st[k]
        para = Paragraph(hyphenate(esc(text)) if not k.startswith('h') else esc(text), style,
                         bulletText='•' if (k == 'li' and first) else None)
        para._gap = it['segs'][si]['gap'] * scale if first else 0
        para._kind = k
        para.spaceBefore = para._gap
        fl.append(para)
    return fl

def fill(frames, fl, c):
    fl = list(fl); fi = 0
    while fl and fi < len(frames):
        fr = frames[fi]; f = fl[0]
        if fr.add(f, c):
            fl.pop(0); continue
        parts = fr.split(f, c)
        if parts:
            fr.add(parts[0], c)
            for p in parts[1:]: p._kind = f._kind; p._gap = 0
            fl[0:1] = parts[1:]
        fi += 1
    return not fl

def make_frames(info, slack=3):
    H = info['h']
    out = []
    for f in info['frames']:
        sl = max(slack, f.get('ext', 0))
        top = f['top'] - (1.5 if f.get('head') else 0)
        out.append(Frame(f['x0'], H - f['bottom'] - sl, f['x1'] - f['x0'] + 0.5, f['bottom'] - top + sl + 2,
                         leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0))
    return out

def fit_text(c, text, font, size, x, y, maxw=None, align='left', color=black):
    if maxw:
        while pdfmetrics.stringWidth(text, font, size) > maxw and size > 4: size -= 0.1
    c.setFont(font, size); c.setFillColor(color)
    if align == 'right': c.drawRightString(x, y, text)
    elif align == 'center': c.drawCentredString(x, y, text)
    else: c.drawString(x, y, text)

def sans(font):
    b, i = 'Bold' in font or 'Black' in font, 'Italic' in font
    return 'Sans' + ('-B' if b and not i else '-I' if i and not b else '-BI' if b and i else '')

def merge_hanging(cells, T):
    """Join hanging-indent continuation lines of numbered/bulleted items (split by the extractor) into their item."""
    cells = [dict(x) for x in sorted(cells, key=lambda x: (x['top'], x['x0']))]
    for x in cells: x['tr'] = T.get(x['id'], x['src'])
    out = []
    for b in cells:
        host = None
        for a in out:
            last = a['src'].split('\n')[-1]
            if (0 <= b['top'] - a['bottom'] < 4 and 1.5 < b['x0'] - a['x0'] < 14 and abs(a['size'] - b['size']) < .3
                    and a['bold'] == b['bold'] and re.match(r'(\d+\.|[a-z]\.|•|–)\s', last)):
                host = a
        if host:
            host['tr'] = host['tr'].rstrip() + ' ' + b['tr'].lstrip()
            host['src'] = host['src'] + ' ' + b['src'].replace('\n', ' ')
            host['bottom'] = b['bottom']; host['x1'] = max(host['x1'], b['x1'])
        else:
            out.append(b)
    return out

def draw_cells(c, info, T, pn):
    H = info['h']; cells = merge_hanging(info['cells'], T)
    for cell in cells:
        tr = cell['tr']
        if not tr.strip(): continue
        x0 = cell['x0']; w0 = cell['x1'] - cell['x0']
        # room to the right: next cell starting on overlapping rows
        cx0, cx1 = info['cx0'], info['cx1']
        if cell['x1'] <= cx1[0] + 3: right = cx1[0] + 2
        elif cell['x1'] <= cx1[1] + 2: right = cx1[1] + 2
        else: right = info['w'] - 12
        for o in cells:
            if o is cell: continue
            if o['x0'] > cell['x1'] - 1 and o['top'] < cell['bottom'] + 1 and o['bottom'] > cell['top'] - 1:
                right = min(right, o['x0'] - 3)
        avail_w = max(w0, min(right - x0, w0 * 1.6 + 10))
        below = info['h']
        for o in cells:
            if o is cell: continue
            if o['top'] >= cell['bottom'] - 1 and o['x0'] < x0 + avail_w and o['x1'] > x0:
                below = min(below, o['top'])
        avail_h = (cell['bottom'] - cell['top']) + max(0, min(below - cell['bottom'] - 2, cell['size'] * 2.4))
        font = sans(cell['font']) if 'Arial' not in cell['font'] else ('Sans-B' if cell['bold'] else 'Sans')
        size = cell['size']
        col = cmyk(cell['color'])
        while True:
            st = ParagraphStyle('c', fontName=font, fontSize=size, leading=size * 1.2, alignment=TA_LEFT, textColor=col)
            p = Paragraph(esc(tr, link=False), st)
            pw, ph = p.wrap(avail_w, 1000)
            if ph <= avail_h + 0.5 or size < 5.2: break
            size -= 0.15
        p.drawOn(c, x0, H - cell['top'] - ph + size * 0.18)

def draw_page(c, pn, L, T, parts):
    info = L['pages'][str(pn)]
    H, W = info['h'], info['w']
    # running head
    for r in info['runhead']:
        y = H - baseline(r)
        tr = T.get(f'p{pn}_rh', r['text']).strip()
        if r['x0'] > W / 2 - 50:      # odd page: right-aligned before the chapter tab
            fit_text(c, tr, 'Serif', r['size'], r['x1'], y, maxw=r['x1'] - 230, align='right')
        else:
            fit_text(c, tr, 'Serif', r['size'], r['x0'], y, maxw=440)
    for t in info['tab']:
        fit_text(c, 'Bölüm', 'Serif', t['size'], t['x0'] - 3, H - baseline(t), maxw=t['x1'] - t['x0'] + 12, color=cmyk(t['color']))
    for t in info['chap']:
        fit_text(c, 'Bölüm', 'Serif', t['size'], t['x1'], H - baseline(t), align='right', color=cmyk(t['color']))
    if info['h1']:
        tr = T.get(f'p{pn}_h1', ' '.join(x['text'] for x in info['h1']))
        l1 = info['h1'][0]
        st = ParagraphStyle('h1', fontName='Serif', fontSize=l1['size'], leading=l1['size'] * 1.17, textColor=cmyk(l1['color']))
        size = l1['size']
        while True:
            st.fontSize = size; st.leading = size * 1.17
            p = Paragraph(esc(tr), st); _, ph = p.wrap(info['cx1'][1] - l1['x0'], 500)
            if ph <= (info['h1'][-1]['bottom'] - l1['top']) * 1.05 + 2 or size < 14: break
            size -= 0.5
        p.drawOn(c, l1['x0'], H - l1['top'] - ph + size * 0.25)
    for t in info['tochead']:
        fit_text(c, 'BÖLÜM İÇERİĞİ', 'Sans-B', t['size'], t['x0'], H - baseline(t), color=cmyk(t['color']))
    for i, t in enumerate(info['toc']):
        tr = T.get(f'p{pn}_toc{i+1}', t['text'])
        y = H - baseline(t)
        last = t['parts'][-1]
        m = re.match(r'(.*?)\s+(\d+)$', tr)
        if m and re.fullmatch(r'\d+', last['t']):
            fit_text(c, m.group(2), sans(last['font']), t['size'], last['x1'], y, align='right', color=cmyk(t['color']))
            tr = m.group(1)
        fit_text(c, tr, sans(t['parts'][0]['font']), t['size'], t['x0'], y, maxw=last['x0'] - t['x0'] - 6, color=cmyk(t['color']))
    # captions
    for cap in info['captions']:
        bold, rest = T.get(cap['id'], [cap['bold'], cap['rest']])
        w = cap['right'] - cap['x0']
        avail = (cap['bottom'] - cap['top']) * 1.12 + 3
        size = cap['size']
        while True:
            st = ParagraphStyle('c', fontName='Sans', fontSize=size, leading=size * 1.2, alignment=TA_LEFT)
            rest_h = esc(rest, link=False)
            rest_h = re.sub(r'<i>', '<font size="%.1f"><i>' % (size * 0.88), rest_h).replace('</i>', '</i></font>')
            p = Paragraph((f'<font color="#4d4d4d"><b>{esc(bold, link=False)}</b></font> ' if bold else '') + rest_h, st)
            _, h = p.wrap(w, 1000)
            if h <= avail or size < 5.8: break
            size -= 0.1
        p.drawOn(c, cap['x0'], H - cap['top'] - h + size * 0.2)
    draw_cells(c, info, T, pn)
    # body: each frame gets the largest font scale (<= 1) at which its text fits
    frames = info['frames']
    rframes = make_frames(info)
    dummy = lambda: canvas.Canvas(io.BytesIO(), pagesize=(W, H))
    scales = []
    for fd in frames:
        best = None
        for sc in [x / 100 for x in range(100, 69, -2)]:
            fr = make_frames({'h': H, 'frames': [fd]})[0]
            if fill([fr], flowables(fd, L, sc, parts), dummy()):
                best = sc; break
        if best is None:
            best = 0.7; print(f'page {pn}: frame text does not fit even at scale 0.7', file=sys.stderr)
        lf = 1.0
        for cand in (1.06, 1.03):
            fr = make_frames({'h': H, 'frames': [fd]})[0]
            if fill([fr], flowables(fd, L, best, parts, cand), dummy()): lf = cand; break
        fr = make_frames({'h': H, 'frames': [fd]})[0]
        fill([fr], flowables(fd, L, best, parts, lf), c)
        scales.append(best)
    return min(scales) if scales else 1.0

def main(pdf, layout, trf, out):
    L = json.load(open(layout)); T = json.load(open(trf))
    for p in L['pages'].values():
        for f in p['frames']:
            below = [g['top'] for g in p['frames'] if g['col'] == f['col'] and g['top'] > f['bottom']]
            if below and min(below) - f['bottom'] < 45: f['ext'] = max(3, min(below) - f['bottom'] - 14)
            elif not below and f['bottom'] < 725: f['ext'] = min(10, 728 - f['bottom'])
    for it in L['items']:
        if it['kind'].startswith('h'):
            for s in it['segs']: L['pages'][str(s['page'])]['frames'][s['frame']]['head'] = True
    # bullet items whose continuation lines were extracted as separate indented ('q') items: join them back
    host, keep = None, []
    for it in L['items']:
        if it['kind'] == 'q' and host is not None and len(it['segs']) == 1 and \
                (it['segs'][0]['page'], it['segs'][0]['frame']) == (host['segs'][-1]['page'], host['segs'][-1]['frame']):
            T[host['id']] = T[host['id']].rstrip() + ' ' + T[it['id']].lstrip()
            host['segs'][-1]['letters'] += it['segs'][0]['letters']
            fr = L['pages'][str(it['segs'][0]['page'])]['frames'][it['segs'][0]['frame']]
            fr['items'] = [x for x in fr['items'] if x[0] != it['id']]
            continue
        host = it if it['kind'] == 'li' else None
        keep.append(it)
    L['items'] = keep
    parts = {it['id']: split_share(T[it['id']], it['segs']) for it in L['items']}
    reader = PdfReader(pdf)
    writer = PdfWriter()
    report, st = {}, {}
    for pn in sorted(int(p) for p in L['pages']):
        writer.add_page(reader.pages[pn - 1])
        page = writer.pages[-1]
        info = L['pages'][str(pn)]
        st[pn] = strip_text(writer, page, info['drop'], info['w'])
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(info['w'], info['h']))
        for fx in info.get('fixed', []):
            for ln in fx['lines']:
                x, y = ln['pos']
                if any(abs(sy - y) < 0.8 and sx - 1 <= x < se - 0.5 for sy, sx, se in st[pn]['spans']):
                    fit_text(c, ln['text'], 'Sans-B' if fx['bold'] else 'Sans', fx['size'], x, y, color=cmyk(fx['color']))
        report[pn] = draw_page(c, pn, L, T, parts)
        c.showPage(); c.save()
        page.merge_page(PdfReader(buf).pages[0])
    writer.write(out)
    print('font scale per page:', report)


if __name__ == '__main__':
    main(*sys.argv[1:])
