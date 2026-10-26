"""Grafiekcijfers, broncitaten en exports uit dezelfde read-only selectie."""
from copy import deepcopy
from collections import Counter
import csv
from dataclasses import replace
from functools import lru_cache
import io
import json
from pathlib import Path

from .actlist import selection_sql
from .cache import CacheError
from ..logic.analysis import CHARTS,CLAIM_CHARTS,point_id,actor_label,matching_steps,with_point
from ..logic.act_filters import ActFilters

QUERY=(Path(__file__).with_name('analysis_sql')/'chart_rows.sql').read_text(encoding='utf-8')
EXAMPLES=(Path(__file__).with_name('analysis_sql')/'municipal_examples.sql').read_text(encoding='utf-8')
OVERLAP='Eén registerbepaling kan door lezersverschillen in meerdere categorieën staan. Per categorie telt zij eenmaal; categorietotalen zijn niet optelbaar.'
# Vrije actornamen, datavelden en verwijzingen kunnen tienduizenden waarden hebben.
LARGE_CHARTS={'actors','data_items','eu_instruments','amended'}


def chart_options(chart):
    limited=CHARTS[chart][1] in ('bar','flow','heatmap')
    return {'default_top':10 if chart in LARGE_CHARTS else 0,
            'allow_all':chart not in LARGE_CHARTS,'limit_control':limited}


class ChartRepository:
    def __init__(self,store,overview,detail=None):self.store=store;self.overview=overview;self.detail=detail

    def get(self,chart,filters=None,top=None):
        if chart not in CHARTS:raise ValueError('Onbekende grafiek.')
        if top is None:top=chart_options(chart)['default_top']
        if type(top) is not int or not 0<=top<=50:raise ValueError('Top-N moet tussen 1 en 50 liggen; 0 betekent alle categorieën.')
        if not self.store.analysis_projection:raise CacheError('Grafiekcache ontbreekt. Voer bouw_grafiekcache.py uit en herstart het dashboard.')
        f=filters or ActFilters();self.store.chart_point(f)
        if f.run_id is not None and f.run_id not in self.store.run_ids:raise ValueError('Onbekende run.')
        f=replace(f,page=1,size=25,sort='pub_date',direction='desc',q=f.q.strip(),q_in=f.q_in if f.q.strip() else 'all')
        # Een volledige vrije-waardenexport kan >100.000 rijen bevatten. Bewaar
        # die eenmalige download niet in de LRU voor interactieve grafieken.
        if top==0 and chart in LARGE_CHARTS:return self._cached.__wrapped__(self,chart,f,top)
        return deepcopy(self._cached(chart,f,top))

    @lru_cache(maxsize=96)
    def _cached(self,chart,filters,top):
        title,kind,unit,group=CHARTS[chart];cte,params=selection_sql(filters,bool(self.store.authority_mapping),True)
        coverage=None
        with self.store.connect() as db:
            rows=[dict(r) for r in db.execute(cte+QUERY,params+[chart])]
            for r in rows:r['value']=r[unit if unit=='duties' else 'register_acts'];r['drillable']=r['register_acts']>0
            if chart in ('flow','flow_ab'):
                for r in rows:r['label']=actor_label(r['x'])+' → '+actor_label(r['y'])
            if chart=='io':
                names={r['io_id']:r['name_short'] for r in db.execute('SELECT * FROM io_types')}
                for r in rows:r['label']=r['x']+' · '+names.get(r['x'],'Onbekend IO-type')
            if kind=='heatmap':
                names={r['io_id']:r['name_short'] for r in db.execute('SELECT * FROM io_types')}
                levels={'federal':'Federaal','region':'Gewest','regional':'Regionaal','commission':'Gemeenschapscommissie','community':'Gemeenschap','unknown':'Onbekend'}
                for r in rows:
                    x=levels.get(r['x'],r['x']) if chart=='level_io' else r['x']
                    r['label']=f"{x} → {r['y']} · {names.get(r['y'],'IO-type niet opgeslagen')}"
            if chart=='admin_actions':
                names={r['aa_id']:r.get('action_en',r['aa_id']) for r in (json.loads(row[0]) for row in db.execute("SELECT data FROM detail_records WHERE kind='admin_action'"))}
                for r in rows:r['label']=r['x']+' · '+names.get(r['x'],'Geen naam opgeslagen')
            vocabulary={
              'frequency':{'per_application':'Per aanvraag','one_off':'Eenmalig','periodic':'Periodiek','annual':'Jaarlijks','monthly':'Maandelijks','quarterly':'Per kwartaal','weekly':'Wekelijks','daily':'Dagelijks','one_time':'Eenmalig','event_triggered':'Bij een gebeurtenis','on_request':'Op verzoek','continuous':'Doorlopend','biennial':'Tweejaarlijks','other':'Overige frequentie','unclear':'Onduidelijke frequentie'},
              'source':{'national_act':'Nationale act','eu_directive':'EU-richtlijn','eu_regulation':'EU-verordening','eu_decision':'EU-besluit','treaty':'Verdrag','none':'Geen bron vastgelegd','other':'Overige bron'},
              'act_relation':{'amends_existing':'Wijzigt bestaande regelgeving','creates_new':'Voert nieuwe regelgeving in','approves_plan':'Keurt een plan goed','allocates_budget':'Kent budget toe','translates':'Vertaalt','new':'Nieuw','amends':'Wijzigt','repeals':'Herroept','restates':'Herneemt','implements':'Voert uit','none':'Geen (broncode none)'}}
            if chart in vocabulary:
                for r in rows:r['label']=vocabulary[chart].get(r['x'],r['label'])
                duplicates=Counter(r['label'] for r in rows)
                for r in rows:
                    if duplicates[r['label']]>1:r['label']+=f" [{r['x']}]"
            kpis=self.overview.get(filters)
            available=True;notes=[]
            if chart=='funnel':
                available=kpis['corpus']['available']
                indexed={r['x']:r for r in rows};stages=[('corpus','Corpus'),('selected','Classifierselectie'),('read','Succesvol gelezen'),('ab','Met AB'),('accepted','Met accepted AB-bepaling')]
                rows=[indexed.get(key,{'point_id':point_id(chart,key),'x':key,'y':None,'register_acts':0,'duties':0,'value':0,'drillable':False})|{'label':label} for key,label in stages]
                if available:
                    rows[0]['value']=kpis['corpus']['acts'];rows[1]['value']=kpis['corpus']['classifier_selected']
                    notes.append('Alle stappen tellen acts. Vanaf “gelezen” alleen via NUMAC gekoppelde classifiergeselecteerde acts. Accepted betekent minstens één filterpassende accepted AB-duty bij een AB-act.')
                    notes.append('De eerste twee stappen omvatten ook corpusacts zonder leesregistratie. Doorklikken toont de gekoppelde registeracts; dat aantal staat afzonderlijk bij de stap.')
                else:notes.append(kpis['corpus']['reason']);rows=[]
            if chart=='ab_year':
                years={r[0] for r in db.execute(cte+" SELECT DISTINCT coalesce(substr(pub_date,1,4),'Onbekend') FROM visible",params)}
                denominators={}
                if self.overview.corpus:
                    db.execute('ATTACH DATABASE ? AS corpusdb',(self.overview.corpus[0].resolve().as_uri()+'?mode=ro',))
                    for year,total in db.execute("SELECT substr(pub_date,1,4),count(*) FROM corpusdb.corpus GROUP BY substr(pub_date,1,4)"):
                        if year is not None and (filters.year_from is None or int(year)>=filters.year_from) and (filters.year_to is None or int(year)<=filters.year_to):
                            denominators[year]=total
                    if kpis['corpus']['available']:years.update(denominators)
                indexed={(r['x'],r['y']):r for r in rows}
                rows=[]
                for year in sorted(years):
                    for series in ('register','classifier'):
                        r=indexed.get((year,series),{'point_id':point_id(chart,year,series),'x':year,'y':series,'register_acts':0,'duties':0,'value':0,'drillable':False})
                        denominator=denominators.get(year) if kpis['corpus']['available'] else None
                        r['denominator']=denominator;r['numerator']=r['value'] if series=='classifier' else None
                        r['share']=r['value']/denominator if series=='classifier' and denominator else None
                        r['label']=year+' · '+('alle AB-registeracts' if series=='register' else 'AB binnen classifierselectie')
                        rows.append(r)
                notes.append('Staven: alle AB-registeracts per publicatiejaar. Lijn: gedetecteerde AB binnen de classifierselectie gedeeld door alle corpusacts in dat jaar; geen populatieschatting.')
                if not kpis['corpus']['available']:notes.append('Aandelen ontbreken: voor de actieve filters is geen overeenkomstige corpusnoemer vastgesteld.')
                notes.append(kpis['classifier_disclaimer'])
            if chart in CLAIM_CHARTS:notes.append(OVERLAP)
            if unit=='duties' and chart not in ('flow','actors'):notes.append('AB-bepaling betekent opgeslagen duty-teller n_ab_claims > 0. Het actverdict wordt niet herberekend, ook als beide bronuitkomsten verschillen.')
            if chart in ('flow','actors'):
                notes.append('Alle filterpassende registerbepalingen, ook niet-AB. Openbare vervolgstappen kunnen anders uit beeld verdwijnen. Losse claims tellen niet als extra bepalingen.')
            if kind=='flow':
                notes.append('Banden verbinden rechtstreeks opgeslagen dragers en ontvangers; breedte telt unieke bepalingen per paar, geen aantallen berichten, personen of bewezen ketens. “Geen ontvanger” kan bewaren/beschikbaar houden betekenen.')
            if chart=='actors':notes.append('Actornamen zijn uitsluitend samengevoegd op hoofdletters en witruimte. Gelijke omschrijvingen zijn geen geverifieerde actor-ID’s.')
            if chart in ('act_relation','amended'):notes.append('Unieke acts per opgeslagen lezersreferentie; meerdere lezingen tellen niet dubbel binnen dezelfde categorie. Een act kan in meerdere categorieën voorkomen.')
            if chart=='amended':notes.append('Alleen expliciete NUMAC-matches zijn genormaliseerd. Vrije referenties worden niet op vermoedelijke titels samengevoegd.')
            if chart in ('org','domain'):notes.append('Niet-herkende organen en beleidsrubrieken blijven Onbekend. Beleidsrubrieken volgen een expliciete diensthoofding of voordragende ministerportefeuille; geen inhoudelijke classificatie van iedere act.')
            if chart in ('org','domain'):
                total=sum(r['value'] for r in rows)
                unknown=sum(r['value'] for r in rows if r['x']=='Onbekend')
                known=total-unknown
                percent=f'{100*known/total:.2f}'.replace('.',',') if total else None
                subject='een beleidsrubriek' if chart=='domain' else 'een herkend overheidsorgaan'
                notes.append(f'Dekking binnen deze selectie: {known} van {total} AB-acts ({percent}%) met {subject}; {unknown} onbekend. De bekende acts vormen geen representatieve steekproef.' if total else 'Dekking: geen AB-acts in deze selectie.')
                coverage={'known':known,'total':total,'unknown':unknown,'description':notes[-1]}
            if chart=='scope_year':
                numeric=[r[0] for r in db.execute(cte+" SELECT DISTINCT substr(pub_date,1,4) FROM visible WHERE pub_date IS NOT NULL",params)]
                if numeric and rows:
                    years=[str(y) for y in range(int(min(numeric)),int(max(numeric))+1)];series={r['y'] for r in rows};known={(r['x'],r['y']) for r in rows}
                    for year in years:
                        for scope in series:
                            if (year,scope) not in known:rows.append({'point_id':point_id(chart,year,scope),'x':year,'y':scope,'label':year+' → '+scope,'value':0,'register_acts':0,'duties':0,'drillable':False})
                notes.append('Opgeslagen actscope van AB-acts; onbekend blijft een afzonderlijke reeks. Geen herberekening uit lezersclaims.')
            if chart=='eu_instruments':notes.append('Letterlijke source_ref bij claims met EU-source_kind; geen instrument uit de titel geraden.')
            if chart in ('data_items','admin_actions'):notes.append('Alleen expliciet opgeslagen items/handelingen; lege lijsten zijn niet aangevuld. Het aantal bepalingen is geen aantal uitgevoerde handelingen of gemeten kosten.')
            examples=[dict(r) for r in db.execute(cte+EXAMPLES,params)] if chart in ('flow','flow_ab','actors') else []
        total_points=len(rows)
        total_categories=len({r['y'] for r in rows}) if kind=='heatmap' else len(rows)
        if kind=='heatmap' and top:
            ranked={}
            for r in rows:ranked[r['y']]=ranked.get(r['y'],0)+r['value']
            keep={k for k,_ in sorted(ranked.items(),key=lambda p:(-p[1],str(p[0])))[:top]}
            rows=[r for r in rows if r['y'] in keep]
        elif kind in ('bar','flow'):
            rows=sorted(rows,key=lambda r:(-r['value'],r['label']))
            if top:rows=rows[:top]
        else:rows.sort(key=lambda r:(str(r['x']),str(r['y']))) if kind!='funnel' else None
        shown=len({r['y'] for r in rows}) if kind=='heatmap' else len(rows)
        category_unit='IO-types' if kind=='heatmap' else 'datapunten' if kind in ('combo','stack','funnel') else 'relaties' if kind=='flow' else 'categorieën'
        truncated=shown<total_categories
        description=(f'{shown} van {total_categories} {category_unit} getoond. Niet-getoonde categorieën zijn niet samengevoegd in “overige”.' if truncated else f'Alle {total_categories} aanwezige {category_unit} binnen deze selectie getoond.') if rows else 'Geen gegevens binnen deze selectie.'
        display={'shown':shown,'total':total_categories,'unit':category_unit,'limited':truncated,
                 'points_shown':len(rows),'points_total':total_points,'description':description}
        if kind in ('bar','flow','heatmap'):notes.append(description)
        names={'year_from':'Vanaf','year_to':'Tot','run_id':'Run','orgaan':'Orgaan','beleidsdomein':'Beleidsrubriek','q':'Zoekterm','verdict':'Verdict','level':'Niveau','entity':'Entiteit','lang':'Taal','act_form':'Instrument','io_id':'IO','duty_status':'Status'}
        selection=self.store.chart_point(filters)
        description=[names.get(k,k)+': '+str(v)[:70] for k,v in filters.as_dict().items() if v not in (None,'') and k not in {'page','size','sort','direction','q_in','chart_id','point_id'}]
        if selection:description.append('Grafiekselectie: '+selection['label'][:150])
        return {'chart_id':chart,'title':title,'kind':kind,'unit':unit,'group':group,'available':available,
                'rows':rows,'notes':notes,'top':top,'total_categories':total_categories,'display':display,
                'filters':filters.as_dict(),'sources':kpis['sources'],'snapshot_id':kpis['snapshot_id'],
                'projection_id':self.store.analysis_projection[1]['projection_id'],'flow_examples':examples,'coverage':coverage,
                'filter_summary':' | '.join(description) or 'Geen actieve filters; laatste verdict-run per act.',
                'full_act_text_loaded':False}

    def evidence(self,chart,point,filters=None,limit=30):
        f=filters or ActFilters();selected=replace(with_point(f,chart,point),page=1,size=limit)
        acts=self.store.list(selected)
        policy_proofs=[]
        if chart in ('domain','org'):
            for act in acts['items']:
                mapping=self.store.authority(act['act_id'],act['numac'])
                proof=mapping.get('domain_evidence') if chart=='domain' else mapping.get('evidence')
                if proof:
                    policy_proofs.append({'act_id':act['act_id'],'numac':act['numac'],
                        'beleidsdomein':mapping['beleidsdomein'],
                        'label':mapping['beleidsdomein'] if chart=='domain' else mapping['orgaan'],
                        'method':mapping['domain_method'] if chart=='domain' else 'expliciete_diensthoofding',
                        'evidence':proof})
        cte,params=selection_sql(selected,bool(self.store.authority_mapping),True)
        with self.store.connect() as db:
            rows=db.execute(cte+''' SELECT DISTINCT m.duty_id,m.obligation_id,m.act_id,m.run_id FROM visible v
                JOIN analysisdb.membership m ON m.act_id=v.act_id AND m.run_id=v.run_id
                WHERE m.chart_id=? AND m.point_id=? AND m.obligation_id IS NOT NULL
                AND EXISTS(SELECT 1 FROM eligible_duties d WHERE d.duty_id=m.duty_id)
                AND EXISTS(SELECT 1 FROM matched_claims c WHERE c.obligation_id=m.obligation_id)
                ORDER BY m.act_id,m.duty_id,m.obligation_id LIMIT ?''',params+[chart,point,limit]).fetchall()
            proofs=[]
            for did,cid,aid,run in rows:
                row=db.execute("SELECT data FROM detail_records WHERE kind='claim' AND key=?",(str(cid),)).fetchone()
                if row:
                    c=json.loads(row[0]);proofs.append({k:c.get(k) for k in ('obligation_id','reading_id','act_id','run_id','duty_bearer','duty_bearer_kind','recipient','recipient_kind','quote','provision','io_id','counts_as_ab','data_items')}|{'duty_id':did})
        return {'acts':acts,'proofs':proofs,'policy_proofs':policy_proofs,'proof_limit':limit,'full_act_text_loaded':False}

    def image(self,chart,filters=None,top=None,format='svg',ui_language='nl'):
        if chart in LARGE_CHARTS and top==0:raise ValueError('Gebruik de volledige CSV voor deze grote categorieënlijst.')
        data=self.get(chart,filters,top)
        f=ActFilters(**data['filters'])
        return self._image_cached(chart,f,data['top'],format,ui_language)

    @lru_cache(maxsize=64)
    def _image_cached(self,chart,filters,top,format,ui_language='nl'):
        from ..logic.chart_render import render
        from ..logic.i18n import localize_chart
        return render(localize_chart(self.get(chart,filters,top),ui_language),format)

    def flow_act(self,act_id,run_id=None):
        if self.detail is None:raise CacheError('Actdetails niet beschikbaar.')
        d=self.detail.get(act_id,run_id)
        if d is None:return None
        result=matching_steps(d['duties'],d['claims'])
        return result|{'act':d['act'],'run_id':d['run_id'],'snapshot_id':d['snapshot_id'],
                       'sources':d['source'],'full_act_text_loaded':False}


def csv_export(chart):
    stream=io.StringIO(newline='');fields=['label','x','y','value','unit','register_acts','numerator','denominator','share','point_id','register_source_utc','corpus_source_utc','filters_json','export_scope','categories_shown','categories_total','category_unit','register_snapshot_id','projection_id']
    writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
    def safe(value):
        if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):return "'"+value
        return value
    for row in chart['rows'] if chart['available'] else []:
        record=row|{'unit':chart['unit'],'register_source_utc':chart['sources']['register']['snapshot_utc'],
                    'corpus_source_utc':(chart['sources']['corpus'] or {}).get('snapshot_utc'),'filters_json':json.dumps(chart['filters'],ensure_ascii=False),
                    'export_scope':'getoonde_categorieen' if chart.get('display',{}).get('limited') else 'alle_aanwezige_categorieen_binnen_filters',
                    'categories_shown':chart.get('display',{}).get('shown'),
                    'categories_total':chart.get('display',{}).get('total'),
                    'category_unit':chart.get('display',{}).get('unit'),
                    'register_snapshot_id':chart.get('snapshot_id'),'projection_id':chart.get('projection_id')}
        writer.writerow({k:safe(v) for k,v in record.items() if k in fields})
    return ('\ufeff'+stream.getvalue()).encode('utf-8')
