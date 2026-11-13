import json,re,sys,pdfplumber
lay,trf,pdf=sys.argv[1:4]
t=json.load(open(trf)); L=json.load(open(lay))
norm=lambda s: re.sub(r'[^\w]','',re.sub(r'<[^>]+>|\*\*','',s)).replace('_','')
parts=[]
for p in pdfplumber.open(pdf).pages:
    W=p.width
    for x0,x1 in [(0,W/2),(W/2,W)]:
        parts.append(p.crop((x0,0,x1,p.height)).extract_text() or '')
txt=norm(''.join(parts).replace('-\n','').replace('­',''))
ids={it['id'] for it in L['items']}
miss=[k for k in sorted(ids) if k in t and norm(t[k])[-18:] not in txt]
print('missing tails:',miss)
