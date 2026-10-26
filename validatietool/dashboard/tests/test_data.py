from contextlib import contextmanager
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import uuid

import psycopg2

from dashboard.data.cache import CacheError, FORMAT_VERSION, SnapshotCache, query_revision, selection_key
from dashboard.data.config import Settings
from dashboard.data.connection import DataSourceError, ReadSession, read_session
from dashboard.data.repository import DashboardData
from dashboard.logic.metrics import VerificationError, compare_metrics, derive
from dashboard.logic.selection import Selection


def settings():
    return Settings(host='private-host', user='private-user', password='secret-password')


def sample():
    register = {'acts':3, 'acts_ab':1, 'acts_no_ab':1, 'acts_unknown':1, 'duties':3,
                'duties_ab':2, 'duties_accepted':1, 'duties_needs_review':2,
                'acts_read':2, 'acts_with_accepted_duty':1}
    corpus = {'corpus_rows':3, 'corpus_acts':3, 'corpus_missing_numac':0, 'classifier_selected':2}
    d = date(2020, 1, 1)
    acts = [dict(numac='a',pub_date=d,ab=False,ab_scope='business',run_id=2,read_success=True,accepted=True),
            dict(numac='b',pub_date=d,ab=True,ab_scope='citizen',run_id=3,read_success=True,accepted=False),
            dict(numac='c',pub_date=d,ab=None,ab_scope=None,run_id=4,read_success=False,accepted=False)]
    laws = [dict(numac=n,pub_date_iso=d,classifier_selected=selected) for n,selected in [('a',True),('b',True),('d',False)]]
    return register, corpus, acts, laws


class SelectionAndConfigTests(unittest.TestCase):
    def test_inclusive_year_bounds_and_invalid_selection(self):
        self.assertEqual(Selection(year_from=2020,year_to=2021).parameters()['date_until'],date(2022,1,1))
        for kwargs in ({'run_id':0},{'run_id':'1 OR TRUE'},{'year_from':2022,'year_to':2021}):
            with self.assertRaises(ValueError):
                Selection(**kwargs)

    def test_explicit_credentials_ignore_os_username_and_do_not_leak(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'.env'
            path.write_text('username=old\nuser=correct\nuser=wrong\nhost=private\npassword=secret # note\n',encoding='utf-8')
            cfg = Settings.load(path,{'USERNAME':'windows-account','USER':'shell-account'})
            self.assertEqual(cfg.user,'correct')
            self.assertEqual(cfg.password,'secret')
            self.assertIn('USER',cfg.duplicate_keys)
            path.write_text(path.read_text()+'AB_DB_USER="explicit"\n',encoding='utf-8')
            self.assertEqual(Settings.load(path,{}).user,'explicit')
            self.assertEqual(Settings.load(path,{'AB_DB_USER':'process-user'}).user,'process-user')
            self.assertNotIn('secret',repr(cfg))
            self.assertNotIn('correct',repr(cfg))


class MetricTests(unittest.TestCase):
    def test_verdict_is_not_replaced_by_claims_or_accepted_status(self):
        register,corpus,acts,laws = sample()
        cohort,scopes = derive(register,corpus,acts,laws)
        self.assertEqual(cohort['classifier_ab'],1)
        self.assertEqual(cohort['classifier_ab_with_accepted'],0)
        self.assertEqual(scopes,[{'scope':'citizen','acts':1,'share_of_ab_acts':1.0}])
        self.assertEqual(register['acts_unknown'],1)
        self.assertEqual(cohort['register_outside_corpus'],1)

    def test_duplicate_corpus_and_date_mismatch_block_publication(self):
        register,corpus,acts,laws = sample()
        for changed in (laws+[laws[0]], [dict(laws[0],pub_date_iso=date(2021,1,1)),*laws[1:]]):
            with self.assertRaises(VerificationError):
                derive(register,corpus,acts,changed)

    def test_empty_selection_has_no_invented_zero_percentage(self):
        r,c,_,_=sample()
        r={key:0 for key in r}; c={key:0 for key in c}
        cohort,scopes=derive(r,c,[],[])
        self.assertIsNone(cohort['detected_ab_share_of_corpus'])
        self.assertEqual(scopes,[])

    def test_independent_query_difference_is_fatal(self):
        with self.assertRaises(VerificationError):
            compare_metrics({'acts':3},{'acts':4},'test')


class SourceSafetyTests(unittest.TestCase):
    def test_connection_is_readonly_and_closed_on_query_error(self):
        con=MagicMock()
        with patch('dashboard.data.connection.psycopg2.connect',return_value=con) as connect, \
             patch('dashboard.data.connection.ReadSession',return_value=object()):
            with self.assertRaises(DataSourceError) as caught:
                with read_session(settings(),'register'):
                    raise psycopg2.OperationalError('host=private user=private password=secret-password')
            con.set_session.assert_called_once_with(readonly=True,isolation_level='REPEATABLE READ',autocommit=False)
            self.assertIn('default_transaction_read_only=on',connect.call_args.kwargs['options'])
            con.rollback.assert_called_once()
            con.close.assert_called_once()
            self.assertNotIn('secret-password',str(caught.exception))
            self.assertNotIn('private',str(caught.exception))

    def test_session_rejects_unverified_readonly_and_unknown_query(self):
        con=MagicMock()
        cur=con.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value=('db',None,'off','repeatable read','30s')
        with self.assertRaises(DataSourceError):
            ReadSession(con)
        session=object.__new__(ReadSession)
        with self.assertRaises(ValueError):
            session.fetch('../../.env')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache=SnapshotCache(self.temp.name)
        self.selection=Selection()
        self.key=selection_key(settings(),self.selection)

    def payload(self):
        return {'snapshot_id':uuid.uuid4().hex,'format_version':FORMAT_VERSION,'cache_key':self.key,
                'query_revision':query_revision(),'verified':True,'register':{'acts':3}}

    def test_cache_key_separates_run_period_and_source(self):
        keys={self.key,selection_key(settings(),Selection(run_id=2)),
              selection_key(settings(),Selection(year_from=2020)),
              selection_key(Settings(host='other',user='u',password='p'),self.selection)}
        self.assertEqual(len(keys),4)

    def test_cached_read_opens_no_source_and_corruption_is_rejected(self):
        payload=self.payload();path=self.cache.publish(self.key,payload)
        with patch('dashboard.data.repository.read_session',side_effect=AssertionError('geen live toegang')):
            self.assertEqual(DashboardData(settings(),self.cache).snapshot(),payload)
        data=json.loads(path.read_text(encoding='utf-8'))
        data['snapshot']['register']['acts']=99
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(CacheError):
            self.cache.load(self.key)

    def test_failed_refresh_keeps_complete_snapshot(self):
        payload=self.payload();self.cache.publish(self.key,payload)
        data=DashboardData(settings(),self.cache)
        with patch('dashboard.data.repository.read_session',side_effect=DataSourceError('geen connecties')):
            with self.assertRaises(DataSourceError):
                data.snapshot(refresh=True)
        self.assertEqual(data.snapshot()['snapshot_id'],payload['snapshot_id'])

    def test_sources_are_sequential_and_refresh_does_not_load_text(self):
        register,corpus,acts,laws=sample();events=[];queries=[]
        @contextmanager
        def fake_session(cfg,source):
            events.append('open '+source)
            session=MagicMock()
            session.metadata={'database':source,'snapshot_utc':'2026-10-21T10:00:00+00:00',
                              'readonly':True,'isolation':'repeatable read','statement_timeout':'30s'}
            values={'register_metrics':[register], 'register_control':[register], 'register_facts':acts,
                    'run_catalog':[], 'corpus_metrics':[corpus], 'corpus_control':[corpus],
                    'corpus_facts':laws,'eu_catalog':[]}
            def fetch(name,params=None):
                queries.append(name);return values[name]
            session.fetch.side_effect=fetch
            yield session
            events.append('close '+source)
        with patch('dashboard.data.repository.read_session',fake_session):
            result=DashboardData(settings(),self.cache).snapshot(refresh=True)
        self.assertEqual(events,['open register','close register','open corpus','close corpus'])
        self.assertNotIn('act_text',queries)
        self.assertNotIn('eu_text',queries)
        self.assertTrue(result['verified'])


if __name__ == '__main__':
    unittest.main()
