"""Actlijstsemantiek, snapshotveiligheid en HTTP-contract; geen bronmutaties."""
from pathlib import Path
import json
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from unittest.mock import patch

from dashboard.data.actlist import ActListStore
from dashboard.data.actlist_snapshot import SQL,VERSION,build_snapshot,cache_folder,file_hash,revision,load_snapshot
from dashboard.data.config import Settings
from dashboard.data.cache import CacheError
from dashboard.data.connection import DataSourceError
from dashboard.logic.act_filters import ActFilters,SORT_FIELDS,norm
from dashboard.ui.actlist_server import ActListHandler,ThreadingHTTPServer


def fixture(root):
    cfg=Settings(host='test',user='test',password='test')
    folder=cache_folder(cfg,root);folder.mkdir(parents=True)
    identity='a'*32;path=folder/(identity+'.sqlite')
    db=sqlite3.connect(path);db.executescript((SQL/'schema.sql').read_text(encoding='utf-8'))
    for act_id,title in [(1,'Besluit met tegenoordeel'),(2,'Onbekend verdict'),(3,'Twee verschillende lezersclaims'),(4,'Nog niet gelezen'),(5,'Titel zonder claims café')]:
        row=[act_id,'NUM-'+str(act_id),title,'2020-01-01','besluit','federaal','entiteit','nl','https://example.org/'+str(act_id),norm('NUM-'+str(act_id)),norm(title)]
        db.execute('INSERT INTO acts VALUES ('+','.join('?' for _ in row)+')',row)
        db.execute('INSERT INTO text_metadata VALUES (?,?,?)',(act_id,32767 if act_id==1 else 100,'to_llm'))
    db.executemany('INSERT INTO verdicts VALUES (?,?,?,?,?)',[(1,1,1,'business',0),(1,2,0,'business',1),(2,2,None,None,1),(3,2,1,'citizen',1),(4,2,0,None,0),(5,2,0,None,0)])
    db.executemany('INSERT INTO readings VALUES (?,?,?,?,?,?)',[(11,1,1,'old',0,0),(12,1,2,'reader',0,0),(22,2,2,'reader',0,1),(32,3,2,'reader',0,0),(52,5,2,'reader',0,0)])
    db.executemany('INSERT INTO duties VALUES (?,?,?,?,?)',[(10,1,2,'accepted',1),(30,3,2,'accepted',1),(31,3,2,'needs_review',1)])
    claims=[(100,1,1,'alleen historisch citaat','IO-old','private_business'),
            (101,1,2,'Uniek negatief tegenoordeel over rapportage','IO-x','private_business'),
            (301,3,2,'alpha over de overheid','IO-a','public_body'),
            (302,3,2,'omega voor de onderneming','IO-b','private_business'),
            (303,3,2,'Losse claim zonder duty, zeldzaam woord','IO-loose','private_business')]
    for claim_id,act_id,run_id,quote,io,bearer in claims:
        values=[claim_id,act_id,run_id,quote,io,bearer,'government','business','annual','1.1','national_act',1,0,norm(quote)]
        db.execute('INSERT INTO claims VALUES ('+','.join('?' for _ in values)+')',values)
    db.executemany('INSERT INTO duty_claims VALUES (?,?)',[(10,101),(30,301),(31,302)])
    db.execute("INSERT INTO io_types VALUES ('IO-x','Type uit bron')")
    db.execute("INSERT INTO cost_categories VALUES ('1.1','Administratieve last')")
    db.executescript((SQL/'indexes.sql').read_text(encoding='utf-8'));db.close()
    manifest={'version':VERSION,'snapshot_id':identity,'query_revision':revision(),'verified':True,
              'source':{'snapshot_utc':'2026-10-21T12:00:00+00:00','readonly':True},
              'runs':[{'run_id':1,'started_at':'2026-08-01T00:00:00+00:00'},{'run_id':2,'started_at':'2026-09-01T00:00:00+00:00'}],
              'control':{'acts':5},'sqlite_sha256':file_hash(path)}
    (folder/(identity+'.json')).write_text(json.dumps(manifest),encoding='utf-8')
    (folder/'LATEST').write_text(identity,encoding='utf-8')
    return cfg,ActListStore(path,manifest)


class ActListTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.cfg,self.store=fixture(self.temp.name)

    def ids(self,**kwargs):
        return {row['act_id'] for row in self.store.list(ActFilters(**kwargs))['items']}

    def test_latest_run_excludes_history_and_keeps_unknown_distinct(self):
        self.assertEqual(self.ids(),{1,2,3,5})
        self.assertEqual(self.ids(verdict='unknown'),{2})
        self.assertEqual(self.ids(verdict='no'),{1,5})
        self.assertEqual(self.ids(q='historisch',q_in='quote'),set())
        self.assertEqual(self.ids(run_id=1,q='historisch',q_in='quote'),{1})

    def test_negative_and_unlinked_claims_are_searchable(self):
        self.assertEqual(self.ids(q='negatief tegenoordeel',q_in='quote'),{1})
        self.assertEqual(self.ids(q='Losse claim zonder duty',q_in='quote'),{3})
        row=self.store.list(ActFilters(q='negatief',q_in='quote'))['items'][0]
        self.assertFalse(row['ab'])
        self.assertEqual(row['ab_duties'],1)

    def test_claim_filters_do_not_combine_different_claims(self):
        self.assertEqual(self.ids(io_id='IO-a',duty_bearer_kind='private_business'),set())
        self.assertEqual(self.ids(io_id='IO-b',duty_bearer_kind='private_business'),{3})
        self.assertEqual(self.ids(q='alpha omega',q_in='quote'),set())

    def test_status_and_claim_must_match_same_duty(self):
        self.assertEqual(self.ids(io_id='IO-b',duty_status='accepted'),set())
        self.assertEqual(self.ids(io_id='IO-b',duty_status='needs_review'),{3})
        self.assertEqual(self.ids(io_id='IO-loose'),{3})
        self.assertEqual(self.ids(io_id='IO-loose',duty_status='accepted'),set())

    def test_numac_title_unicode_empty_and_literal_search(self):
        self.assertEqual(self.ids(q='NUM-2',q_in='numac'),{2})
        self.assertEqual(self.ids(q='CAFÉ',q_in='title'),{5})
        self.assertEqual(self.ids(q='Titel zonder claims',q_in='all'),{5})
        self.assertEqual(self.ids(q='   '),{1,2,3,5})
        self.assertEqual(self.ids(q="%' OR 1=1 --"),set())
        title_hit=self.store.list(ActFilters(q='Besluit'))['items'][0]
        self.assertIsNone(title_hit['matched_quote'])
        mixed_hit=self.store.list(ActFilters(q='Twee alpha'))['items'][0]
        self.assertIn('alpha',mixed_hit['matched_quote'])

    def test_pagination_and_every_sort_column(self):
        for field in SORT_FIELDS:
            for direction in ('asc','desc'):
                first=self.store.list(ActFilters(sort=field,direction=direction,size=2))
                last=self.store.list(ActFilters(sort=field,direction=direction,size=2,page=999))
                self.assertEqual(last['page'],2)
                self.assertEqual({r['act_id'] for r in first['items']+last['items']},{1,2,3,5})

    def test_pasted_numac_label(self):
        with sqlite3.connect(self.store.path) as db:
            db.execute('UPDATE acts SET numac=?,numac_search=? WHERE act_id=2',('2022042769','2022042769'))
        db.close()
        for field in ('all','numac'):
            for query in ('2022042769','NUMAC 2022042769','numac: 2022042769',"'NUMAC 2022042769'"):
                self.assertEqual(self.ids(q=query,q_in=field),{2})
        self.assertEqual(self.ids(q='NUMAC 2022042769',q_in='quote'),set())
        self.assertEqual(self.ids(q='NUMAC 2022042769',q_in='title'),set())
        self.assertEqual(self.ids(q='NUMAC 2022042769 extra'),set())

    def test_quality_filters_and_empty_selection(self):
        self.assertEqual(self.ids(truncated='yes'),{1})
        self.assertEqual(self.ids(year_from=2021),set())
        self.assertEqual(self.store.list(ActFilters(verdict='unknown'))['summary']['read_failed'],1)

    def test_cache_is_readonly_and_failed_refresh_preserves_pointer(self):
        with self.store.connect() as db:self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
        before=(cache_folder(self.cfg,self.temp.name)/'LATEST').read_bytes()
        with patch('dashboard.data.actlist_snapshot.read_session',side_effect=DataSourceError('geen slots')):
            with self.assertRaises(DataSourceError):build_snapshot(self.cfg,self.temp.name)
        self.assertEqual((cache_folder(self.cfg,self.temp.name)/'LATEST').read_bytes(),before)
        loaded=ActListStore(*load_snapshot(self.cfg,self.temp.name))
        self.assertEqual(loaded.list()['summary']['acts'],4)

    def test_corrupt_cache_is_rejected(self):
        with self.store.path.open('ab') as output:output.write(b'corruption')
        with self.assertRaises(CacheError):load_snapshot(self.cfg,self.temp.name)

    def test_invalid_parameters(self):
        for params in ({'page':'0'},{'size':'101'},{'sort':'title; DROP TABLE acts'},{'surprise':'1'},{'year_from':'2022','year_to':'2020'}):
            with self.assertRaises(ValueError):ActFilters.from_params(params)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        _,cls.store=fixture(cls.temp.name)
        handler=type('TestActListHandler',(ActListHandler,),{'store':cls.store})
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()

    def test_api_static_pages_and_selection(self):
        for path in ('/','/style.css','/app.js','/api/meta'):
            with urlopen(self.url+path) as response:
                self.assertEqual(response.status,200)
                self.assertIn("default-src 'self'",response.headers['Content-Security-Policy'])
        with urlopen(self.url+'/api/acts?'+urlencode({'verdict':'unknown'})) as response:
            data=json.load(response)
            self.assertEqual(data['summary']['acts'],1)
            self.assertIsNone(data['items'][0]['ab'])

    def test_bad_input_private_files_and_write_methods(self):
        for path,expected in [('/.env',404),('/../.env',404),('/api/acts?size=1000',400),('/api/acts?page=1&page=2',400),('/api/acts?run_id=999',400)]:
            with self.assertRaises(HTTPError) as caught:urlopen(self.url+path)
            self.assertEqual(caught.exception.code,expected)
        for method in ('POST','PUT','PATCH','DELETE'):
            with self.assertRaises(HTTPError) as caught:urlopen(Request(self.url+'/api/acts',method=method))
            self.assertEqual(caught.exception.code,405)

    def test_refresh_does_not_reuse_stale_scripts_or_styles(self):
        for path in ('/','/detail.js','/detail.css'):
            request=Request(self.url+path,headers={'If-Modified-Since':'Wed, 01 Jan 2031 00:00:00 GMT'})
            with urlopen(request) as response:
                self.assertEqual(response.status,200)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                content=response.read().decode('utf-8')
                if path=='/':self.assertRegex(content,r'/detail\.js\?v=[0-9a-f]{16}')
        with urlopen(self.url+'/detail.js?v=oude-versie') as response:
            self.assertIn('function processing(d)',response.read().decode('utf-8'))


if __name__=='__main__':unittest.main()
