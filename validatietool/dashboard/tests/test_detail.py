"""Bewijsbehoud, reviewprovenance, tekstversies, markeringen en exports."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import MagicMock,patch
from urllib.request import urlopen
from urllib.error import HTTPError

from dashboard.tests.test_actlist import fixture
from dashboard.data.detail import DetailRepository
from dashboard.data.detail_text import DetailTextProvider,content_hash
from dashboard.logic.highlights import highlight
from dashboard.logic.detail import amended_links
from dashboard.logic.detail_export import markdown_export,pdf_export
from dashboard.data.cache import CacheError
from dashboard.ui.actlist_server import ActListHandler,ThreadingHTTPServer


def detail_fixture(root):
    cfg,store=fixture(root)
    db=sqlite3.connect(store.path);db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE detail_records(kind TEXT,key TEXT,act_id INTEGER,run_id INTEGER,data TEXT,PRIMARY KEY(kind,key))')
    db.execute('CREATE INDEX detail_act ON detail_records(kind,act_id,run_id)')
    def add(kind,key,item):
        db.execute('INSERT INTO detail_records VALUES (?,?,?,?,?)',(kind,str(key),item.get('act_id'),item.get('run_id'),json.dumps(item)))
    for table,kind,idkey in [('acts','act','act_id'),('verdicts','verdict','act_id'),('readings','reading','reading_id'),('duties','duty','duty_id'),('claims','claim','obligation_id')]:
        for row in list(db.execute('SELECT * FROM '+table)):
            item=dict(row)
            for field in ('ab','needs_review','counts_as_ab','is_new_here','text_truncated'):
                if field in item and item[field] is not None:item[field]=bool(item[field])
            if kind=='verdict':item.update(reason='Oorspronkelijke façade-motivering für deze act.',n_ab_obligations=0)
            if kind=='duty':
                item.update(canonical_quote={10:'Uniek negatief tegenoordeel',30:'alpha over de overheid',31:'omega voor de onderneming'}[item[idkey]],quote_norm='same' if item[idkey]==10 else str(item[idkey]),n_claims=1)
            if kind=='claim':
                item.update(quote_norm='same' if item[idkey]==101 else str(item[idkey]),reading_id=11 if item['run_id']==1 else {1:12,3:32}[item['act_id']],ab_reason='AB-redenering van lezer',io_reason='IO-redenering van lezer',admin_actions=['AH-1'],data_items=['een veld'],rule_reason='duty_origin=restates_elsewhere',duty_origin='restates_elsewhere')
                if item[idkey] in (301,302):item['counts_as_ab']=True
            if kind=='reading':item['error']='leesfout' if item['failed'] else None
            key=f"{item['act_id']}:{item['run_id']}" if kind=='verdict' else item[idkey]
            add(kind,key,item)
    add('duty',11,dict(duty_id=11,act_id=1,run_id=1,canonical_quote='oud',quote_norm='same',n_claims=1,n_ab_claims=1,status='accepted'))
    for rid,duty_id,quote in [(1,10,None),(2,None,'same'),(3,11,'same')]:
        add('review',rid,dict(decision_id=rid,act_id=1,duty_id=duty_id,quote_norm=quote,reviewer='llm_judge:test',decided_at='2026-01-01',decision='correct',corrected={'counts_as_ab':True},note='Bestaande correctie'))
    for kind,key,item in [('io_type','IO-x',dict(io_id='IO-x',name_short='Bronnaam',description='Oorspronkelijke definitie')),
                          ('cost_category','1.1',dict(code='1.1',name='Bronkost')),
                          ('admin_action','AH-1',dict(aa_id='AH-1',action_en='Checking',std_minutes='3.5'))]:add(kind,key,item)
    for aid in range(1,6):
        body='Voorwoord Uniek negatief tegenoordeel alpha over de overheid omega voor de onderneming.'
        add('text_metadata',aid,dict(act_id=aid,n_articles=1,disposition='to_llm',raw_hash=content_hash(body),llm_hash=content_hash(body),raw_chars=len(body),llm_chars=len(body)))
    db.commit();db.close()
    store.manifest['details_available']=True
    for run in store.manifest['runs']:run['models']=[{'model':'reader','role':'primary'}]
    provider=MagicMock()
    provider.get.return_value={'available':True,'text':{'raw_text':body,'llm_text':body},'provenance':{'origin':'test','content_matches_snapshot':True}}
    return cfg,store,DetailRepository(store,provider),provider


class DetailTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.cfg,self.store,self.repo,self.provider=detail_fixture(self.temp.name)

    def test_detail_does_not_load_text_and_keeps_verdict_and_claims(self):
        d=self.repo.get(1)
        self.provider.get.assert_not_called()
        self.assertFalse(d['verdict']['ab'])
        self.assertFalse(d['duties'][0]['claims'][0]['counts_as_ab'])
        self.assertEqual(d['explanation']['ab_duties'],1)
        self.assertTrue(d['explanation']['notes'])
        self.assertEqual(d['duties'][0]['claims'][0]['ab_reason'],'AB-redenering van lezer')
        self.assertEqual(d['duties'][0]['claims'][0]['action_details'][0]['std_minutes'],'3.5')

    def test_unknown_no_candidates_and_historical_run(self):
        self.assertIn('onbekend',self.repo.get(2)['explanation']['summary'])
        self.assertIn('geen kandidaatclaims',self.repo.get(5)['explanation']['summary'])
        self.assertEqual(self.repo.get(1,1)['run_id'],1)
        self.assertIsNone(self.repo.get(1,999))

    def test_amended_links_use_exact_numac_not_guessed_titles(self):
        readings=[{'reading_id':1,'model_slug':'reader','amended_acts':['VLCODEX-7',{'numac':'2025000001'},'X2025000001Y','gelijkende titel']}]
        result=amended_links(readings,{'VLCODEX-7':7,'2025000001':1})
        self.assertEqual(result[0]['links'],[{'numac':'VLCODEX-7','act_id':7}])
        self.assertEqual(result[1]['links'],[{'numac':'2025000001','act_id':1}])
        self.assertEqual(result[2]['links'],[]);self.assertEqual(result[3]['links'],[])

    def test_reviews_are_not_reapplied_and_ambiguous_quotes_are_labelled(self):
        d=self.repo.get(1)
        self.assertFalse(d['verdict']['ab'])
        reviews={r['decision_id']:r for r in d['reviews']}
        self.assertTrue(reviews[1]['association']['current_by_duty_id'])
        self.assertTrue(reviews[2]['association']['ambiguous'])
        self.assertEqual(reviews[2]['association']['run_ids'],[1,2])
        self.assertNotIn(3,{r['decision_id'] for r in d['duties'][0]['reviews']})

    def test_text_load_is_explicit_and_export_keeps_all_fields(self):
        d=self.repo.get(1);t=self.repo.text(1)
        self.provider.get.assert_called_once()
        self.assertTrue(t['available']);self.assertGreater(t['matched_occurrences'],0)
        md=markdown_export(d,t).decode('utf-8')
        self.assertIn('Oorspronkelijke façade-motivering für deze act.',md)
        self.assertIn('AB-redenering van lezer',md)
        self.assertIn('counts_as_ab',md)
        self.assertIn('same',md)
        pdf=pdf_export(d,t)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        from io import BytesIO
        from pypdf import PdfReader
        extracted='\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
        self.assertIn('façade',extracted);self.assertIn('für',extracted)


class HighlightTests(unittest.TestCase):
    def test_overlap_whitespace_repetition_and_unicode_offsets(self):
        text='😊 alpha\n beta gamma. alpha beta gamma.'
        detail={'duties':[{'duty_id':1,'n_ab_claims':1,'canonical_quote':'alpha beta','claims':[]}],
                'claims':[{'obligation_id':2,'counts_as_ab':True,'quote':'beta gamma','linked_duty_ids':[2],'io_id':'IO-02'}]}
        result=highlight(text,detail)
        self.assertEqual(result['matched_occurrences'],4)
        self.assertTrue(any(len(s['targets'])==2 for s in result['segments']))
        for s in result['segments']:
            self.assertNotIn('😊',text[s['start']:s['end']])
        self.assertEqual(result['unmatched'],[])
        detail['claims'][0]['quote']='niet aanwezig'
        self.assertTrue(highlight(text,detail)['unmatched'])


class TextVersionTests(unittest.TestCase):
    def test_wrong_live_version_is_not_displayed(self):
        with tempfile.TemporaryDirectory() as folder:
            p=DetailTextProvider(None,Path(folder)/'cache',Path(folder)/'missing.sqlite')
            metadata={'act_id':1,'raw_hash':content_hash('oud'),'llm_hash':content_hash('oud')}
            with patch('dashboard.data.detail_text.DashboardData') as data:
                data.return_value.act_text.return_value={'text':{'raw_text':'nieuw','llm_text':'nieuw'},'source':{}}
                result=p.get(metadata)
            self.assertFalse(result['available']);self.assertIn('gewijzigd',result['message'])

    def test_matching_local_text_needs_no_live_connection_and_cache_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            legacy=Path(folder)/'source.sqlite';db=sqlite3.connect(legacy)
            db.execute('CREATE TABLE act_text(act_id INTEGER,raw_text TEXT,llm_text TEXT)')
            db.execute('INSERT INTO act_text VALUES (1,?,?)',('bron','bron'));db.commit();db.close()
            provider=DetailTextProvider(None,Path(folder)/'cache',legacy)
            metadata={'act_id':1,'raw_hash':content_hash('bron'),'llm_hash':content_hash('bron')}
            with patch('dashboard.data.detail_text.DashboardData',side_effect=AssertionError('geen live opvraag')):
                self.assertTrue(provider.get(metadata)['available'])
                self.assertTrue(provider.get(metadata)['available'])
            cache=next((Path(folder)/'cache').glob('*.json'));cache.write_text('{}')
            with self.assertRaises(CacheError):provider.get(metadata)


class DetailHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();_,store,detail,_=detail_fixture(cls.temp.name)
        handler=type('DetailTestHandler',(ActListHandler,),{'store':store,'detail':detail})
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()

    def test_detail_text_markdown_and_pdf_routes(self):
        for path,mime in [('/api/act/1','application/json'),('/api/act/1/text','application/json'),('/api/act/1/export.md','text/markdown'),('/api/act/1/export.pdf','application/pdf'),('/detail.js','text/javascript'),('/detail.css','text/css')]:
            with urlopen(self.url+path) as response:self.assertIn(mime,response.headers['Content-Type'])
        for path,code in [('/api/act/999',404),('/api/act/1?run_id=999',404),('/api/act/1/text?variant=bad',400)]:
            with self.assertRaises(HTTPError) as caught:urlopen(self.url+path)
            self.assertEqual(caught.exception.code,code)


if __name__=='__main__':unittest.main()
