"""Dump/draw text overlays for tables & diagrams.
dump: python3 overlay.py dump book.pdf PAGE x0 top x1 bottom
draw: python3 overlay.py draw in.pdf out.pdf spec.json  (spec: {"<outpage_index>": [{"x":..,"y_top":..,"size":..,"bold":bool,"text":..,"maxw":..,"align":"left|center","color":[c,m,y,k]}]})
"""
import sys,json
def dump(pdf,pn,x0,top,x1,bot):
    import pdfplumber
    p=pdfplumber.open(pdf).pages[pn-1]
    ws=[w for w in p.extract_words(extra_attrs=['fontname','size','non_stroking_color'],keep_blank_chars=False,x_tolerance=1.5) if x0<=w['x0']<=x1 and top<=w['top']<=bot]
    ws.sort(key=lambda w:(round(w['top']),w['x0']))
    lines=[]
    for w in ws:
        if lines and abs(lines[-1]['top']-w['top'])<2 and w['x0']-lines[-1]['x1']<5:
            l=lines[-1]; l['text']+=' '+w['text']; l['x1']=w['x1']
        else: lines.append(dict(x0=round(w['x0'],1),x1=w['x1'],top=round(w['top'],1),size=round(w['size'],1),font=w['fontname'].split('+')[-1],col=w['non_stroking_color'],text=w['text']))
    for l in lines: l['x1']=round(l['x1'],1); print(json.dumps(l,ensure_ascii=False))
def draw(inp,out,specf):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import CMYKColor,black
    from pypdf import PdfReader,PdfWriter
    import io
    pdfmetrics.registerFont(TTFont('Sans','/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('Sans-B','/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf'))
    spec=json.load(open(specf)); r=PdfReader(inp); w=PdfWriter()
    for i,pg in enumerate(r.pages):
        items=spec.get(str(i))
        if items:
            W=float(pg.mediabox.width); H=float(pg.mediabox.height)
            buf=io.BytesIO(); c=canvas.Canvas(buf,pagesize=(W,H))
            for it in items:
                f='Sans-B' if it.get('bold') else 'Sans'; s=it['size']
                tw=pdfmetrics.stringWidth(it['text'],f,s); mw=it.get('maxw',1e9)
                sc=min(1,mw/tw) if tw else 1
                col=it.get('color'); c.setFillColor(CMYKColor(*col) if col and len(col)==4 else black)
                c.saveState(); y=H-it['y_top']-0.8*s
                x=it['x']-(tw*sc/2 if it.get('align')=='center' else 0)
                c.translate(x,y); c.scale(sc,1); c.setFont(f,s); c.drawString(0,0,it['text']); c.restoreState()
            c.save(); buf.seek(0); pg.merge_page(PdfReader(buf).pages[0])
        w.add_page(pg)
    w.write(out)
if sys.argv[1]=='dump': dump(sys.argv[2],int(sys.argv[3]),*map(float,sys.argv[4:8]))
else: draw(*sys.argv[2:5])
