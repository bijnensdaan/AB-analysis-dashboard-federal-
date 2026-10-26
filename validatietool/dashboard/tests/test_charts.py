"""Unieke teleenheden, exacte drill-down, ketenbeperkingen, veilige exports."""
from contextlib import contextmanager
from dataclasses import replace
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError
from PIL import Image

from dashboard.tests.test_detail import detail_fixture
from dashboard.tests.test_overview import FakeSource
from dashboard.data.actlist import ActListStore
from dashboard.data.actlist_snapshot import file_hash
from dashboard.data.analysis_projection import build_projection,load_projection
from dashboard.data.overview_corpus import build_corpus
from dashboard.data.overview import OverviewRepository
from dashboard.data.charts import ChartRepository,csv_export
from dashboard.data.detail import DetailRepository
from dashboard.data.cache import CacheError
from dashboard.logic.analysis import CHARTS,with_point,matching_steps
from dashboard.logic.act_filters import ActFilters
from dashboard.ui.actlist_server import ActListHandler,ThreadingHTTPServer


class ChartTests(unittest.TestCase):
    def setUp(self):
        from datetime import date
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        cfg,store,_,_=detail_fixture(self.temp.name);self.cfg=cfg
        db=sqlite3.connect(store.path)
        c=json.loads(db.execute("SELECT data FROM detail_records WHERE kind='claim' AND key='301'").fetchone()[0])
        row=list(db.execute('SELECT * FROM claims WHERE obligation_id=301').fetchone())
        # Twee extra beoordelingen van dezelfde duty, met andere IO/categorie.
        for cid in (304,305):
            copied={**c,'obligation_id':cid,'io_id':'IO-b','duty_bearer_kind':'private_business','data_items':['=SUM(1,2)','gemeenschappelijk veld']}
            db.execute('INSERT INTO detail_records VALUES (?,?,?,?,?)',('claim',str(cid),3,2,json.dumps(copied)))
            values=list(row);values[0]=cid;values[4]='IO-b';values[5]='private_business'
            db.execute('INSERT INTO claims VALUES ('+','.join('?' for _ in values)+')',values);db.execute('INSERT INTO duty_claims VALUES (?,?)',(30,cid))
        db.commit();db.close();store.manifest['sqlite_sha256']=file_hash(store.path)
        @contextmanager
        def session(settings,source):yield FakeSource([('NUM-1',date(2020,1,1),'nl','besluit',True),('NUM-3',date(2020,1,1),'nl','besluit',True),('EXTRA',date(2020,1,1),'nl','besluit',True)])
        with patch('dashboard.data.overview_corpus.read_session',session):self.corpus=build_corpus(cfg,store,Path(self.temp.name)/'corpus')
        self.projection_root=Path(self.temp.name)/'projection';self.projection=build_projection(store,self.corpus,self.projection_root)
        self.store=ActListStore(store.path,store.manifest,analysis_root=self.projection_root)
        self.overview=OverviewRepository(self.store,self.corpus)
        self.repo=ChartRepository(self.store,self.overview,DetailRepository(self.store))

    def row(self,chart,x,y=None):return next(r for r in self.repo.get(chart,top=50)['rows'] if r['x']==x and r['y']==y)

    def test_memberships_do_not_count_claims_as_duties(self):
        row=self.row('io','IO-b')
        self.assertEqual(row['value'],2) # 3 claims, slechts 2 duties.
        f=with_point(ActFilters(),'io',row['point_id']);summary=self.store.list(f)['summary']
        self.assertEqual((summary['acts'],summary['duties']),(1,2))
        self.assertEqual(self.overview.get(f)['register']['ab_duties'],2)
        self.assertGreater(sum(r['value'] for r in self.repo.get('io')['rows']),self.overview.get()['register']['ab_duties'])

    def test_multiple_chart_filters_require_same_original_claim(self):
        flow=self.row('flow','public_body','government');io=self.row('io','IO-b')
        f=with_point(with_point(ActFilters(),'flow',flow['point_id']),'io',io['point_id'])
        self.assertEqual(self.store.list(f)['summary']['acts'],0)
        self.assertEqual(self.overview.get(f)['register']['duties'],0)
        self.assertEqual(self.repo.get('frequency',f)['rows'],[])
        # Een globale claimfilter mag evenmin uit de andere lezer komen.
        self.assertEqual(self.store.list(replace(with_point(ActFilters(),'flow',flow['point_id']),io_id='IO-b'))['summary']['acts'],0)

    def test_every_point_drills_to_its_exact_register_counts(self):
        for chart in CHARTS:
            d=self.repo.get(chart,top=50)
            for row in d['rows']:
                if not row['drillable']:continue
                f=with_point(ActFilters(),chart,row['point_id']);summary=self.store.list(f)['summary']
                self.assertEqual(summary['acts'],row['register_acts'],(chart,row))
                if d['unit']=='duties':self.assertEqual(summary['duties'],row['value'],(chart,row))
            self.assertFalse(d['full_act_text_loaded'])

    def test_funnel_does_not_mix_units_or_accepted_outside_filter(self):
        d=self.repo.get('funnel');values=[r['value'] for r in d['rows']]
        self.assertEqual(values,[3,3,2,1,1])
        row=self.row('funnel','accepted')
        f=with_point(ActFilters(io_id='IO-b',duty_status='needs_review'),'funnel',row['point_id'])
        self.assertEqual(self.store.list(f)['summary']['acts'],0)
        self.assertFalse(self.repo.get('funnel',ActFilters(io_id='IO-b'))['available'])

    def test_unknown_no_data_and_corpus_share_not_zero_fill(self):
        empty=self.repo.get('io',ActFilters(verdict='unknown'))
        self.assertEqual(empty['rows'],[])
        rows=self.repo.get('ab_year',ActFilters(io_id='IO-b'))['rows']
        self.assertTrue(all(r['share'] is None for r in rows))
        self.assertTrue(any(r['value']>0 for r in rows if r['y']=='register'))

    def test_cache_integrity_and_source_immutability(self):
        before=file_hash(self.store.path)
        with patch('dashboard.data.connection.read_session',side_effect=AssertionError('no PostgreSQL')):
            self.repo.get('flow');self.repo.evidence('io',self.row('io','IO-b')['point_id'])
        self.assertEqual(before,file_hash(self.store.path))
        self.projection[0].write_bytes(self.projection[0].read_bytes()+b'changed')
        with self.assertRaises(CacheError):load_projection(self.store.manifest,root=self.projection_root)

    def test_svg_png_csv_and_empty_exports(self):
        svg=self.repo.image('flow')
        self.assertIn('data-point=',svg);self.assertIn('<title>',svg)
        self.assertNotIn('style=',svg);self.assertNotIn('<style',svg);self.assertNotIn('<script',svg)
        import xml.etree.ElementTree as ET
        heatmap=ET.fromstring(self.repo.image('level_io'))
        values=list(heatmap.iter('{http://www.w3.org/2000/svg}text'))
        self.assertTrue(values)
        self.assertTrue(all(e.get('pointer-events')=='none' for e in values))
        png=self.repo.image('io',format='png');self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        image=Image.open(io.BytesIO(png));image.verify()
        csv=csv_export(self.repo.get('data_items')).decode('utf-8-sig')
        self.assertIn("'=SUM(1,2)",csv)
        self.assertIn('register_source_utc',csv)
        self.assertIn('Geen gegevens',self.repo.image('io',ActFilters(verdict='unknown')))

    def test_complete_io_defaults_and_heatmap_counts_are_types_not_cells(self):
        complete=self.repo.get('level_io')
        types={r['y'] for r in complete['rows']}
        self.assertGreater(len(types),1)
        self.assertEqual(complete['top'],0)
        self.assertEqual(complete['total_categories'],len(types))
        self.assertFalse(complete['display']['limited'])
        partial=self.repo.get('level_io',top=1)
        self.assertEqual(len({r['y'] for r in partial['rows']}),1)
        self.assertTrue(partial['display']['limited'])
        self.assertEqual(partial['display']['points_total'],len(complete['rows']))
        self.assertEqual(partial['display']['total'],len(types))
        self.assertIn('IO-types',partial['display']['description'])
        self.assertGreater(len(self.repo.get('io')['rows']),1)
        with self.assertRaises(ValueError):self.repo.image('data_items',top=0)
        self.assertGreater(len(self.repo.get('data_items',top=0)['rows']),1)

    def test_candidate_chains_keep_non_ab_steps_and_do_not_claim_lineage(self):
        duties=[{'duty_id':1,'n_ab_claims':1},{'duty_id':2,'n_ab_claims':0}]
        claims=[{'obligation_id':11,'linked_duty_ids':[1],'duty_bearer':'burger','recipient':'Gemeente','data_items':['adres'],'quote':'adres aan gemeente'},
                {'obligation_id':12,'linked_duty_ids':[2],'duty_bearer':'gemeente','recipient':'centrale dienst','data_items':['adres'],'quote':'gemeente meldt adres'},
                {'obligation_id':13,'linked_duty_ids':[2],'duty_bearer':'Gemeente','recipient':'centrale dienst','data_items':['identiteit'],'quote':'andere lezer'}]
        flow=matching_steps(duties,claims)
        self.assertEqual(len(flow['candidates']),1)
        self.assertIsNone(flow['confirmed_chains'])
        self.assertFalse(flow['candidates'][0]['second']['duty_counts_as_ab'])
        self.assertEqual(flow['candidates'][0]['shared_data_items'],['adres'])
        self.assertEqual(len(flow['candidates'][0]['second']['sources']),2)
        same=matching_steps([duties[0]],[{**c,'linked_duty_ids':[1]} for c in claims])
        self.assertEqual(same['candidates'],[])

    def test_http_graph_exports_flow_and_validation(self):
        from urllib.parse import urlencode
        handler=type('ChartHandler',(ActListHandler,),{'store':self.store,'overview':self.overview,'detail':self.repo.detail,'charts':self.repo})
        server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/api/chart/io') as response:
                payload=json.load(response);self.assertIn('svg',payload);self.assertFalse(payload['full_act_text_loaded'])
                self.assertEqual(payload['top'],0)
                self.assertFalse(payload['display']['limited'])
            point=self.row('io','IO-b')['point_id']
            with urlopen(base+'/api/chart/io/evidence?'+urlencode({'point':point})) as response:
                self.assertEqual(json.load(response)['acts']['summary']['duties'],2)
            with urlopen(base+'/api/chart/io/export.png') as response:self.assertTrue(response.read().startswith(b'\x89PNG'))
            with urlopen(base+'/api/chart/io/export.csv') as response:self.assertIn('register_source_utc',response.read().decode('utf-8-sig'))
            with urlopen(base+'/api/chart/data_items/export.csv?top=0') as response:self.assertIn('register_source_utc',response.read().decode('utf-8-sig'))
            with urlopen(base+'/api/flow/act/3') as response:self.assertIsNone(json.load(response)['confirmed_chains'])
            for path in ('/api/chart/not_a_chart','/api/chart/io?top=51','/api/chart/data_items?top=0','/api/chart/data_items/export.png?top=0','/api/acts?chart_id=io&point_id=bad'):
                with self.assertRaises(HTTPError) as caught:urlopen(base+path)
                self.assertEqual(caught.exception.code,400);caught.exception.close()
        finally:server.shutdown();server.server_close();thread.join()

    def test_aborted_browser_request_does_not_become_a_server_error(self):
        handler=object.__new__(ActListHandler)
        handler.path='/api/meta';handler.store=self.store
        handler.overview=self.overview;handler.charts=self.repo
        with patch.object(handler,'send',side_effect=ConnectionAbortedError) as send:
            handler.do_GET()
            send.assert_called_once() # geen tweede poging om een 500-fout te sturen


if __name__=='__main__':unittest.main()
