"""Zelfstandige Markdown/PDF-export; geen nieuwe classificaties of bronwijzigingen."""
from html import escape
from io import BytesIO
import json
from pathlib import Path
import threading
from .i18n import tr

_FONT_LOCK=threading.Lock()


def blocks(detail,text=None):
    """Dezelfde volledige bewijsinhoud voor beide formaten; exports zijn niet gefilterd."""
    yield 'title','Act '+str(detail['act']['numac'])
    yield 'sourcebody',detail['act'].get('title') or 'Titel ontbreekt'
    yield 'body','Registersnapshot: '+detail['source']['snapshot_utc']+' | Run: '+str(detail['run_id'])
    yield 'body','Bestaande registeruitkomsten. Claim-, duty- en actoordelen blijven afzonderlijk; er wordt niets gecorrigeerd.'
    yield 'heading','Verdict en verklaring'
    yield 'body',detail['explanation']['summary']
    yield 'reason',detail['verdict'].get('reason')
    for note in detail['explanation']['notes']:yield 'body',note
    for title,value in [('Identificatie',detail['act']),('Oorspronkelijk actverdict',detail['verdict']),
                        ('Run en modellen',detail['run']),('Wat de act doet',detail['amended_acts'])]:
        yield 'heading',title;yield 'data',value
    yield 'heading','Overheidsorgaan en beleidsrubriek'
    yield 'authority',(detail.get('orgaan','Onbekend'),detail.get('beleidsdomein','Onbekend'))
    if detail.get('authority_mapping'):
        yield 'body','Afzonderlijke bronkoppeling; beleidsrubriek uit een expliciete diensthoofding of voordragende ministerportefeuille, geen inhoudelijke classificatie van deze act.'
        yield 'data',detail['authority_mapping']
    for duty in detail['duties']:
        label='AB-bepaling' if duty.get('n_ab_claims') is not None and duty['n_ab_claims']>0 else 'Overige registerbepaling'
        yield 'heading',label+' '+str(duty['duty_id'])
        yield 'quote',duty.get('canonical_quote') or 'Canoniek citaat ontbreekt'
        yield 'data',{k:v for k,v in duty.items() if k not in ('claims','reviews')}
        for claim in duty['claims']:
            yield 'subheading','Lezersclaim '+str(claim['obligation_id'])+' - '+str(claim['reader'].get('model') or 'model onbekend')
            yield 'data',claim
        if duty['reviews']:
            yield 'subheading','Gekoppelde judge-beslissingen (koppelmethode vermeld)';yield 'data',duty['reviews']
    if detail['loose_claims']:
        yield 'heading','Losse claims zonder duty-koppeling'
        for claim in detail['loose_claims']:
            yield 'subheading','Claim '+str(claim['obligation_id']);yield 'data',claim
    yield 'heading','Alle reviews van deze act, inclusief historie en ambigue koppelingen'
    yield 'data',detail['reviews']
    yield 'heading','Lezingen en kwaliteit'
    yield 'data',{'text_metadata':detail['text_metadata'],'readings':detail['readings']}
    yield 'heading','Volledige opgeslagen ruwe tekst'
    if text and text.get('available'):
        yield 'body','Inhoud geverifieerd tegen de tekstmetadata van de snapshot. Bron: '+text['provenance']['origin']
        yield 'text',text['content']
        yield 'body','Niet teruggevonden markeerdoelen: '+str(len(text['unmatched']))+'. Citaatmatching tolereert alleen witruimte.'
    else:
        yield 'body',text.get('message','Tekst niet geladen.') if text else 'Tekst niet geladen.'


def markdown_export(detail,text=None,ui_language='nl'):
    """Bronvelden als JSON-fences behouden ook ontbrekende waarden en originele tekst."""
    out=[]
    for kind,value in blocks(detail,text):
        if kind=='authority':kind,value='sourcebody',tr('Herkend overheidsorgaan',ui_language)+': '+str(value[0])+' | '+tr('Beleidsrubriek',ui_language)+': '+tr(value[1],ui_language)
        elif kind=='reason':kind,value='sourcebody',tr('Opgeslagen motivering',ui_language)+': '+str(value or tr('Niet opgeslagen',ui_language))
        elif kind in ('title','heading','subheading','body'):value=tr(value,ui_language)
        if kind in ('title','heading','subheading'):
            heading={'title':'# ','heading':'## ','subheading':'### '}[kind]
            out.append(heading+escape(str(value)))
        elif kind in ('body','sourcebody'):out.append(escape(str(value)))
        else:
            body=json.dumps(value,ensure_ascii=False,indent=2) if kind=='data' else str(value)
            # Een broncitaat met backticks mag de code-fence niet sluiten.
            import re
            fence='`'*max(3,1+max((len(s) for s in re.findall(r'`+',body)),default=0))
            out.append(fence+('json' if kind=='data' else 'text')+'\n'+body+'\n'+fence)
    return ('\n\n'.join(out)+'\n').encode('utf-8')


def pdf_export(detail,text=None,ui_language='nl'):
    """A4 met Unicode-lettertype, afbreekbare tekst en paginanummers."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    with _FONT_LOCK:
        if 'ABText' not in pdfmetrics.getRegisteredFontNames():
            font=next((p for p in [Path('C:/Windows/Fonts/segoeui.ttf'),
                Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.exists()),None)
            if font is None:raise ValueError('Unicode-lettertype voor PDF ontbreekt; gebruik de Markdown-export.')
            pdfmetrics.registerFont(TTFont('ABText',str(font)))
    base=dict(fontName='ABText',fontSize=9,leading=13,textColor=colors.HexColor('#243e32'),
              alignment=TA_LEFT,splitLongWords=1,spaceAfter=7)
    styles={kind:ParagraphStyle(kind,**dict(base,**extra)) for kind,extra in {
        'title':dict(fontSize=19,leading=24,spaceAfter=12),
        'heading':dict(fontSize=12,leading=17,spaceBefore=11,keepWithNext=True),
        'subheading':dict(fontSize=10,leading=14,spaceBefore=8,keepWithNext=True),
        'body':{},'data':dict(fontSize=7.8,leading=11,textColor=colors.HexColor('#536559')),
        'quote':dict(leftIndent=9,borderColor=colors.HexColor('#bfd7c6'),borderWidth=.5,borderPadding=7),
        'text':dict(fontSize=8.3,leading=12)}.items()}
    story=[]
    for kind,value in blocks(detail,text):
        if kind=='authority':kind,value='sourcebody',tr('Herkend overheidsorgaan',ui_language)+': '+str(value[0])+' | '+tr('Beleidsrubriek',ui_language)+': '+tr(value[1],ui_language)
        elif kind=='reason':kind,value='sourcebody',tr('Opgeslagen motivering',ui_language)+': '+str(value or tr('Niet opgeslagen',ui_language))
        elif kind in ('title','heading','subheading','body'):value=tr(value,ui_language)
        if kind=='sourcebody':kind='body'
        body=json.dumps(value,ensure_ascii=False,indent=2) if kind=='data' else str(value)
        # Kleine blokken kunnen over paginagrenzen worden gesplitst, ook bij lange citaten/JSON.
        for start in range(0,max(1,len(body)),1200):
            part=escape(body[start:start+1200]).replace('\n','<br/>')
            story.append(Paragraph(part or ' ',styles[kind]))
        if kind=='data':story.append(Spacer(1,3*mm))
    buffer=BytesIO()
    document=SimpleDocTemplate(buffer,pagesize=A4,leftMargin=19*mm,rightMargin=19*mm,
        topMargin=20*mm,bottomMargin=19*mm,title='Act '+str(detail['act']['numac']),author='AB-dashboard')
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('ABText',8);canvas.setFillColor(colors.HexColor('#687d6e'))
        canvas.drawString(19*mm,11*mm,'AB-dashboard | '+str(detail['act']['numac'])+' | run '+str(detail['run_id']))
        canvas.drawRightString(A4[0]-19*mm,11*mm,tr('Pagina',ui_language)+' '+str(doc.page));canvas.restoreState()
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()
