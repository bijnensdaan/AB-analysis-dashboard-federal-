"""KPI's met precies dezelfde act-/dutyselectie als de actlijst; cache-only."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from functools import lru_cache

from .actlist import selection_sql
from .overview_corpus import SQL
from ..logic.act_filters import ActFilters
from ..logic.metrics import require,DISCLAIMER

REGISTER_KPIS=(SQL/'register_kpis.sql').read_text(encoding='utf-8')
SCOPE_SQL=''' SELECT ab_scope scope,count(*) acts FROM visible WHERE ab IS TRUE GROUP BY ab_scope ORDER BY ab_scope IS NULL,ab_scope'''
PRESENTATION_FIELDS={'page','size','sort','direction','q_in'}


class OverviewRepository:
    def __init__(self,store,corpus=None):
        self.store=store;self.corpus=corpus

    def get(self,filters=None):
        filters=filters or ActFilters()
        # Paginering en sortering veranderen de selectie niet.
        filters=replace(filters,page=1,size=25,sort='pub_date',direction='desc',q=filters.q.strip(),q_in=filters.q_in if filters.q.strip() else 'all')
        if filters.run_id is not None and filters.run_id not in self.store.run_ids:raise ValueError('Onbekende run.')
        self.store.chart_point(filters)
        return deepcopy(self._cached(filters))

    @lru_cache(maxsize=128)
    def _cached(self,filters):
        cte,params=selection_sql(filters,bool(self.store.authority_mapping),bool(self.store.analysis_projection))
        with self.store.connect() as db:
            register=dict(db.execute(cte+REGISTER_KPIS,params).fetchone())
            scopes=[dict(row) for row in db.execute(cte+SCOPE_SQL,params)]
            for row in scopes:row['share_of_ab_acts']=row['acts']/register['acts_ab'] if register['acts_ab'] else None
            corpus={'available':False,'reason':'Corpusmetadata is nog niet gecachet. Bouw de overzichtscache expliciet op.','unsupported_filters':[]}
            cohort=None
            if self.corpus:
                path,manifest=self.corpus
                db.execute('ATTACH DATABASE ? AS corpusdb',(path.resolve().as_uri()+'?mode=ro',))
                pred=[];p=[]
                if filters.year_from is not None:pred.append('pub_date>=?');p.append(f'{filters.year_from:04d}-01-01')
                if filters.year_to is not None:pred.append('pub_date<?');p.append(f'{filters.year_to+1:04d}-01-01')
                period=dict(db.execute('SELECT count(*) acts,coalesce(sum(classifier_selected),0) classifier_selected FROM corpusdb.corpus'+(' WHERE '+' AND '.join(pred) if pred else ''),p).fetchone())
                unsupported=[key for key,value in filters.as_dict().items() if key not in PRESENTATION_FIELDS|{'run_id','year_from','year_to','point_id'} and value not in (None,'')]
                corpus={'available':not unsupported,'acts':period['acts'] if not unsupported else None,
                        'classifier_selected':period['classifier_selected'] if not unsupported else None,
                        'period_context':period,'unsupported_filters':unsupported,
                        'reason':'Voor deze registerfilters is geen overeenkomstig gefilterde corpusnoemer vastgesteld.' if unsupported else '',
                        'applied_filters':{'year_from':filters.year_from,'year_to':filters.year_to},
                        'run_note':'Een runfilter selecteert de registerverwerking; het corpus heeft geen runs.',
                        'snapshot_id':manifest['snapshot_id'],'source':manifest['source']}
                cohort=dict(db.execute(cte+''' SELECT
                   coalesce(sum(c.numac IS NOT NULL),0) register_in_corpus,
                   coalesce(sum(c.classifier_selected IS TRUE),0) register_in_classifier,
                   coalesce(sum(c.classifier_selected IS TRUE AND v.ab IS TRUE),0) classifier_ab,
                   coalesce(sum(c.numac IS NULL),0) register_outside_corpus,
                   coalesce(sum(c.classifier_selected IS NOT TRUE),0) register_outside_classifier
                   FROM visible v LEFT JOIN corpusdb.corpus c ON c.numac=v.numac''',params).fetchone())
        require(register['acts']==register['acts_ab']+register['acts_no_ab']+register['acts_unknown'],'Verdict-KPI somcontrole faalt.')
        require(register['duties']==register['duties_accepted']+register['duties_needs_review'],'Onbekende duty-status; niet stilzwijgend gegroepeerd.')
        require(register['ab_duties']==register['ab_duties_accepted']+register['ab_duties_needs_review'],'AB-duty somcontrole faalt.')
        require(sum(r['acts'] for r in scopes)==register['acts_ab'],'Scopeverdeling telt niet op tot alle AB-acts.')
        register_source=self.store.manifest['source']
        corpus_source=self.corpus[1]['source'] if self.corpus else None
        difference=abs((datetime.fromisoformat(register_source['snapshot_utc'])-datetime.fromisoformat(corpus_source['snapshot_utc'])).total_seconds()) if corpus_source else None
        return {'register':register,'scopes':scopes,'corpus':corpus,'classifier_cohort':cohort,
                'filters':filters.as_dict(),'snapshot_id':self.store.manifest['snapshot_id'],
                'sources':{'register':register_source,'corpus':corpus_source},
                'atomic_across_databases':False,'source_time_difference_seconds':difference,
                'scope_denominator':'Alle acts met verdict AB binnen dezelfde registerselectie, inclusief onbekende scope; iedere act telt eenmaal.',
                'classifier_disclaimer':DISCLAIMER,
                'full_act_text_loaded':False}
