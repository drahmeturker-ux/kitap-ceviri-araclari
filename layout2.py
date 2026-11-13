#!/usr/bin/env python3
"""Write a translation onto the original PDF pages (original layout) — variant for
Thieme books like Essentials of Septorhinoplasty (mirrored margins, superscript
citations, italics, gray boxes, vector figure labels, chapter-opener TOC page).

Usage: layout2.py book.pdf layout.json tr.json out.pdf   (layout.json from extract2.py)
"""
import io, json, re, sys
import pdfplumber
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

import os
LIB = '/usr/share/fonts/truetype/liberation/'
DJ = '/usr/share/fonts/truetype/dejavu/'
CAR = '/usr/share/fonts/truetype/crosextra/'
SERIF = [('Serif', DJ + 'DejaVuSerifCondensed.ttf'), ('Serif-B', DJ + 'DejaVuSerifCondensed-Bold.ttf'),
         ('Serif-I', DJ + 'DejaVuSerifCondensed-Italic.ttf'), ('Serif-BI', DJ + 'DejaVuSerifCondensed-BoldItalic.ttf')] \
    if os.environ.get('BODYFONT', 'dejavu') == 'dejavu' else \
        [('Serif', LIB + 'LiberationSerif-Regular.ttf'), ('Serif-B', LIB + 'LiberationSerif-Bold.ttf'),
         ('Serif-I', LIB + 'LiberationSerif-Italic.ttf'), ('Serif-BI', LIB + 'LiberationSerif-BoldItalic.ttf')]
for name, path in SERIF + [
                   ('Sans', CAR + 'Carlito-Regular.ttf'), ('Sans-B', CAR + 'Carlito-Bold.ttf'),
                   ('Sans-I', CAR + 'Carlito-Italic.ttf'), ('Sans-BI', CAR + 'Carlito-BoldItalic.ttf')]:
    pdfmetrics.registerFont(TTFont(name, path))
for fam in ('Serif', 'Sans'):
    addMapping(fam, 0, 0, fam); addMapping(fam, 1, 0, fam + '-B'); addMapping(fam, 0, 1, fam + '-I'); addMapping(fam, 1, 1, fam + '-BI')

RED = CMYKColor(0.161, 1, 0.869, 0.064)
BODY_SIZE = float(os.environ.get('BODYSIZE', '8.7'))
PITCH, PARA_INDENT, BULLET_INDENT = 11.0, 14.2, 9.9
VOW = set('aeıioöuüâîûAEIİOÖUÜÂÎÛ')

def hyph_word(w):
    """Turkish syllable breaks (soft hyphens) for one plain word."""
    if len(w) < 7 or not w.isalpha(): return w
    idx = [i for i, ch in enumerate(w) if ch in VOW]
    cuts = []
    for a, b in zip(idx, idx[1:]):
        k = b - a - 1
        cut = a + 1 if k == 0 else b - 1
        if 2 <= cut <= len(w) - 2: cuts.append(cut)
    for cut in reversed(cuts): w = w[:cut] + '\xad' + w[cut:]
    return w

def hyphenate(t):
    out, depth = [], 0
    toks = re.split(r'(<[^>]+>|\(|\)|[^\W\d_]+)', t)
    for j, tok in enumerate(toks):
        if tok == '(': depth += 1
        elif tok == ')': depth = max(0, depth - 1)
        # reportlab drops/doubles the space next to a tag when the adjacent word has soft hyphens
        nxt = ''.join(toks[j + 1:j + 4])
        prv = ''.join(toks[max(0, j - 3):j])
        near_tag = re.match(r'[^\w<*]*(<|\*\*)', nxt) or re.search(r'(>|\*\*)[^\w>*]*$', prv)
        if tok and re.fullmatch(r'[^\W\d_]+', tok) and depth == 0 and not near_tag: tok = hyph_word(tok)
        out.append(tok)
    return ''.join(out)
TEXT_OPS = {b'Tj', b'TJ', b"'", b'"'}
TAGRE = re.compile(r'<(/?)(i|sup)>')

def cmyk(c):
    if isinstance(c, (list, tuple)) and len(c) == 4: return CMYKColor(*c)
    return black

def baseline(line):
    return line['bottom'] - 0.2 * line['size']

def esc(t):
    t = TAGRE.sub(lambda m: '\x01' + m.group(1) + m.group(2) + '\x02', t)
    t = t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    t = t.replace('\x01i\x02', '<i>').replace('\x01/i\x02', '</i>')
    t = t.replace('\x01sup\x02', '<super rise="2.6" size="5.4">').replace('\x01/sup\x02', '</super>')
    t = re.sub(r'(\d) (?=(mm|cm|μm|µm|W|mbar|%|N)\b)', '\\1\u00a0', t)
    t = t.replace('\n', '<br/>')
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t, flags=re.S)

def strip_text(writer, page):
    cs = ContentStream(page.get_contents(), writer)
    cs.operations = [(o, op) for o, op in cs.operations if op not in TEXT_OPS]
    page.replace_contents(cs)
    seen = set()
    def walk(res):
        if not res: return
        xo = res.get_object().get('/XObject')
        if not xo: return
        for k, v in xo.get_object().items():
            o = v.get_object()
            if id(o) in seen or o.get('/Subtype') != '/Form': continue
            seen.add(id(o))
            c2 = ContentStream(o, writer)
            c2.operations = [(a, op) for a, op in c2.operations if op not in TEXT_OPS]
            o.set_data(c2.get_data())
            walk(o.get('/Resources'))
    walk(page.get('/Resources'))

def balance(parts):
    """Keep **, <i>, <sup> balanced across split parts."""
    out, carry = [], []
    for p in parts:
        p = ''.join(carry) + p
        carry = []
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
        'li': ParagraphStyle('li', parent=base, leftIndent=BULLET_INDENT, bulletIndent=0, bulletFontName='Serif', bulletFontSize=BODY_SIZE * s),
        'lic': ParagraphStyle('lic', parent=base, leftIndent=BULLET_INDENT),
        'li2': ParagraphStyle('li2', parent=base, leftIndent=2 * BULLET_INDENT, bulletIndent=BULLET_INDENT, bulletFontName='Serif', bulletFontSize=BODY_SIZE * s),
        'li2c': ParagraphStyle('li2c', parent=base, leftIndent=2 * BULLET_INDENT),
        'h2': ParagraphStyle('h2', fontName='Sans-B', fontSize=15 * s, leading=17.5 * s, textColor=RED, alignment=TA_LEFT),
        'h3': ParagraphStyle('h3', fontName='Sans-B', fontSize=13 * s, leading=15.4 * s, textColor=RED, alignment=TA_LEFT),
        'h4': ParagraphStyle('h4', fontName='Sans-B', fontSize=12 * s, leading=14 * s, textColor=RED, alignment=TA_LEFT),
        'h5': ParagraphStyle('h5', fontName='Sans-B', fontSize=11 * s, leading=13 * s, alignment=TA_LEFT),
        'h6': ParagraphStyle('h6', fontName='Sans-BI', fontSize=10 * s, leading=12 * s, alignment=TA_LEFT),
    }

def flowables(frame, L, T, scale, parts, lf=1.0):
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
        elif k == 'li2': style = st['li2'] if first else st['li2c']
        else: style = st[k]
        para = Paragraph(hyphenate(esc(text)) if not k.startswith('h') else esc(text), style, bulletText=('•' if k == 'li' else '–') if (k in ('li', 'li2') and first) else None)
        para._gap = it['segs'][si]['gap'] * scale if first else 0
        para._kind = k
        para.spaceBefore = para._gap
        fl.append(para)
    return fl

def fill(frames, fl, c):
    fl = list(fl)
    fi = 0
    while fl and fi < len(frames):
        fr = frames[fi]
        f = fl[0]
        if f._kind.startswith('h') and len(fl) > 1:
            need = f.wrap(fr._aW, fr._aH)[1] + f._gap + 3 * PITCH
            if fr._y - fr._y1p < need and not fr._atTop:
                fi += 1; continue
        if fr.add(f, c):
            fl.pop(0); continue
        parts = fr.split(f, c)
        if parts:
            fr.add(parts[0], c)
            for p in parts[1:]:
                p._kind = f._kind; p._gap = 0
            fl[0:1] = parts[1:]
        fi += 1
    return not fl

def make_frames(info, slack=3):
    H = info['h']
    return [Frame(f['x0'], H - f['bottom'] - slack, f['x1'] - f['x0'] + 0.5, f['bottom'] - f['top'] + slack + 2,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0) for f in info['frames']]

def fit_text(c, text, font, size, x, y, maxw=None, align='left', color=black):
    if maxw:
        while pdfmetrics.stringWidth(text, font, size) > maxw and size > 4: size -= 0.1
    c.setFont(font, size); c.setFillColor(color)
    if align == 'right': c.drawRightString(x, y, text)
    elif align == 'center': c.drawCentredString(x, y, text)
    else: c.drawString(x, y, text)

def sans(font, medium_bold=False):
    b, i = 'Bold' in font or (medium_bold and 'Medium' in font), 'Italic' in font
    return 'Sans' + ('-B' if b and not i else '-I' if i and not b else '-BI' if b and i else '')

def draw_page(c, pn, L, T, parts, plpage):
    info = L['pages'][str(pn)]
    H, W = info['h'], info['w']
    # decorative giant numerals (exact baseline from char matrix)
    for ch in plpage.chars:
        if ch['size'] > 100:
            col = ch.get('non_stroking_color')
            c.setFillColor(cmyk(list(col)) if isinstance(col, (list, tuple)) else black)
            c.setFont('Serif', ch['size']); c.drawString(ch['matrix'][4], ch['matrix'][5], ch['text'])
    # reference entries on mixed pages: redrawn char by char, unchanged
    for ch in plpage.chars:
        if 'Gulliver' in ch['fontname'] and 6.2 <= ch['size'] < 6.8:
            c.setFillColor(black); c.setFont('Serif', ch['size']); c.drawString(ch['matrix'][4], ch['matrix'][5], ch['text'])
    # running head: bold parts (page number) kept, medium parts translated
    for r in info['runhead']:
        y = H - baseline(r)
        bold = [p for p in r['parts'] if 'Bold' in p['font']]
        txt = [p for p in r['parts'] if 'Bold' not in p['font']]
        for p in bold: fit_text(c, p['t'], 'Sans-B', r['size'], p['x0'], y)
        tr = T.get(f'p{pn}_rh', '').strip()
        if not txt or not tr: continue
        if bold and bold[0]['x0'] > txt[-1]['x0']:   # odd page: text right-aligned before the number
            right = bold[0]['x0'] - (bold[0]['x0'] - (txt[-1]['x0'] + pdfmetrics.stringWidth(txt[-1]['t'], 'Sans', r['size'])))
            fit_text(c, tr, 'Sans', r['size'], right, y, align='right')
        else:
            fit_text(c, tr, 'Sans', r['size'], txt[0]['x0'], y, maxw=info['colr'][1] - txt[0]['x0'])
    # chapter title
    if info['h1']:
        l1 = info['h1'][0]
        num = l1['parts'][0]
        x_text = l1['parts'][1]['x0']
        fit_text(c, num['t'], 'Sans-B', l1['size'], num['x0'], H - baseline(l1), color=RED)
        fit_text(c, T[f'p{pn}_h1'], 'Sans-B', l1['size'], x_text, H - baseline(l1), maxw=info['colr'][1] - x_text, color=RED)
    for a in info['author']:
        fit_text(c, a['text'], 'Sans-I', a['size'], a['x0'], H - baseline(a))
    # chapter opener TOC
    for i, t in enumerate(info['toc']):
        tr = T.get(f'p{pn}_toc{i+1}', t['text'])
        col = cmyk(t['color']); y = H - baseline(t)
        last = t['parts'][-1]
        if len(t['parts']) > 1 and 'Italic' in last['font'] and last['t'].isdigit():
            fit_text(c, last['t'], 'Sans-I', t['size'], last['x0'], y, color=col)
            tr = re.sub(r'\s*\d+$', '', tr); right = last['x0'] - 6
        else:
            right = 595
        if re.fullmatch(r'\d+', t['text']):
            fit_text(c, tr, 'Sans-I', t['size'], t['x0'], y, color=col)
        elif t['x0'] < 363:
            fit_text(c, tr, sans(t['font'], True), t['size'], t['x1'], y, maxw=270, align='right', color=col)
        else:
            m = re.match(r'(\d+\.\d+)\s+(.*)', tr)
            if m and t['parts'][0]['t'] == m.group(1):
                fit_text(c, m.group(1), sans(t['font'], True), t['size'], t['x0'], y, color=col)
                fit_text(c, m.group(2), sans(t['font'], True), t['size'], t['parts'][1]['x0'], y, maxw=right - t['parts'][1]['x0'], color=col)
            else:
                fit_text(c, tr, sans(t['font'], True), t['size'], t['x0'], y, maxw=right - t['x0'], color=col)
    # figure labels
    labs = T.get(f'p{pn}_labels', [])
    li = 0
    for lb in info['labels']:
        txt = lb['text']
        if len(re.findall(r'[^\W\d_]', txt)) > 1 and li < len(labs):
            txt = labs[li]; li += 1
        w0 = lb['x1'] - lb['x0']
        fit_text(c, txt, sans(lb['font']), lb['size'], lb['x0'], H - baseline(lb), maxw=max(w0 * 1.2, w0 + 8), color=cmyk(lb['color']))
    # gray boxes
    for b in info['boxes']:
        tr = T.get(b['id'], [x['t'] for x in b['lines']])
        x0 = min(x['x0'] for x in b['lines'])
        size = 9.0
        while True:
            st = ParagraphStyle('b', fontName='Sans', fontSize=size, leading=size * 1.22, alignment=TA_LEFT)
            sb = ParagraphStyle('bl', parent=st, leftIndent=9.9, bulletIndent=0)
            fl = [Paragraph(esc(t), ParagraphStyle('bh', parent=st, fontName='Sans-B', spaceAfter=2)) if x['k'] == 'h'
                  else Paragraph(esc(t), sb, bulletText='•') for x, t in zip(b['lines'], tr)]
            h = sum(p.wrap(b['x1'] - x0 - 6, 1000)[1] + p.style.spaceAfter for p in fl)
            if h <= b['bottom'] - b['lines'][0]['top'] - 3 or size < 6: break
            size -= 0.2
        y = H - b['lines'][0]['top'] + 1
        for p in fl:
            _, ph = p.wrap(b['x1'] - x0 - 6, 1000)
            p.drawOn(c, x0, y - ph); y -= ph + p.style.spaceAfter
    # captions
    for cap in info['captions']:
        bold, rest = T.get(cap['id'], [cap['bold'], cap['rest']])
        if not re.search(r'[^\W\d_]{2}', cap['bold'] + cap['rest']):
            fit_text(c, (cap['bold'] + ' ' + cap['rest']).strip(), 'Sans', cap['size'], cap['x0'], H - cap['bottom'] + 1.6)
            continue
        w = cap['right'] - cap['x0']
        avail = (cap['bottom'] - cap['top']) * 1.15 + 4
        size = cap['size'] * 1.07
        while True:
            st = ParagraphStyle('c', fontName='Sans', fontSize=size, leading=size * 1.22, alignment=TA_LEFT)
            p = Paragraph((f'<b>{esc(bold)}</b> ' if bold else '') + esc(rest), st)
            _, h = p.wrap(w, 1000)
            if h <= avail or size < 5.8: break
            size -= 0.1
        p.drawOn(c, cap['x0'], H - cap['top'] - h + size * 0.22)
    # body
    frames = info['frames']
    def all_fit(scale, cv, lf=1.0):
        ok = True
        for fr, fd in zip(make_frames(info), frames):
            ok &= fill([fr], flowables(fd, L, T, scale, parts, lf), cv)
        return ok
    dummy = lambda: canvas.Canvas(io.BytesIO(), pagesize=(W, H))
    for scale in [x / 100 for x in range(100, 79, -2)]:
        if all_fit(scale, dummy()):
            break
    else:
        print(f'page {pn}: text does not fit even at scale {scale}', file=sys.stderr)
    lf = 1.0
    for cand in (1.12, 1.08, 1.04):
        if all_fit(scale, dummy(), cand): lf = cand; break
    all_fit(scale, c, lf)
    return (scale, lf)

def draw_refpage(c, plpage, T, H):
    """Reference pages: entries redrawn char by char as in the source; only headings translated."""
    words = plpage.extract_words(extra_attrs=['fontname', 'size'])
    argo = [w for w in words if 'Argo' in w['fontname']]
    for ch in plpage.chars:
        if 'Argo' in ch['fontname']: continue
        col = ch.get('non_stroking_color')
        c.setFillColor(cmyk(list(col)) if isinstance(col, (list, tuple)) else black)
        c.setFont('Serif', ch['size']); c.drawString(ch['matrix'][4], ch['matrix'][5], ch['text'])
    rh = [w for w in argo if w['top'] < 75 and 'Bold' not in w['fontname']]
    for w in argo:
        y = H - (w['bottom'] - 0.2 * w['size'])
        if w['top'] < 75 and 'Bold' in w['fontname']: fit_text(c, w['text'], 'Sans-B', w['size'], w['x0'], y)
        elif w['top'] >= 75 and w['text'] == 'References': fit_text(c, 'Kaynaklar', 'Sans-B', w['size'], w['x0'], y)
    if rh:
        y = H - (rh[0]['bottom'] - 0.2 * rh[0]['size'])
        if [w['text'] for w in rh] == ['References']:
            fit_text(c, 'Kaynaklar', 'Sans', rh[0]['size'], rh[0]['x1'], y, align='right')
        else:
            fit_text(c, T.get('_chapter_rh', ' '.join(w['text'] for w in rh)), 'Sans', rh[0]['size'], rh[0]['x0'], y)

def main(pdf, layout, trf, out, keep=None):
    L = json.load(open(layout)); T = json.load(open(trf))
    parts = {it['id']: split_share(T[it['id']], it['segs']) for it in L['items']}
    reader = PdfReader(pdf)
    pl = pdfplumber.open(pdf)
    writer = PdfWriter()
    report = {}
    pns = sorted(int(p) for p in L['pages'])
    for pn in range(pns[0], (int(keep) if keep else pns[-1]) + 1):
        writer.add_page(reader.pages[pn - 1])
        page = writer.pages[-1]
        if pn not in pns:                    # reference pages: entries unchanged, headings translated
            if not pl.pages[pn - 1].chars: continue
            strip_text(writer, page)
            buf = io.BytesIO(); H = float(pl.pages[pn - 1].height)
            c = canvas.Canvas(buf, pagesize=(float(pl.pages[pn - 1].width), H))
            draw_refpage(c, pl.pages[pn - 1], T, H); c.showPage(); c.save()
            page.merge_page(PdfReader(buf).pages[0]); continue
        strip_text(writer, page)
        info = L['pages'][str(pn)]
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(info['w'], info['h']))
        report[pn] = draw_page(c, pn, L, T, parts, pl.pages[pn - 1])
        c.showPage(); c.save()
        page.merge_page(PdfReader(buf).pages[0])
    writer.write(out)
    print('font scale per page:', report)

if __name__ == '__main__':
    main(*sys.argv[1:])
