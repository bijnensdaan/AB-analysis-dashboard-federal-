"""Actdetails uit dezelfde read-only snapshot als de lijst; tekst apart en op aanvraag."""
from functools import lru_cache
import json
import re

from ..logic.detail import amended_links,disagreements,explain_verdict
from .cache import CacheError


class DetailRepository:
    def __init__(self,store,text_provider=None,eu_catalog=()):
        self.store=store;self.text_provider=text_provider
        self.eu_available={row['celex'] for row in eu_catalog}
        self.ready=store.manifest.get('details_available',False)
        self.lookups={}
        if self.ready:
            with store.connect() as db:
                for kind,key in [('io_type','io_id'),('cost_category','code'),('admin_action','aa_id')]:
                    self.lookups[kind]={r[key]:r for r in (json.loads(row[0]) for row in db.execute('SELECT data FROM detail_records WHERE kind=?',(kind,)))}
                self.acts_by_numac={r['numac']:r['act_id'] for r in db.execute('SELECT act_id,numac FROM acts')}

    @lru_cache(maxsize=64)
    def get(self,act_id,run_id=None):
        if type(act_id) is not int or act_id<1 or (run_id is not None and (type(run_id) is not int or run_id<1)):
            raise ValueError('Ongeldige act of run.')
        if not self.ready:raise CacheError('Deze snapshot bevat nog geen actdetails. Start het dashboard met --ververs.')
        with self.store.connect() as db:
            rows=db.execute("SELECT kind,data FROM detail_records WHERE act_id=? AND kind IN ('act','verdict','reading','duty','claim','review','text_metadata')",(act_id,)).fetchall()
            grouped={}
            for kind,raw in rows:grouped.setdefault(kind,[]).append(json.loads(raw))
            verdicts=grouped.get('verdict',[])
            if not grouped.get('act') or not verdicts:return None
            chosen=run_id if run_id is not None else max(v['run_id'] for v in verdicts)
            verdict=next((v for v in verdicts if v['run_id']==chosen),None)
            if verdict is None:return None
            links=db.execute('''SELECT dc.duty_id,dc.obligation_id FROM duty_claims dc
                JOIN duties d USING(duty_id) WHERE d.act_id=?''',(act_id,)).fetchall()
        all_duties={d['duty_id']:d for d in grouped.get('duty',[])}
        all_claims={c['obligation_id']:c for c in grouped.get('claim',[])}
        readings=[r for r in grouped.get('reading',[]) if r['run_id']==chosen]
        reading_map={r['reading_id']:r for r in readings}
        run=next((r for r in self.store.manifest['runs'] if r['run_id']==chosen),{})
        roles={m['model']:m['role'] for m in run.get('models',[])}
        duties=[dict(d) for d in all_duties.values() if d['run_id']==chosen]
        claims=[dict(c) for c in all_claims.values() if c['run_id']==chosen]
        selected_claims={c['obligation_id']:c for c in claims}
        by_duty={d['duty_id']:[] for d in duties};by_claim={c['obligation_id']:[] for c in claims}
        quote_targets={}
        for duty in all_duties.values():
            if duty.get('quote_norm'):quote_targets.setdefault(duty['quote_norm'],set()).add(duty['duty_id'])
        for duty_id,claim_id in links:
            if claim_id in all_claims and all_claims[claim_id].get('quote_norm'):
                quote_targets.setdefault(all_claims[claim_id]['quote_norm'],set()).add(duty_id)
            if duty_id in by_duty and claim_id in selected_claims:
                by_duty[duty_id].append(selected_claims[claim_id]);by_claim[claim_id].append(duty_id)
        for claim in claims:
            reading=reading_map.get(claim['reading_id'],{})
            claim['reader']={'reading_id':claim['reading_id'],'model':reading.get('model_slug'),
                             'role':roles.get(reading.get('model_slug'))}
            claim['linked_duty_ids']=sorted(by_claim[claim['obligation_id']])
            claim['io_type']=self.lookups['io_type'].get(claim.get('io_id'))
            claim['cost_definition']=self.lookups['cost_category'].get(claim.get('cost_category'))
            claim['action_details']=[self.lookups['admin_action'].get(code,{'aa_id':code,'std_minutes':None,'unavailable':True})
                                     for code in claim.get('admin_actions') or []]
            tokens=sorted(set(re.findall(r'(?<![A-Z0-9])[0-9]\d{4}[A-Z]{1,2}\d{4}(?![A-Z0-9])',str(claim.get('source_ref') or '').upper())))
            claim['eu_links']=[{'celex':token,'local_available':token in self.eu_available,
                               'url':'https://eur-lex.europa.eu/legal-content/NL/TXT/?uri=CELEX:'+token} for token in tokens]
        reviews=[]
        for stored in sorted(grouped.get('review',[]),key=lambda r:(r.get('decided_at') or '',r['decision_id'])):
            review=dict(stored);duty_id=review.get('duty_id')
            if duty_id is not None:
                targets={duty_id} if duty_id in all_duties else set()
                association='duty_id' if targets else 'onbekende duty'
            else:
                targets=quote_targets.get(review.get('quote_norm'),set())
                association='citaatmatch zonder run-ID' if len(targets)<=1 else 'ambigue citaatmatch'
            runs=sorted({all_duties[d]['run_id'] for d in targets if d in all_duties})
            review['association']={'kind':association,'duty_ids':sorted(targets),'run_ids':runs,
                                   'selected_duty_ids':sorted(targets & set(by_duty)),
                                   'ambiguous':duty_id is None and len(targets)>1,
                                   'current_by_duty_id':duty_id is not None and duty_id in by_duty}
            reviews.append(review)
        for duty in duties:
            linked=by_duty[duty['duty_id']]
            duty['claims']=sorted(linked,key=lambda c:(c['reader']['role']!='primary',c['obligation_id']))
            duty['actual_claims']=len(linked)
            duty['actual_ab_claims']=sum(c.get('counts_as_ab') is True for c in linked)
            duty['actual_readers']=len({c['reading_id'] for c in linked})
            duty['differences']=disagreements(linked)
            duty['reviews']=[r for r in reviews if duty['duty_id'] in r['association']['selected_duty_ids']]
        duties.sort(key=lambda d:d['duty_id'])
        text_metadata=next(iter(grouped.get('text_metadata',[])),None)
        authority=self.store.authority(act_id,grouped['act'][0]['numac'])
        return {'act':grouped['act'][0],'verdict':verdict,'run':run,'run_id':chosen,
                'available_runs':sorted({v['run_id'] for v in verdicts}),'readings':readings,
                'duties':duties,'claims':claims,'loose_claims':[c for c in claims if not c['linked_duty_ids']],
                'reviews':reviews,'text_metadata':text_metadata,
                'explanation':explain_verdict(verdict,duties,claims),
                'amended_acts':amended_links(readings,self.acts_by_numac),
                'orgaan':authority['orgaan'],'beleidsdomein':authority['beleidsdomein'],'authority_mapping':authority,
                'snapshot_id':self.store.manifest['snapshot_id'],'source':self.store.manifest['source'],
                'full_text_loaded':False}

    def text(self,act_id,run_id=None,variant='raw'):
        if variant not in ('raw','llm'):raise ValueError('Onbekende tekstversie.')
        detail=self.get(act_id,run_id)
        if detail is None:return None
        if self.text_provider is None:return {'available':False,'message':'Tekstverbinding is niet ingesteld.'}
        body=self.text_provider.get(detail['text_metadata'])
        if not body['available']:return body
        from ..logic.highlights import highlight
        content=body['text']['raw_text' if variant=='raw' else 'llm_text']
        if content is None:return {'available':False,'message':'Deze tekstversie is niet opgeslagen.'}
        return {'available':True,'variant':variant,'content':content,'provenance':body['provenance'],
                'snapshot_id':detail['snapshot_id'],**highlight(content,detail)}
