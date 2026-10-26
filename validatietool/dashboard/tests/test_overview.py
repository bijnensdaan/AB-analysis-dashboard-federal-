"""Gedeelde filtersemantiek, KPI-eenheden, corpusnoemers en gecontroleerde cache."""
from contextlib import contextmanager
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dashboard.tests.test_detail import detail_fixture
from dashboard.data.actlist_snapshot import file_hash
from dashboard.data.overview import OverviewRepository
from dashboard.data.overview_corpus import build_corpus,load_corpus,folder_for
from dashboard.logic.act_filters import ActFilters
from dashboard.logic.metrics import VerificationError
from dashboard.data.cache import CacheError


class CorpusCursor:
    def __init__(self,rows):self.rows=list(rows)
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,query):
        assert 'embedding' not in query.lower().split('select',1)[-1] # no large fields
    def fetchmany(self,n):rows=self.rows[:n];self.rows=self.rows[n:];return rows


class FakeSource:
    metadata={'snapshot_utc':'2026-10-21T13:00:00+00:00','readonly':True}
    def __init__(self,rows):self.rows=rows;self.connection=self
    def cursor(self,**kwargs):return CorpusCursor(self.rows)
    def fetch(self,name,params):
        assert name=='corpus_control'
        dates=[r[1] for r in self.rows if r[1]]
        return [dict(corpus_rows=len(self.rows),corpus_acts=len({r[0] for r in self.rows}),corpus_missing_numac=0,
                     classifier_selected=sum(bool(r[4]) for r in self.rows),corpus_date_from=min(dates) if dates else None,corpus_date_to=max(dates) if dates else None)]


class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.cfg,self.store,_,_=detail_fixture(self.temp.name)
        self.store.manifest['sqlite_sha256']=file_hash(self.store.path)
        self.root=Path(self.temp.name)/'corpus'
        self.rows=[('NUM-1',date(2020,1,1),'nl','besluit',True),('NUM-2',date(2020,1,1),'nl','besluit',False),('NUM-3',date(2020,1,1),'nl','besluit',True),('CORPUS-EXTRA',date(2020,1,1),'nl','besluit',True)]
        self.corpus=self.build(self.rows)
        self.repo=OverviewRepository(self.store,self.corpus)

    def build(self,rows):
        @contextmanager
        def session(settings,source):
            self.assertEqual(source,'corpus');yield FakeSource(rows)
        with patch('dashboard.data.overview_corpus.read_session',session):
            return build_corpus(self.cfg,self.store,self.root)

    def test_units_verdicts_scopes_and_negative_act_with_positive_duty(self):
        d=self.repo.get();r=d['register']
        self.assertEqual([r[k] for k in ('acts','acts_ab','acts_no_ab','acts_unknown','read_success','read_failed')],[4,1,2,1,3,1])
        self.assertEqual([r[k] for k in ('duties','ab_duties','duties_accepted','duties_needs_review','ab_duties_accepted','ab_duties_needs_review')],[3,3,2,1,2,1])
        self.assertEqual(d['scopes'],[{'scope':'citizen','acts':1,'share_of_ab_acts':1}])
        no=self.repo.get(ActFilters(verdict='no'))['register']
        self.assertEqual((no['acts_ab'],no['ab_duties']),(0,1))

    def test_same_claim_same_duty_and_loose_claims(self):
        empty=self.repo.get(ActFilters(io_id='IO-a',duty_bearer_kind='private_business'))
        self.assertEqual(empty['register']['acts'],0)
        self.assertEqual(self.repo.get(ActFilters(io_id='IO-b',duty_status='accepted'))['register']['acts'],0)
        self.assertEqual(self.repo.get(ActFilters(io_id='IO-b',duty_status='needs_review'))['register']['duties'],1)
        loose=self.repo.get(ActFilters(io_id='IO-loose'))['register']
        self.assertEqual((loose['acts'],loose['acts_ab'],loose['duties']),(1,1,0))

    def test_unknown_empty_and_zero_denominator_are_distinct(self):
        unknown=self.repo.get(ActFilters(verdict='unknown'))
        self.assertEqual((unknown['register']['acts_unknown'],unknown['register']['acts_no_ab']),(1,0))
        self.assertEqual(unknown['scopes'],[])
        empty=self.repo.get(ActFilters(year_from=1900,year_to=1900))
        self.assertEqual(empty['register']['acts'],0)
        self.assertEqual(empty['corpus']['acts'],0)
        self.assertTrue(empty['corpus']['available'])
        self.assertEqual(empty['scopes'],[])

    def test_corpus_context_and_unsupported_filters_not_a_false_denominator(self):
        d=self.repo.get()
        self.assertEqual((d['corpus']['acts'],d['corpus']['classifier_selected']),(4,3))
        self.assertEqual(d['classifier_cohort']['register_outside_corpus'],1)
        self.assertEqual(d['classifier_cohort']['register_in_classifier'],2)
        self.assertEqual(d['classifier_cohort']['classifier_ab'],1)
        filtered=self.repo.get(ActFilters(io_id='IO-a'))
        self.assertFalse(filtered['corpus']['available'])
        self.assertIsNone(filtered['corpus']['acts'])
        self.assertEqual(filtered['corpus']['period_context']['acts'],4)
        self.assertEqual(filtered['corpus']['unsupported_filters'],['io_id'])
        self.assertTrue(self.repo.get(ActFilters(run_id=1))['corpus']['available'])
        missing=OverviewRepository(self.store).get()
        self.assertFalse(missing['corpus']['available'])
        self.assertEqual(missing['register']['acts'],4)

    def test_cached_selection_ignores_presentation_but_not_filters(self):
        hits=self.repo._cached.cache_info().hits
        d=self.repo.get();d['register']['acts']=999
        again=self.repo.get(ActFilters(page=2,size=100,sort='title'))
        self.assertEqual(again['register']['acts'],4)
        self.assertEqual(self.repo._cached.cache_info().hits,hits+1)
        self.assertEqual(self.repo.get(ActFilters(run_id=1))['register']['acts'],1)
        with self.assertRaises(ValueError):self.repo.get(ActFilters(run_id=999))

    def test_corpus_snapshot_cache_needs_no_source_and_detects_corruption(self):
        before=file_hash(self.store.path)
        with patch('dashboard.data.overview_corpus.read_session',side_effect=AssertionError('No source access')):
            loaded=load_corpus(self.cfg,self.store,self.root)
            self.assertEqual(loaded[1]['date_mismatches'],0)
            self.repo.get()
        self.assertEqual(file_hash(self.store.path),before)
        self.corpus[0].write_bytes(self.corpus[0].read_bytes()+b'changed')
        with self.assertRaises(CacheError):load_corpus(self.cfg,self.store,self.root)

    def test_failed_build_preserves_published_cache(self):
        pointer=folder_for(self.cfg,self.store,self.root)/'LATEST';before=pointer.read_text()
        bad=[('NUM-1',date(2021,1,1),'nl','besluit',True)]
        with self.assertRaises(VerificationError):self.build(bad)
        self.assertEqual(pointer.read_text(),before)
        with self.assertRaises(sqlite3.IntegrityError):self.build([self.rows[0],self.rows[0]])
        self.assertEqual(pointer.read_text(),before)
        self.assertEqual(list(pointer.parent.glob('*.building.sqlite')),[])


if __name__=='__main__':unittest.main()
