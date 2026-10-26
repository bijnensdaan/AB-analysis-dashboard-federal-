"""Gepagineerde actlijst op één onveranderlijke registersnapshot.

Alle dynamische SQL-identifiers komen uit whitelists; waarden zijn parameters.
Lezersfilters en citaatwoorden moeten op dezelfde claim passen. Dutystatus
moet, samen met lezersfilters, bij diezelfde gekoppelde duty horen.
"""
from contextlib import contextmanager
import math
import sqlite3

from ..logic.act_filters import ActFilters,CLAIM_FIELDS,norm,search_terms
from .actlist_snapshot import load_snapshot
from .authority_mapping import load_mapping
from .analysis_projection import load_projection

CLAIM_COLUMNS={key:('ab_scope' if key=='scope' else key) for key in CLAIM_FIELDS}
SORT_COLUMNS={'numac':'numac_search','title':'title_search','pub_date':'pub_date','act_form':'act_form',
              'level':'level','orgaan':'orgaan','ab':'ab','ab_duties':'ab_duties','scope':'ab_scope',
              'needs_review':'needs_review','truncated':'truncated','run_id':'run_id','lang':'lang'}


def bool_filter(column,value,params):
    if value=='unknown':return column+' IS NULL'
    params.append(1 if value=='yes' else 0)
    return column+'=?'


def words_sql(column,terms,params):
    params.extend(terms)
    return ' AND '.join('instr('+column+',?)>0' for _ in terms) or '1=1'


def selection_sql(filters,mapped=False,analysis=False):
    """CTE's bewaren unieke acts/duties; nooit obligation-rijen als bepalingen tellen."""
    params=[];core=['coalesce(r.readings,0)>0']
    if filters.run_id is None:
        chosen='JOIN latest l ON l.act_id=v.act_id AND l.run_id=v.run_id'
    else:
        chosen='';core.append('v.run_id=?');params.append(filters.run_id)
    for attr in ('year_from','year_to'):
        year=getattr(filters,attr)
        if year is not None:
            core.append('a.pub_date '+('>= ?' if attr=='year_from' else '< ?'))
            params.append(f'{year if attr=="year_from" else year+1:04d}-01-01')
    for key in ('level','entity','act_form','lang'):
        if getattr(filters,key):core.append('a.'+key+'=?');params.append(getattr(filters,key))
    if filters.verdict:core.append(bool_filter('v.ab',filters.verdict,params))
    truncated="CASE WHEN r.text_truncated=1 OR t.raw_chars=32767 THEN 1 WHEN t.raw_chars IS NULL THEN NULL ELSE 0 END"
    if filters.truncated:core.append(bool_filter('('+truncated+')',filters.truncated,params))
    if filters.disposition:core.append('t.disposition=?');params.append(filters.disposition)
    terms=search_terms(filters)
    if terms and filters.q_in in ('numac','title'):
        core.append(words_sql('a.'+filters.q_in+'_search',terms,params))
    organ="coalesce(am.orgaan,'Onbekend')" if mapped else "'Onbekend'"
    domain="coalesce(am.beleidsdomein,'Onbekend')" if mapped else "'Onbekend'"
    for field,column in [('orgaan',organ),('beleidsdomein',domain)]:
        if getattr(filters,field):core.append(column+'=?');params.append(getattr(filters,field))
    authority_join='LEFT JOIN authorities.authority_map am ON am.act_id=a.act_id AND am.numac=a.numac' if mapped else ''
    if filters.chart_id:
        if not analysis:raise ValueError('Grafiekselectie is niet beschikbaar; wis de grafiekfilter.')
        from ..logic.analysis import selections
        for chart,point in selections(filters):
            core.append('EXISTS(SELECT 1 FROM analysisdb.membership m WHERE m.chart_id=? AND m.point_id=? AND m.act_id=v.act_id AND m.run_id=v.run_id)')
            params.extend([chart,point])
    query='''WITH selected AS (
      SELECT a.*,v.run_id,v.ab,v.ab_scope,v.needs_review,'''+organ+''' orgaan,'''+domain+''' beleidsdomein,
       r.readings,r.successes,r.errors,'''+truncated+''' truncated,t.disposition,
       coalesce(tot.ab_duties,0) ab_duties_total
      FROM verdicts v '''+chosen+''' JOIN acts a USING(act_id)
      LEFT JOIN reading_summary r ON r.act_id=v.act_id AND r.run_id=v.run_id
      LEFT JOIN text_metadata t ON t.act_id=a.act_id
      LEFT JOIN duty_totals tot ON tot.act_id=v.act_id AND tot.run_id=v.run_id
      '''+authority_join+''' WHERE '''+' AND '.join(core)+')'
    claim_params=[];claim_pred=[]
    has_claim_filters=any(getattr(filters,k) for k in CLAIM_FIELDS)
    for key,column in CLAIM_COLUMNS.items():
        value=getattr(filters,key)
        if value:
            if key=='is_new_here':claim_pred.append(bool_filter('o.'+column,value,claim_params))
            else:claim_pred.append('o.'+column+'=?');claim_params.append(value)
    if terms and filters.q_in in ('all','quote'):
        haystack="(s.numac_search||' '||s.title_search||' '||o.quote_search)" if filters.q_in=='all' else 'o.quote_search'
        claim_pred.append(words_sql(haystack,terms,claim_params))
    if filters.chart_id:
        for chart,point in selections(filters):
            claim_pred.append('''EXISTS(SELECT 1 FROM analysisdb.membership m WHERE m.chart_id=? AND m.point_id=?
              AND m.act_id=o.act_id AND m.run_id=o.run_id AND (m.obligation_id IS NULL OR m.obligation_id=o.obligation_id))''')
            claim_params.extend([chart,point])
    query+=', matched_claims AS (SELECT o.obligation_id,o.act_id,o.run_id,o.quote FROM claims o JOIN selected s ON s.act_id=o.act_id AND s.run_id=o.run_id WHERE '+(' AND '.join(claim_pred) or '1=1')+')'
    params.extend(claim_params)
    duty_pred=[]
    if filters.duty_status:duty_pred.append('d.status=?');params.append(filters.duty_status)
    if filters.chart_id:
        for chart,point in selections(filters):
            duty_pred.append('''EXISTS(SELECT 1 FROM analysisdb.membership m WHERE m.chart_id=? AND m.point_id=?
              AND m.act_id=d.act_id AND m.run_id=d.run_id AND (m.duty_id IS NULL OR m.duty_id=d.duty_id)
              AND (m.obligation_id IS NULL OR EXISTS(SELECT 1 FROM matched_claims mc WHERE mc.obligation_id=m.obligation_id)))''')
            params.extend([chart,point])
    linked='EXISTS(SELECT 1 FROM duty_claims dc JOIN matched_claims mc USING(obligation_id) WHERE dc.duty_id=d.duty_id)'
    if has_claim_filters or (terms and filters.q_in=='quote'):
        duty_pred.append(linked)
    elif terms and filters.q_in=='all':
        duty_pred.append('('+words_sql("(s.numac_search||' '||s.title_search)",terms,params)+' OR '+linked+')')
    query+=', eligible_duties AS (SELECT d.* FROM duties d JOIN selected s ON s.act_id=d.act_id AND s.run_id=d.run_id WHERE '+(' AND '.join(duty_pred) or '1=1')+')'
    query+=''', duty_counts AS (SELECT act_id,run_id,count(*) matched_duties,
      sum(n_ab_claims>0) ab_duties,sum(status='needs_review') needs_review_duties
      FROM eligible_duties GROUP BY act_id,run_id)'''
    visible_pred=[]
    exists='EXISTS(SELECT 1 FROM matched_claims mc WHERE mc.act_id=s.act_id AND mc.run_id=s.run_id)'
    if has_claim_filters or (terms and filters.q_in=='quote'):visible_pred.append(exists)
    elif terms and filters.q_in=='all':
        visible_pred.append('('+words_sql("(s.numac_search||' '||s.title_search)",terms,params)+' OR '+exists+')')
    if filters.duty_status:visible_pred.append('coalesce(d.matched_duties,0)>0')
    if filters.chart_id:
        for chart,point in selections(filters):
            visible_pred.append('''(coalesce(d.matched_duties,0)>0 OR EXISTS(SELECT 1 FROM analysisdb.membership m
              WHERE m.chart_id=? AND m.point_id=? AND m.act_id=s.act_id AND m.run_id=s.run_id AND m.duty_id IS NULL))''')
            params.extend([chart,point])
    query+=''', visible AS (SELECT s.*,coalesce(d.matched_duties,0) matched_duties,
       coalesce(d.ab_duties,0) ab_duties,coalesce(d.needs_review_duties,0) needs_review_duties
       FROM selected s LEFT JOIN duty_counts d ON d.act_id=s.act_id AND d.run_id=s.run_id
       WHERE '''+(' AND '.join(visible_pred) or '1=1')+')'
    return query,params


class ActListStore:
    def __init__(self,path,manifest,authority_root=None,load_authorities=True,analysis_root=None,load_analysis=True):
        self.path=path
        self.manifest=manifest
        self.authority_mapping=load_mapping(manifest,**({'root':authority_root} if authority_root is not None else {})) if load_authorities else None
        self.analysis_projection=load_projection(manifest,self.authority_mapping,**({'root':analysis_root} if analysis_root is not None else {})) if load_analysis else None
        self.run_ids={r['run_id'] for r in manifest['runs']}
        with self.connect() as db:
            self.options=self._options(db)

    @classmethod
    def load(cls,settings,root=None):
        return cls(*load_snapshot(settings,**({'root':root} if root is not None else {})))

    @contextmanager
    def connect(self):
        con=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            if self.authority_mapping:
                con.execute('ATTACH DATABASE ? AS authorities',(self.authority_mapping[0].resolve().as_uri()+'?mode=ro',))
            if self.analysis_projection:
                con.execute('ATTACH DATABASE ? AS analysisdb',(self.analysis_projection[0].resolve().as_uri()+'?mode=ro',))
            con.execute('PRAGMA query_only=ON');con.row_factory=sqlite3.Row
            yield con
        finally:con.close()

    def _options(self,db):
        """Facetten uit opgeslagen bronwaarden; geen nieuwe semantische classificatie."""
        out={}
        for field in ('level','entity','act_form','lang'):
            out[field]=[r[0] for r in db.execute('SELECT DISTINCT '+field+' FROM acts WHERE '+field+" IS NOT NULL AND "+field+"<>'' ORDER BY 1")]
        for field in CLAIM_FIELDS:
            if field=='is_new_here':continue
            column=CLAIM_COLUMNS[field]
            out[field]=[r[0] for r in db.execute('SELECT DISTINCT '+column+' FROM claims WHERE '+column+" IS NOT NULL AND "+column+"<>'' ORDER BY 1")]
        out['disposition']=[r[0] for r in db.execute('SELECT DISTINCT disposition FROM text_metadata WHERE disposition IS NOT NULL ORDER BY 1')]
        out['io_types']=[dict(r) for r in db.execute('SELECT * FROM io_types ORDER BY io_id')]
        out['cost_categories']=[dict(r) for r in db.execute('SELECT * FROM cost_categories ORDER BY code')]
        for field in ('orgaan','beleidsdomein'):
            out[field]=[r[0] for r in db.execute('SELECT DISTINCT '+field+' FROM authorities.authority_map ORDER BY 1')] if self.authority_mapping else ['Onbekend']
        return out

    def authority(self,act_id,numac):
        if self.authority_mapping:
            import json
            with self.connect() as db:
                row=db.execute('SELECT data FROM authorities.authority_map WHERE act_id=? AND numac=?',(act_id,numac)).fetchone()
            if row:return {**json.loads(row[0]),'mapping_id':self.authority_mapping[1]['mapping_id'],
                           'register_snapshot_id':self.manifest['snapshot_id'],'source':self.authority_mapping[1]['source']}
        return {'orgaan':'Onbekend','beleidsdomein':'Onbekend','status':'geen_koppeltabel','evidence':[]}

    def list(self,filters=None):
        filters=filters or ActFilters()
        if filters.run_id is not None and filters.run_id not in self.run_ids:
            raise ValueError('Onbekende run.')
        point=self.chart_point(filters)
        cte,params=selection_sql(filters,bool(self.authority_mapping),bool(self.analysis_projection))
        with self.connect() as db:
            summary=dict(db.execute(cte+''' SELECT count(*) acts,coalesce(sum(matched_duties),0) duties,
              coalesce(sum(ab_duties),0) ab_duties,coalesce(sum(successes>0),0) read_success,
              coalesce(sum(successes=0),0) read_failed FROM visible''',params).fetchone())
            pages=max(1,math.ceil(summary['acts']/filters.size));page=min(filters.page,pages)
            sort=SORT_COLUMNS[filters.sort]
            fields='act_id,numac,title,pub_date,act_form,level,entity,lang,url,run_id,ab,ab_scope,needs_review,orgaan,beleidsdomein,truncated,disposition,ab_duties,ab_duties_total,matched_duties,needs_review_duties,readings,successes,errors'
            quoted='(SELECT mc.quote FROM matched_claims mc WHERE mc.act_id=visible.act_id AND mc.run_id=visible.run_id ORDER BY mc.obligation_id LIMIT 1)' if norm(filters.q) and filters.q_in in ('all','quote') else 'NULL'
            rows=db.execute(cte+' SELECT '+fields+','+quoted+' matched_quote FROM visible ORDER BY '+sort+' IS NULL,'+sort+' '+filters.direction+',act_id ASC LIMIT ? OFFSET ?',params+[filters.size,(page-1)*filters.size]).fetchall()
            items=[]
            for row in rows:
                item=dict(row)
                for key in ('ab','needs_review','truncated'):
                    if item[key] is not None:item[key]=bool(item[key])
                terms=search_terms(filters)
                # Een titel/NUMAC-hit is geen citaathit: geen willekeurig citaat suggereren.
                if filters.q_in=='all' and all(term in norm((item['numac'] or '')+' '+(item['title'] or '')) for term in terms):
                    item['matched_quote']=None
                if item['matched_quote']:
                    quote=' '.join(item['matched_quote'].split())
                    positions=[quote.casefold().find(term) for term in terms]
                    position=min((p for p in positions if p>=0),default=0);start=max(0,position-70)
                    item['matched_quote']=('…' if start else '')+quote[start:start+260]+('…' if len(quote)>start+260 else '')
                items.append(item)
        return {'items':items,'summary':summary,'page':page,'pages':pages,'size':filters.size,
                'filters':filters.as_dict(),'snapshot_id':self.manifest['snapshot_id'],'chart_selection':point}

    def chart_point(self,filters):
        if not filters.chart_id:return None
        if not self.analysis_projection:raise ValueError('Geen grafiekcache voor deze selectie. Wis de grafiekfilter.')
        from ..logic.analysis import selections
        rows=[]
        with self.connect() as db:
            for pair in selections(filters):
                row=db.execute('SELECT chart_id,point_id,x,y,label FROM analysisdb.points WHERE chart_id=? AND point_id=?',pair).fetchone()
                if row is None:raise ValueError('Grafiekpunt bestaat niet in deze snapshot. Wis de grafiekfilter.')
                item=dict(row)
                if item['chart_id'] in ('flow','flow_ab'):
                    from ..logic.analysis import actor_label
                    item['label']=actor_label(item['x'])+' → '+actor_label(item['y'])
                rows.append(item)
        return {'selections':rows,'label':' ∩ '.join(r['label'] for r in rows)}

    def meta(self):
        return {'snapshot_id':self.manifest['snapshot_id'],'source':self.manifest['source'],
                'options':self.options,'runs':self.manifest['runs'],'control':self.manifest['control'],
                'authority_mapping_available':bool(self.authority_mapping),
                'authority_mapping':{k:self.authority_mapping[1][k] for k in ('mapping_id','source','coverage','created_utc','domain_method')} if self.authority_mapping else None,
                'full_act_text_loaded':False,
                'details_available':self.manifest.get('details_available',False)}
