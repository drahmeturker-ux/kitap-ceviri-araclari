#!/usr/bin/env python3
"""Write a translation onto the original PDF pages (original layout).

Usage: layout.py book.pdf layout.json tr.json out.pdf

tr.json keys: item ids (body text, **bold** allowed), caption ids -> [bold title, rest],
p<N>_rh (running head text without page/chapter numbers), p<N>_h1 (chapter title).
Source text is removed from the page content streams (not covered), then the
translation is drawn with substitute fonts in the original frames.
"""
import io, json, re, sys, copy
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject
from reportlab.pdfgen import canvas
from reportlab.lib.colors import CMYKColor, black
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Frame
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

LIB = '/usr/share/fonts/truetype/liberation/'
CAR = '/usr/share/fonts/truetype/crosextra/'
for name, path in [('Serif', LIB + 'LiberationSerif-Regular.ttf'), ('Serif-B', LIB + 'LiberationSerif-Bold.ttf'),
                   ('Serif-I', LIB + 'LiberationSerif-Italic.ttf'), ('Serif-BI', LIB + 'LiberationSerif-BoldItalic.ttf'),
                   ('Sans', CAR + 'Carlito-Regular.ttf'), ('Sans-B', CAR + 'Carlito-Bold.ttf'),
                   ('Sans-I', CAR + 'Carlito-Italic.ttf'), ('Sans-BI', CAR + 'Carlito-BoldItalic.ttf')]:
    pdfmetrics.registerFont(TTFont(name, path))
for fam in ('Serif', 'Sans'):
    addMapping(fam, 0, 0, fam); addMapping(fam, 1, 0, fam + '-B'); addMapping(fam, 0, 1, fam + '-I'); addMapping(fam, 1, 1, fam + '-BI')

RED = CMYKColor(0.15, 1, 1, 0)
BODY_SIZE, PITCH, PARA_INDENT, BULLET_INDENT = 8.2, 11.2, 10.5, 11.4
TEXT_OPS = {b'Tj', b'TJ', b"'", b'"'}

def baseline(line):
    return line['bottom'] - 0.2 * line['size']

def esc(t):
    t = t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    t = re.sub(r'(\d) (?=(mm|cm|μm|N|%)\b)', '\\1\u00a0', t)   # keep number and unit together
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)

def strip_text(writer, page):
    def clean(obj, resources):
        cs = ContentStream(obj, writer)
        cs.operations = [(o, op) for o, op in cs.operations if op not in TEXT_OPS]
        return cs
    page.replace_contents(clean(page.get_contents(), None))
    res = page.get('/Resources')
    seen = set()
    def walk(res):
        if not res: return
        xo = res.get_object().get('/XObject')
        if not xo: return
        for k, v in xo.get_object().items():
            o = v.get_object()
            if id(o) in seen or o.get('/Subtype') != '/Form': continue
            seen.add(id(o))
            cs = ContentStream(o, writer)
            cs.operations = [(a, op) for a, op in cs.operations if op not in TEXT_OPS]
            o.set_data(cs.get_data())
            walk(o.get('/Resources'))
    walk(res)

def split_share(text, segs):
    """Split a translated paragraph into per-page parts by the source letter shares."""
    if len(segs) == 1: return [text]
    words = text.split(' ')
    letters = [len(re.findall(r'[^\W\d_]', w)) for w in words]
    total = sum(letters) or 1
    src_total = sum(s['letters'] for s in segs) or 1
    parts, start, acc = [], 0, 0
    cum = 0
    for s in segs[:-1]:
        cum += s['letters'] / src_total
        target = cum * total
        i = start
        while i < len(words) and acc + letters[i] / 2 < target:
            acc += letters[i]; i += 1
        parts.append(' '.join(words[start:i])); start = i
    parts.append(' '.join(words[start:]))
    # keep **bold** pairs balanced across the cut
    out = []
    for p in parts:
        if p.count('**') % 2:
            p = p + '**' if p.rfind('**') > p.rfind(' ') - 0 and not p.endswith('**') else '**' + p
        out.append(p)
    return out

def styles(scale):
    s = scale
    base = ParagraphStyle('p', fontName='Serif', fontSize=BODY_SIZE * s, leading=PITCH * s, alignment=TA_JUSTIFY,
                          splitLongWords=0, allowWidows=1, allowOrphans=1)
    return {
        'p': base,
        'pi': ParagraphStyle('pi', parent=base, firstLineIndent=PARA_INDENT * s),
        'li': ParagraphStyle('li', parent=base, leftIndent=BULLET_INDENT, bulletIndent=0, bulletFontName='Serif', bulletFontSize=BODY_SIZE * s),
        'lic': ParagraphStyle('lic', parent=base, leftIndent=BULLET_INDENT),
        'h2': ParagraphStyle('h2', fontName='Sans-B', fontSize=11.9 * s, leading=14 * s, textColor=RED, alignment=TA_LEFT),
        'h3': ParagraphStyle('h3', fontName='Sans-B', fontSize=9.9 * s, leading=12 * s, alignment=TA_LEFT),
        'h4': ParagraphStyle('h4', fontName='Sans-B', fontSize=9.0 * s, leading=PITCH * s, alignment=TA_LEFT),
        'li2': ParagraphStyle('li2', parent=base, leftIndent=2 * BULLET_INDENT, bulletIndent=BULLET_INDENT, bulletFontName='Serif', bulletFontSize=BODY_SIZE * s),
        'li2c': ParagraphStyle('li2c', parent=base, leftIndent=2 * BULLET_INDENT),
    }

def flowables(frame, L, T, scale, parts):
    st = styles(scale)
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
        para = Paragraph(esc(text), style, bulletText=('•' if k == 'li' else '–') if (k in ('li', 'li2') and first) else None)
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
        if f._kind in ('h2', 'h3', 'h4') and len(fl) > 1:
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
    out = []
    for f in info['frames']:
        x0, x1 = f['x0'], max(f['x1'], f['x0'] + 215)
        out.append(Frame(x0, H - f['bottom'] - slack, x1 - x0 + 0.5, f['bottom'] - f['top'] + slack + 2,
                         leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0))
    return out

def fit_text(c, text, font, size, x, y, maxw=None, align='left', color=black):
    if maxw:
        while pdfmetrics.stringWidth(text, font, size) > maxw and size > 4: size -= 0.1
    c.setFont(font, size); c.setFillColor(color)
    if align == 'right': c.drawRightString(x, y, text)
    else: c.drawString(x, y, text)

def draw_page(c, pn, L, T, parts):
    info = L['pages'][str(pn)]
    H = info['h']
    # running head: keep numbers, replace the text
    for r in info['runhead']:
        nums = [p for p in r['parts'] if re.fullmatch(r'\d+', p['t'])]
        txt = [p for p in r['parts'] if not re.fullmatch(r'\d+', p['t'])]
        y = H - baseline(r)
        for p in nums:
            fit_text(c, p['t'], 'Sans-B', r['size'], p['x0'], y)
        tr = T.get(f'p{pn}_rh', '')
        tr = re.sub(r'^[\d\s]+', '', tr) if nums and txt and nums[0]['x0'] < txt[0]['x0'] else tr
        if txt and tr.strip():
            italic = 'Italic' in txt[0]['font']
            font = 'Sans-I' if italic else 'Sans-B'
            if txt[0]['x0'] > info['w'] / 2 or (nums and nums[0]['x0'] > txt[-1]['x0']):
                xr = max(p['x0'] for p in txt) + (r['x1'] - r['x0']) * 0  # right edge of text part
                right = nums[0]['x0'] - 8 if nums else r['x1']
                fit_text(c, tr.strip(), font, r['size'], right, y, align='right')
            else:
                fit_text(c, tr.strip(), font, r['size'], txt[0]['x0'], y, maxw=r['x1'] - txt[0]['x0'])
    # chapter title
    if info['h1']:
        l1 = info['h1'][0]
        num = l1['parts'][0]
        c.setFillColor(RED)
        size = l1['size']
        x_text = l1['parts'][1]['x0'] if len(l1['parts']) > 1 else l1['x0']
        title = T[f'p{pn}_h1']
        maxw = 510.4 - x_text
        from reportlab.lib.utils import simpleSplit
        while True:
            lines = simpleSplit(title, 'Sans-B', size, maxw)
            if len(lines) <= len(info['h1']) or size < 11: break
            size -= 0.2
        fit_text(c, num['t'], 'Sans-B', size, num['x0'], H - baseline(l1), color=RED)
        step = (info['h1'][1]['bottom'] - l1['bottom']) if len(info['h1']) > 1 else size * 1.15
        for i, ln in enumerate(lines):
            fit_text(c, ln, 'Sans-B', size, x_text, H - baseline(l1) - i * step, color=RED)
    for a in info['author']:   # author names stay as in the source
        fit_text(c, a['text'], 'Sans-I', a['size'], a['x0'], H - baseline(a))
    # captions
    for cap in info['captions']:
        bold, rest = T[cap['id']]
        right = 280.8 if cap['x1'] < info['w'] / 2 else 510.4
        if right - cap['x1'] > 40: right = cap['x1'] + 2
        w = right - cap['x0']
        avail = (cap['bottom'] - cap['top']) * 1.25 + 6
        size = cap['size']
        while True:
            st = ParagraphStyle('c', fontName='Sans', fontSize=size, leading=size * 1.31, alignment=TA_LEFT)
            p = Paragraph(f'<b>{esc(bold)}</b> {esc(rest)}', st)
            _, h = p.wrap(w, 1000)
            if h <= avail or size < 5.5: break
            size -= 0.1
        p.drawOn(c, cap['x0'], H - cap['top'] - h + size * 0.25)
    # body
    frames = info['frames']
    def all_fit(scale, cv):
        ok = True
        for fr, fd in zip(make_frames(info), frames):
            ok &= fill([fr], flowables(fd, L, T, scale, parts), cv)
        return ok
    for scale in [x / 100 for x in range(116, 79, -2)]:
        if all_fit(scale, canvas.Canvas(io.BytesIO(), pagesize=(info['w'], H))):
            break
    else:
        print(f'page {pn}: text does not fit even at scale {scale}', file=sys.stderr)
    all_fit(scale, c)
    return scale

def main(pdf, layout, trf, out):
    L = json.load(open(layout)); T = json.load(open(trf))
    parts = {it['id']: split_share(T[it['id']], it['segs']) for it in L['items']}
    reader = PdfReader(pdf)
    writer = PdfWriter()
    report = {}
    for pn in sorted(int(p) for p in L['pages']):
        writer.add_page(reader.pages[pn - 1])
        page = writer.pages[-1]
        strip_text(writer, page)
        info = L['pages'][str(pn)]
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(info['w'], info['h']))
        report[pn] = draw_page(c, pn, L, T, parts)
        c.showPage(); c.save()
        page.merge_page(PdfReader(buf).pages[0])
    writer.write(out)
    print('font scale per page:', report)

if __name__ == '__main__':
    main(*sys.argv[1:])
