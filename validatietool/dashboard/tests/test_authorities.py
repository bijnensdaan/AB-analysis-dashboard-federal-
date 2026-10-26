"""Hoofdingcontext, taal/historie, snapshotbinding en consistente orgaanfilters."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dashboard.logic.authorities import identify,REFERENCE
from dashboard.data.authority_mapping import build_mapping,load_mapping
from dashboard.data.actlist import ActListStore
from dashboard.data.actlist_snapshot import file_hash
from dashboard.data.detail import DetailRepository
from dashboard.data.cache import CacheError
from dashboard.logic.act_filters import ActFilters
from dashboard.tests.test_detail import detail_fixture
from dashboard.logic.detail_export import markdown_export


class AuthorityRecognitionTests(unittest.TestCase):
    def test_nl_fr_de_spelling_and_original_offsets(self):
        for heading in ['FEDERALE OVERHEIDSDIENST FINANCIEN','SERVICE PUBLIC FÉDÉRAL FINANCES','FÖDERALER ÖFFENTLICHER DIENST FINANZEN']:
            source='\n'+heading+'12. JANUARI 2020 - Besluit\nFILIP, Koning der Belgen'
            result=identify(source)
            self.assertEqual(result['orgaan'],'FOD Financiën')
            self.assertEqual(result['beleidsdomein'],'Financiën')
            for e in result['evidence']:self.assertEqual(source[e['start']:e['end']],e['text'])

    def test_historical_ministry_kept_separate(self):
        for heading in ['MINISTERIE VAN FINANCIËN','MINISTÈRE DES FINANCES','MINISTERIUM DER FINANZEN']:
            self.assertEqual(identify(heading+'\n12 mei 1998 - Besluit')['orgaan'],'Ministerie van Financiën')
        self.assertTrue(next(r for r in REFERENCE if r['id']=='ministerie_financien')['historical'])

    def test_regional_issuer_without_invented_domain(self):
        for heading in ['De Vlaamse Regering,Gelet op de wet','Le Gouvernement wallon,Vu la loi','Die Regierung der Deutschsprachigen Gemeinschaft,']:
            result=identify(heading)
            self.assertEqual(result['status'],'gekoppeld')
            self.assertEqual(result['beleidsdomein'],'Onbekend')
        self.assertEqual(identify('SERVICE PUBLIC DE WALLONIE\n12 mai 2020')['beleidsdomein'],'Onbekend')
        result=identify('SPW FINANCES\n12 mai 2020')
        self.assertEqual(result['orgaan'],'SPW Finances')
        self.assertEqual(result['beleidsdomein'],'Financiën')

    def test_names_in_body_title_report_or_signature_not_authority(self):
        samples=[
          'FILIP, Koning der BelgenArtikel 1.\nFEDERALE OVERHEIDSDIENST FINANCIEN\n12 mei 2000',
          'TekstArtikel 1. De FEDERALE OVERHEIDSDIENST FINANCIEN\n12 mei 2000',
          'VERSLAG AAN DE KONING\nFEDERALE OVERHEIDSDIENST FINANCIEN\n12 mei 2000',
          'De Minister van Financiën,Gelet op de wet',
          'Het Vlaams Parlement heeft aangenomen en Wij, Regering, bekrachtigen hetgeen volgt.',
          'MINISTERIE VAN BUITENLANDSE ZAKEN VAN DE REPUBLIEK SENEGAL\n12 mei 2000',
          'Titel: wijziging van de Federale Overheidsdienst Financiën in deze wet',
          'FEDERALE OVERHEIDSDIENST FINANCIEN is genoemd maar geen afzonderlijke hoofding',
        ]
        for source in samples:self.assertEqual(identify(source)['orgaan'],'Onbekend',source)

    def test_ambiguous_joint_heading_and_compound_translation(self):
        source='MINISTERIUM DER FINANZEN UND MINISTERIUM DER JUSTIZ5. MÄRZ 1952 - Gesetz'
        result=identify(source)
        self.assertEqual(result['status'],'meerdere_organen')
        self.assertEqual(len(result['evidence']),2)
        self.assertEqual(identify('De respectievelijk in bijlagen 1 tot 3 gevoegde teksten zijn de Duitse vertaling.\nFEDERALE OVERHEIDSDIENST FINANCIEN\n12 mei 2020')['status'],'samengestelde_publicatie')
        self.assertEqual(identify(None)['status'],'tekst_ontbreekt')
        self.assertEqual(identify('x'*4096+'FEDERALE OVERHEIDSDIENST FINANCIEN\n12 mei 2020')['orgaan'],'Onbekend')


class AuthorityMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        _,self.store,_,_=detail_fixture(self.temp.name)
        self.root=Path(self.temp.name)/'mapping'
        # Fixture metadata hashes stand for identical source versions; no DB access.
        with self.store.connect() as db:
            metadata=[json.loads(r[0]) for r in db.execute("SELECT data FROM detail_records WHERE kind='text_metadata'")]
        self.extract={'register_snapshot_id':self.store.manifest['snapshot_id'],'source':{'readonly':True,'snapshot_utc':'2026-10-21T00:00:00+00:00'},
          'rows':[dict(act_id=m['act_id'],numac='NUM-'+str(m['act_id']),raw_hash=m['raw_hash'],llm_hash=m['llm_hash'],prefix='FEDERALE OVERHEIDSDIENST FINANCIEN\n12 mei 2020' if m['act_id']==1 else 'De Vlaamse Regering,Gelet op de wet' if m['act_id']==3 else 'Artikel 1. Geen hoofding') for m in metadata]}

    def test_version_mismatch_and_duplicate_source_never_silently_linked(self):
        self.extract['rows'][0]['raw_hash']='andere inhoud'
        _,manifest,rows=build_mapping(self.store,self.extract,self.root)
        self.assertEqual(rows[0]['orgaan'],'Onbekend')
        self.assertFalse(rows[0]['header_version_matches_snapshot'])
        self.assertEqual(manifest['coverage']['statuses']['tekstversie_verschilt_of_ontbreekt'],1)
        self.extract['rows'].append(self.extract['rows'][0])
        with self.assertRaises(CacheError):build_mapping(self.store,self.extract,self.root)

    def test_mapping_is_separate_readonly_and_bound_to_register(self):
        before=file_hash(self.store.path)
        path,manifest,rows=build_mapping(self.store,self.extract,self.root)
        self.assertEqual(file_hash(self.store.path),before)
        self.assertEqual(manifest['coverage']['orgaan_known'],2)
        self.assertEqual(manifest['coverage']['domain_known'],1)
        self.assertEqual(load_mapping(self.store.manifest,self.root)[0],path)
        bad={**self.store.manifest,'sqlite_sha256':'changed'}
        with self.assertRaises(CacheError):load_mapping(bad,self.root)
        path.write_bytes(path.read_bytes()+b'corrupt')
        with self.assertRaises(CacheError):load_mapping(self.store.manifest,self.root)

    def test_list_detail_filters_counts_exports_and_null_preserved(self):
        build_mapping(self.store,self.extract,self.root)
        store=ActListStore(self.store.path,self.store.manifest,authority_root=self.root)
        self.assertTrue(store.meta()['authority_mapping_available'])
        result=store.list(ActFilters(orgaan='FOD Financiën'))
        self.assertEqual([r['act_id'] for r in result['items']],[1])
        self.assertEqual(result['summary']['duties'],1)
        self.assertFalse(result['items'][0]['ab'])
        self.assertEqual(store.list(ActFilters(beleidsdomein='Financiën'))['summary']['acts'],1)
        self.assertEqual(store.list(ActFilters(orgaan='Vlaamse Regering',beleidsdomein='Financiën'))['summary']['acts'],0)
        self.assertEqual(store.list(ActFilters(orgaan='Onbekend',verdict='unknown'))['items'][0]['act_id'],2)
        self.assertEqual(store.list(ActFilters(orgaan='Vlaamse Regering',io_id='IO-b',duty_status='accepted'))['summary']['acts'],0)
        self.assertEqual(store.list(ActFilters(orgaan='Vlaamse Regering',io_id='IO-b',duty_status='needs_review'))['summary']['duties'],1)
        d=DetailRepository(store).get(1)
        self.assertEqual(d['orgaan'],'FOD Financiën')
        self.assertIn('FOD Financiën',markdown_export(d).decode('utf-8'))
        with store.connect() as db:
            with self.assertRaises(sqlite3.OperationalError):db.execute("UPDATE authorities.authority_map SET orgaan='test'")


if __name__=='__main__':unittest.main()
