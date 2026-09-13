from pathlib import Path
from html import escape
import re, shutil, json
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted, KeepTogether
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pdf/fly-connectomes-and-crypto-liquidity.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
ARCHIVE=ROOT/'output/pdf/archive/fly-connectomes-research-v1.pdf'
if OUT.exists() and not ARCHIVE.exists():
    ARCHIVE.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OUT,ARCHIVE)
FONT=Path('/Users/welly/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/Resources/fonts/truetype')
for name,file in [('D','DejaVuSans.ttf'),('DB','DejaVuSans-Bold.ttf'),('DM','DejaVuSansMono.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONT/file)))
pdfmetrics.registerFontFamily('D',normal='D',bold='DB',italic='D',boldItalic='DB')
INK=colors.HexColor('#132A35');TEAL=colors.HexColor('#097C80');GRAY=colors.HexColor('#52646D');LINE=colors.HexColor('#D9E2E6')
S={
'body':ParagraphStyle('body',fontName='D',fontSize=9.2,leading=13.4,spaceAfter=6,textColor=INK),
'h1':ParagraphStyle('h1',fontName='DB',fontSize=23,leading=28,spaceAfter=15,textColor=INK,keepWithNext=True),
'h2':ParagraphStyle('h2',fontName='DB',fontSize=13.5,leading=18,spaceBefore=13,spaceAfter=7,textColor=TEAL,keepWithNext=True),
'h3':ParagraphStyle('h3',fontName='DB',fontSize=10.5,leading=14,spaceBefore=9,spaceAfter=5,textColor=INK,keepWithNext=True),
'cell':ParagraphStyle('cell',fontName='D',fontSize=8.2,leading=11.4,textColor=INK),
'bullet':ParagraphStyle('bullet',fontName='D',fontSize=9.2,leading=13.4,spaceAfter=5,leftIndent=13,firstLineIndent=-10,textColor=INK),
'note':ParagraphStyle('note',fontName='D',fontSize=8.4,leading=12,spaceAfter=8,textColor=GRAY,backColor=colors.HexColor('#EFF5F6'),borderPadding=7),
'meta':ParagraphStyle('meta',fontName='D',fontSize=7.6,leading=10.5,spaceAfter=4,textColor=GRAY,keepWithNext=True),
'code':ParagraphStyle('code',fontName='DM',fontSize=7.5,leading=10.3,spaceAfter=9,textColor=INK),
'kicker':ParagraphStyle('kicker',fontName='DB',fontSize=10,leading=15,spaceAfter=14,textColor=TEAL),
'cover':ParagraphStyle('cover',fontName='DB',fontSize=38,leading=44,spaceAfter=18,textColor=INK),
'deck':ParagraphStyle('deck',fontName='D',fontSize=16,leading=23,spaceAfter=20,textColor=INK),
}
PARTS=[
('direction','Current direction and tools',ROOT/'docs/project-direction.md'),
('training','Training and hybrid intelligence',ROOT/'docs/training-design.md'),
('roadmap','Release roadmap and architecture',ROOT/'docs/build-roadmap.md'),
('tasks','Complete build task catalogue',ROOT/'docs/build-tasks.md'),
('experiment','Scientific evaluation design',ROOT/'docs/experiment-plan.md'),
('literature','Historical literature review',ROOT/'output/fly-connectomes-research.md')]
PATH_ANCHORS={str(p.resolve()):a for a,_,p in PARTS}
PATH_ANCHORS[str((ROOT/'docs/build-tasks.json').resolve())]='tasks'

class Report(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path),pagesize=(595.28,841.89),leftMargin=46,rightMargin=46,topMargin=51,bottomMargin=51,title='Willfly - Research, Architecture and Build Roadmap',author='Willfly research project',subject='Robinhood launches, neural learning, trading and selective LP; 77-task implementation roadmap')
        self.addPageTemplates(PageTemplate(id='main',frames=[Frame(46,51,503.28,739.89,id='body',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.paint))
        self.active_section='WILLFLY'
    def beforeDocument(self): self.active_section='WILLFLY'
    def paint(self,c,doc):
        c.saveState()
        if doc.page>1:
            c.setFillColor(GRAY); c.setFont('D',7.4)
            c.drawString(46,817,'WILLFLY / RESEARCH AND BUILD PLAN')
            c.drawRightString(549,817,'13 SEPTEMBER 2026 / v2')
            c.setStrokeColor(LINE);c.line(46,807,549,807)
        c.setStrokeColor(LINE);c.line(46,39,549,39)
        c.setFont('D',7);c.setFillColor(GRAY)
        c.drawString(46,26,'PLANNED WORK - NO VALIDATED TRADING PERFORMANCE')
        c.drawRightString(549,26,str(doc.page))
        c.restoreState()
    def afterFlowable(self,f):
        if hasattr(f,'bookmark'):
            self.canv.bookmarkPage(f.bookmark)
            self.canv.addOutlineEntry(f.getPlainText(),f.bookmark,f.level,False)
            self.notify('TOCEntry',(f.level,f.getPlainText(),self.page,f.bookmark))

story=[]
def norm(t):
    for a,b in {'—':' - ','–':'-','‑':'-','“':'"','”':'"','’':"'",'→':'->','≤':'<=','≥':'>='}.items(): t=t.replace(a,b)
    return t

def fmt(t,base):
    t=norm(t)
    saved=[]
    def link(m):
        label,url=m.groups()
        if url.startswith(('https://','http://')):
            rendered=f'<link href="{escape(url,quote=True)}" color="#097C80">{escape(label)}</link>'
        else:
            dest=PATH_ANCHORS.get(str((base.parent/url).resolve()))
            rendered=f'<link href="#{dest}" color="#097C80">{escape(label)}</link>' if dest else escape(label)
        saved.append(rendered);return f'ZZLINK{len(saved)-1}ZZ'
    t=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,t)
    t=escape(t)
    t=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',t)
    t=re.sub(r'`([^`]+)`',r'<font name="DM" size="8">\1</font>',t)
    if base.name=='fly-connectomes-research.md':
        t=re.sub(r'\[([0-9,]+)\]',lambda m:'<super>'+','.join(f'<link href="#ref{n}">{n}</link>' for n in m.group(1).split(','))+'</super>',t)
    for i,s in enumerate(saved): t=t.replace(f'ZZLINK{i}ZZ',s)
    return t

def p(text,kind='body',base=ROOT/'README.md'):
    para=Paragraph(fmt(text,base),S[kind]);story.append(para);return para

def heading(text,kind='h2',bookmark=None,level=1):
    para=p(text,kind)
    if bookmark: para.bookmark=bookmark;para.level=level
    return para

def make_table(lines,base):
    rows=[[x.strip() for x in l.strip().strip('|').split('|')] for l in lines]
    rows=[r for r in rows if not all(re.fullmatch(r':?-+:?',v.replace(' ','')) for v in r)]
    n=len(rows[0]);rows=[r+['']*(n-len(r)) for r in rows]
    widths={2:[145,358.28],3:[112,194,197.28],4:[91,142,140,130.28]}.get(n,[503.28/n]*n)
    # Phase overview gives most space to gate description.
    if rows[0][0]=='Phase': widths=[111,298.28,94]
    if rows[0][0]=='Record': widths=[103,400.28]
    rendered=[[Paragraph(('<b>'+fmt(v,base)+'</b>') if i==0 else fmt(v,base),S['cell']) for v in r] for i,r in enumerate(rows)]
    tab=Table(rendered,colWidths=widths,repeatRows=1,hAlign='LEFT')
    tab.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8F1F3')),('LINEBELOW',(0,0),(-1,0),.7,TEAL),('LINEBELOW',(0,1),(-1,-1),.35,LINE),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.extend([tab,Spacer(1,7)])

def markdown(path,anchor):
    lines=path.read_text().splitlines();i=0;first=True;sub=0;in_sources=False
    while i<len(lines):
        line=lines[i].strip()
        if not line: i+=1;continue
        if line.startswith('# ') and first:
            first=False;i+=1;continue
        first=False
        if line.startswith('```'):
            code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                code.append(norm(lines[i]));i+=1
            story.append(Preformatted('\n'.join(code),S['code']));i+=1;continue
        if line.startswith('|'):
            table=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                table.append(lines[i]);i+=1
            make_table(table,path);continue
        m=re.match(r'^(#{1,3}) (.+)$',line)
        if m:
            depth=len(m[1]);title=m[2];sub+=1
            if anchor=='tasks' and depth==2:
                story.append(PageBreak())
                heading(title,'h2',f'{anchor}-{sub}',1)
            elif anchor=='literature' and depth==1:
                story.append(PageBreak());heading(title,'h2',f'{anchor}-{sub}',1)
                in_sources=title.startswith('Sources')
            else:
                heading(title,'h2' if depth<=2 else 'h3',None,1)
            i+=1;continue
        block=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#{1,3} |\||```|[-*] |\d+\. )',lines[i].strip()):
            block.append(lines[i].strip());i+=1
        text=' '.join(block)
        if text.startswith('> '): p(text[2:],'note',path)
        elif text.startswith('**Status:**') or text.startswith('**Target paths:**'): p(text,'meta',path)
        elif re.match(r'^[-*] ',text): p('- '+text[2:],'bullet',path)
        elif in_sources:
            m=re.match(r'^(\d+)\. ',text)
            par=Paragraph((f'<a name="ref{m[1]}"/>' if m else '')+fmt(text,path),S['body'])
            story.append(par)
        else: p(text,'body',path)

p('RESEARCH / ARCHITECTURE / IMPLEMENTATION','kicker')
story.append(Spacer(1,34))
p('Willfly','cover')
p('A neural decision system for new crypto markets','deck')
p('Robinhood Chain first. New launches and spot trading, with selective liquidity provision.','deck')
story.append(Spacer(1,15))
p('VERSION 2 / 13 SEPTEMBER 2026','kicker')
p('**Build first: Observatory v0.1.** Capture launch and pool events, preserve their history, recover missing data, and inspect what was knowable at each moment. Establish replay and ordinary strategy baselines before evaluating fly-derived neural learning.')
p('**This edition:** current project direction, training methods, release roadmap, architecture and **77 build tasks** with dependencies and acceptance checks. The original 40-source literature review is retained as a historical appendix.')
p('**Evidence boundary:** a connectome-derived model can be trained. Its advantage for crypto decisions is unproven. All application tasks are planned; no live integration, model, backtest or funded execution has been validated.','note')
story.append(Spacer(1,20))
p('Prepared from the maintained project documents. Estimates and numerical thresholds are proposed engineering choices; provider behavior and exact launch deployments must be validated during Phase 0.','meta')
story.append(PageBreak())
heading('Contents','h1')
toc=TableOfContents();toc.levelStyles=[ParagraphStyle('toc0',fontName='DB',fontSize=10.5,leading=15,spaceBefore=10,textColor=INK),ParagraphStyle('toc1',fontName='D',fontSize=8.5,leading=12,leftIndent=13,textColor=GRAY)]
story.append(toc)
for anchor,title,path in PARTS:
    story.append(PageBreak());heading(title,'h1',anchor,0)
    if anchor=='tasks':
        p('64 research-build tasks and 13 conditional follow-on tasks. Each task states what to implement, its dependencies, proposed files and the evidence required for completion. All tasks are currently unimplemented.','note')
        catalogue=json.loads((ROOT/'docs/build-tasks.json').read_text())
        for phase in catalogue['phases']:
            first_task=True
            for task in catalogue['tasks']:
                if task['phase']!=phase['id']: continue
                start=len(story)
                if first_task:
                    heading(phase['id']+' - '+phase['title'],'h2','tasks-'+phase['id'],1)
                    first_task=False
                p(task['id']+' - '+task['title'],'h3')
                p('**Status:** '+task['status']+' | **Owner role:** '+task['owner_role']+' | **Depends on:** '+(', '.join(task['depends_on']) or 'None'),'meta')
                p('**Target paths:** '+', '.join('`'+x+'`' for x in task['target_paths']),'meta')
                p(task['work'])
                p('**Done when:** '+task['acceptance'])
                story[start:]=[KeepTogether(story[start:])]
        continue
    if anchor=='literature':
        p('HISTORICAL APPENDIX','kicker')
        p('This is the foundational review from the earlier LP-first research stage. Its scientific evidence and access notes are preserved. Its original recommendation to start with LP range selection has been superseded by the Observatory and launch-trading roadmap in the preceding sections.','note')
    markdown(path,anchor)
doc=Report(OUT);doc.multiBuild(story)
print(OUT)
