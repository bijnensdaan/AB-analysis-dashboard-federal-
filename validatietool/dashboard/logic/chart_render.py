"""Dezelfde standaardplot voor SVG in dashboard en PNG-export; geen browserdienst."""
from io import BytesIO
import math
import textwrap
import threading
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.patches import PathPatch,Rectangle
from matplotlib.path import Path
from matplotlib.ticker import FuncFormatter,MaxNLocator

from .analysis import actor_label
from .i18n import tr

LOCK=threading.Lock()
COLORS=['#22664e','#548c7b','#9cb784','#d4a55f','#7a83a7','#b57978','#7a9299','#9f8b72']


def short(value,width=44,lines=3):
    value=str(value or 'Niet opgeslagen');parts=textwrap.wrap(value,width=width) or ['']
    return '\n'.join(parts[:lines])+('…' if len(parts)>lines else '')


def number(value,language='nl'):return f'{value:,.0f}' if language=='en' else f'{value:,.0f}'.replace(',','.')


def _figure(chart):
    language=chart.get('ui_language','nl');T=lambda value:tr(value,language)
    fmt=lambda value:number(value,language)
    rows=chart['rows'];kind=chart['kind']
    height=max(4.2,.53*len(rows)+1.9) if kind=='bar' else 5.8
    if kind=='heatmap':height=max(4.8,.32*len({r['y'] for r in rows})+1.8)
    fig=Figure(figsize=(12,height),facecolor='white',layout='constrained');ax=fig.subplots()
    fig.suptitle(chart['title'],fontsize=15,fontweight='bold',color='#203b32',ha='left',x=.02)
    unit='Unieke registerbepalingen' if chart['unit']=='duties' else 'Unieke acts'
    footer=T(unit)+' · '+T('directe relaties, geen bewezen ketens' if kind=='flow' else 'binnen de geselecteerde bronversies')
    if chart['unit']=='duties' or chart['chart_id'] in ('act_relation','amended'):footer+=' · '+T('categorieën kunnen overlappen')
    if chart['unit']=='duties' and chart['chart_id'] not in ('flow','actors'):footer+=' · '+T('AB: opgeslagen n_ab_claims > 0')
    footer+='\nRegister: '+chart['sources']['register']['snapshot_utc']+' | Corpus: '+(chart['sources']['corpus'] or {}).get('snapshot_utc','niet beschikbaar')
    footer+='\n'+textwrap.fill(chart.get('filter_summary',''),width=140,max_lines=2,placeholder='…')
    if kind=='combo':footer+='\n'+T('Aandeel: gedetecteerde AB in classifiergeselecteerde acts (pred=1, zekerheid ≥0,75) / corpus; geen populatieschatting.')
    if chart.get('display'):
        footer+='\n'+textwrap.fill(chart['display']['description'],width=140)
    if chart.get('coverage'):
        footer+='\n'+textwrap.fill(chart['coverage']['description'],width=140)
    fig.supxlabel(footer,fontsize=7.8,color='#607269')
    ax.spines[['top','right']].set_visible(False)
    ax.tick_params(labelsize=9,colors='#465f53')
    for spine in ax.spines.values():spine.set_color('#dce6df')
    if not chart['available'] or not rows:
        ax.axis('off');ax.text(.5,.5,T('Geen betrouwbare corpusnoemer voor deze selectie.' if not chart['available'] else 'Geen gegevens binnen deze selectie.'),ha='center',va='center',fontsize=12,color='#607269',transform=ax.transAxes)
        return fig
    if kind in ('bar','funnel'):
        labels=[short(r['label'],48,3) for r in rows];values=[r['value'] for r in rows]
        bars=ax.barh(range(len(rows)),values,color=COLORS[0],height=.64,left=[(max(values)-v)/2 for v in values] if kind=='funnel' else 0)
        ax.set_yticks(range(len(rows)),labels);ax.invert_yaxis();ax.set_axisbelow(True);ax.grid(axis='x',color='#edf1ed')
        for bar,row in zip(bars,rows):
            bar.set_gid('point-'+row['point_id']);x=bar.get_x()+bar.get_width()
            ax.annotate(fmt(row['value']),(x,bar.get_y()+bar.get_height()/2),xytext=(6,0),textcoords='offset points',va='center',fontsize=10,color='#203b32')
        ax.set_xlim(0,max(values+[1])*1.18);ax.xaxis.set_major_formatter(FuncFormatter(lambda x,p:fmt(x)));ax.xaxis.set_major_locator(MaxNLocator(integer=True,nbins=6))
    elif kind=='heatmap':
        xs=sorted({r['x'] for r in rows});ys=sorted({r['y'] for r in rows});lookup={(r['x'],r['y']):r for r in rows};maximum=max(r['value'] for r in rows) or 1
        for i,y in enumerate(ys):
            for j,x in enumerate(xs):
                row=lookup.get((x,y));value=row['value'] if row else 0
                patch=Rectangle((j-.5,i-.5),1,1,facecolor=matplotlib.colormaps['YlGn'](.08+.83*value/maximum),edgecolor='white',linewidth=1)
                if row:patch.set_gid('point-'+row['point_id'])
                ax.add_patch(patch)
                if len(xs)<=32:ax.text(j,i,fmt(value),ha='center',va='center',fontsize=7.5,color='white' if value/maximum>.65 else '#244d38')
        ax.set_xlim(-.5,len(xs)-.5);ax.set_ylim(len(ys)-.5,-.5);ax.set_xticks(range(len(xs)),[short(T({'federal':'Federaal','region':'Gewest','regional':'Regionaal','commission':'Gemeenschapscommissie','community':'Gemeenschap','unknown':'Onbekend'}.get(x,x)) if chart['chart_id']=='level_io' else x,18,2) for x in xs],rotation=45,ha='right');ax.set_yticks(range(len(ys)),[short(y,30,2) for y in ys]);ax.spines[:].set_visible(False)
    elif kind in ('combo','stack'):
        xs=sorted({r['x'] for r in rows});positions={x:int(x) if str(x).isdigit() and all(str(y).isdigit() for y in xs) else i for i,x in enumerate(xs)}
        if kind=='combo':
            bars=[r for r in rows if r['y']=='register'];patches=ax.bar([positions[r['x']] for r in bars],[r['value'] for r in bars],color='#9cbda9',label=T('Alle AB-registeracts'),width=.75)
            for patch,row in zip(patches,bars):patch.set_gid('point-'+row['point_id'])
            shares=[r for r in rows if r['y']=='classifier' and r.get('share') is not None]
            if shares:
                right=ax.twinx();right.spines['top'].set_visible(False);right.set_ylabel(T('Gedetecteerd aandeel van corpus'),fontsize=9,color='#22664e')
                right.plot([positions[r['x']] for r in shares],[100*r['share'] for r in shares],color='#22664e',linewidth=2,label='Classifier-AB / corpus')
                for row in shares:
                    marker,=right.plot(positions[row['x']],100*row['share'],marker='o',markersize=5,color='#22664e');marker.set_gid('point-'+row['point_id'])
                right.yaxis.set_major_formatter(FuncFormatter(lambda x,p:f'{x:g}%'));right.tick_params(labelsize=9,colors='#22664e');right.set_ylim(bottom=0)
            fig.legend(loc='upper left',bbox_to_anchor=(.08,.94),frameon=False,fontsize=8)
        else:
            series=sorted({r['y'] for r in rows});lookup={(r['x'],r['y']):r for r in rows};base=[0]*len(xs)
            for index,series_name in enumerate(series):
                vals=[lookup.get((x,series_name),{}).get('value',0) for x in xs]
                ax.fill_between([positions[x] for x in xs],base,[a+b for a,b in zip(base,vals)],color=COLORS[index%len(COLORS)],alpha=.3,label=T({'business':'Onderneming','citizen':'Burger','both':'Onderneming en burger'}.get(series_name,series_name)))
                top=[a+b for a,b in zip(base,vals)];ax.plot([positions[x] for x in xs],top,color=COLORS[index%len(COLORS)],linewidth=1.6)
                for i,x in enumerate(xs):
                    row=lookup.get((x,series_name))
                    if row:
                        marker,=ax.plot(positions[x],top[i],marker='o',markersize=4,color=COLORS[index%len(COLORS)]);marker.set_gid('point-'+row['point_id'])
                base=top
            ax.legend(frameon=False,fontsize=9,loc='upper left')
        ax.set_xticks([positions[x] for x in xs],xs,rotation=45,ha='right');ax.set_ylim(bottom=0);ax.set_ylabel(T('AB-acts'),fontsize=9);ax.yaxis.set_major_formatter(FuncFormatter(lambda x,p:fmt(x)));ax.set_axisbelow(True);ax.grid(axis='y',color='#edf1ed')
    elif kind=='flow':
        # Twee gescheiden rollen: een gelijknamige knoop links/rechts is geen ketenkoppeling.
        left={};right={}
        for r in rows:left[r['x']]=left.get(r['x'],0)+r['value'];right[r['y']]=right.get(r['y'],0)+r['value']
        total=sum(r['value'] for r in rows) or 1;gap=.055;scale=(.85-gap*(max(len(left),len(right))-1))/total
        def layout(values):
            result={};y=.95
            for key,count in sorted(values.items(),key=lambda p:(-p[1],p[0])):
                height=count*scale;result[key]=[y-height,y];y-=height+gap
            return result
        lpos=layout(left);rpos=layout(right);lc={k:v[0] for k,v in lpos.items()};rc={k:v[0] for k,v in rpos.items()}
        palette={key:COLORS[i%len(COLORS)] for i,key in enumerate(lpos)}
        for row in rows:
            a,b=row['x'],row['y'];h=row['value']*scale;la,rb=lc[a],rc[b]
            verts=[(.26,la),(.45,la),(.55,rb),(.74,rb),(.74,rb+h),(.55,rb+h),(.45,la+h),(.26,la+h),(.26,la)]
            codes=[Path.MOVETO,Path.CURVE4,Path.CURVE4,Path.CURVE4,Path.LINETO,Path.CURVE4,Path.CURVE4,Path.CURVE4,Path.CLOSEPOLY]
            patch=PathPatch(Path(verts,codes),facecolor=palette[a],alpha=.4,edgecolor='none');patch.set_gid('point-'+row['point_id']);ax.add_patch(patch);lc[a]+=h;rc[b]+=h
        for x,values,positions,align,labelx in [(.24,left,lpos,'right',.23),(.74,right,rpos,'left',.77)]:
            for key,(lo,hi) in positions.items():
                ax.add_patch(Rectangle((x,lo),.02,hi-lo,color='#466f59',linewidth=0))
                ax.text(labelx,(lo+hi)/2,short(T(actor_label(key)),25,2),ha=align,va='center',fontsize=9,color='#203b32')
        ax.text(.24,1.025,T('Drager'),ha='right',fontsize=10,fontweight='bold');ax.text(.76,1.025,T('Ontvanger'),ha='left',fontsize=10,fontweight='bold');ax.set_xlim(0,1);ax.set_ylim(0,1.08);ax.axis('off')
    return fig


def render(chart,format='svg'):
    if format not in ('svg','png'):raise ValueError('Onbekend grafiekformaat.')
    language=chart.get('ui_language','nl');T=lambda value:tr(value,language)
    with LOCK,matplotlib.rc_context({'svg.fonttype':'none','font.family':'DejaVu Sans','text.parse_math':False}):
        fig=_figure(chart);buffer=BytesIO();fig.savefig(buffer,format=format,dpi=150,metadata={'Description':chart['title']} if format=='png' else None);fig.clear();body=buffer.getvalue()
    if format=='png':return body
    ET.register_namespace('','http://www.w3.org/2000/svg');ET.register_namespace('xlink','http://www.w3.org/1999/xlink')
    root=ET.fromstring(body);namespace='{http://www.w3.org/2000/svg}';lookup={'point-'+r['point_id']:r for r in chart['rows']}
    for parent in root.iter():
        for child in list(parent):
            if child.tag==namespace+'style':parent.remove(child)
    # SVG-presentatieattributen werken ook met de strikte CSP, zonder inline CSS.
    for element in root.iter():
        # Matplotlib tekent celwaarden als losse tekst boven de klikbare rechthoek.
        # Laat een klik op het getal door naar die cel gaan; de aria-naam blijft.
        if element.tag==namespace+'text':element.set('pointer-events','none')
        for property in element.attrib.pop('style','').split(';'):
            if ':' in property:
                name,value=property.split(':',1);element.set(name.strip(),value.strip())
        if 'font-family' in element.attrib:element.set('font-family','DejaVu Sans, Segoe UI, Arial, sans-serif')
        row=lookup.get(element.get('id'))
        if row:
            label=row['label']+': '+number(row['value'],language)+' '+(T('bepalingen') if chart['unit']=='duties' else 'acts')
            if row.get('share') is not None:label+=f"; {row['numerator']} / {row['denominator']} = {100*row['share']:.2f}%"
            if row['value']!=row['register_acts'] and chart['unit']=='acts':label+='; '+T('gekoppelde registeracts')+': '+number(row['register_acts'],language)
            title=ET.SubElement(element,namespace+'title');title.text=label
            element.set('aria-label',label)
            if row['drillable']:element.set('data-point',row['point_id']);element.set('tabindex','0');element.set('role','button')
    root.set('role','img');root.set('aria-label',chart['title']);root.set('stroke-linejoin','round');root.set('stroke-linecap','butt')
    return ET.tostring(root,encoding='unicode')
