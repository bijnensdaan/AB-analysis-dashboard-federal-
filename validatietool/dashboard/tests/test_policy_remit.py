"""Portefeuillebewijs mag geen orgaan, citaat of ontbrekend tekstdeel verzinnen."""
import unittest

from dashboard.logic.policy_remit import identify_remit
from dashboard.tests import test_authorities
from dashboard.data.authority_mapping import build_mapping


class PolicyRemitTests(unittest.TestCase):
    def test_whole_portfolio_and_source_offsets(self):
        for role, domain in [('de Minister van Werk', 'Werk en sociaal overleg'),
                             ('Onze Vice-Eerste Minister en Minister van Financiën', 'Financiën'),
                             ('de Minister bevoegd voor Onderwijs', 'Onderwijs en vorming')]:
            source=f'\nFILIP, Koning der Belgen,Gelet op de wet;Op de voordracht van {role},Hebben Wij besloten en besluiten Wij : Artikel 1. Test'
            result=identify_remit(source)
            self.assertEqual(result['beleidsdomein'],domain)
            for e in result['domain_evidence']:
                self.assertEqual(source[e['start']:e['end']],e['text'])
                self.assertIn(role,e['text'])

    def test_ambiguous_partial_report_body_and_missing_boundaries(self):
        for clause in ['de Minister van Werk en de Minister van Financiën',
                       'de Minister van Werk en Begroting', 'de Minister van Werkgelegen',
                       'de Minister van Onbekend', 'de Minister van Werk, op voorstel van de Minister van Financiën']:
            self.assertIsNone(identify_remit('FILIP, Koning der Belgen,Op de voordracht van '+clause+',Hebben Wij besloten :'))
        for source in [
            'VERSLAG AAN DE KONING FILIP, Koning der Belgen,Op de voordracht van de Minister van Werk,Hebben Wij besloten :',
            'FILIP, Koning der Belgen,Artikel 1. Op de voordracht van de Minister van Werk,Hebben Wij besloten :',
            'FILIP, Koning der Belgen,Op de voordracht van de Minister van Werk',
            'FILIP, Koning der Belgen,Op de voordracht van de Minister van Werk;Op de voordracht van de Minister van Werk,Hebben Wij besloten :',
            'De Vlaamse Regering,Gelet op de wet;'+('x'*4096)+'Op de voordracht van de Minister van Werk,Besluit :',
        ]:
            self.assertIsNone(identify_remit(source),source[:100])


class PolicyMappingTests(unittest.TestCase):
    setUp = test_authorities.AuthorityMappingTests.setUp

    def test_domain_enrichment_preserves_unknown_organ_and_hash_guard(self):
        row=self.extract['rows'][0]
        row['prefix']='FILIP, Koning der Belgen,Op de voordracht van de Minister van Werk,Hebben Wij besloten :'
        _,_,rows=build_mapping(self.store,self.extract,self.root)
        result=next(r for r in rows if r['act_id']==row['act_id'])
        self.assertEqual(result['orgaan'],'Onbekend')
        self.assertEqual(result['beleidsdomein'],'Werk en sociaal overleg')
        self.assertEqual(result['domain_method'],'expliciete_voordragende_portefeuille')
        row['raw_hash']='gewijzigd'
        _,_,rows=build_mapping(self.store,self.extract,self.root)
        result=next(r for r in rows if r['act_id']==row['act_id'])
        self.assertEqual(result['beleidsdomein'],'Onbekend')
        self.assertEqual(result['domain_evidence'],[])


if __name__=='__main__':unittest.main()
