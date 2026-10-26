"""Afgeleide cijfers op bestaande uitkomsten; geen wijziging van registeroordelen."""
from collections import Counter

DISCLAIMER = ('Deze aandelen betreffen gedetecteerde AB in acts die de classifier selecteerde '
              '(pred = 1, zekerheid ≥ 0,75); geen schatting van alle werkelijke AB in het Staatsblad.')


class VerificationError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def compare_metrics(actual, independent, label):
    require(actual.keys() == independent.keys(), label + ': controlekolommen verschillen.')
    for key, value in actual.items():
        require(value == independent[key], label + ': onafhankelijke SQL wijkt af bij ' + key + '.')


def derive(register, corpus, register_facts, corpus_facts):
    """Koppel op exacte NUMAC; extra registeracts blijven buiten de classifiercohort."""
    require(register['acts'] == register['acts_ab'] + register['acts_no_ab'] + register['acts_unknown'],
            'Actverdicts tellen niet op tot het aantal acts.')
    require(register['duties'] >= register['duties_ab'], 'AB-duties overschrijden totaal.')
    require(register['duties_accepted'] + register['duties_needs_review'] == register['duties'],
            'Onverwachte duty-status; niet stilzwijgend als accepted of needs_review opnemen.')
    require(corpus['corpus_rows'] == corpus['corpus_acts'] and corpus['corpus_missing_numac'] == 0,
            'Corpus bevat dubbele/ontbrekende NUMAC; snapshot niet gepubliceerd.')
    laws = {r['numac']: r for r in corpus_facts}
    require(len(laws) == len(corpus_facts) == corpus['corpus_acts'], 'Corpusfacts verschillen van SQL.')
    require(len(register_facts) == register['acts'], 'Registerfacts verschillen van SQL.')
    require(len({r['numac'] for r in register_facts}) == len(register_facts), 'Dubbele register-NUMAC.')
    require(sum(r['ab'] is True for r in register_facts) == register['acts_ab'], 'AB-facts verschillen van SQL.')
    require(sum(r['read_success'] for r in register_facts) == register['acts_read'], 'Leesstatus wijkt af.')
    require(sum(r['accepted'] for r in register_facts) == register['acts_with_accepted_duty'], 'Accepted-facts wijken af.')
    require(sum(r['classifier_selected'] for r in corpus_facts) == corpus['classifier_selected'],
            'Classifierfacts verschillen van SQL.')
    matched = [r for r in register_facts if r['numac'] in laws]
    require(all(r['pub_date'] == laws[r['numac']]['pub_date_iso'] for r in matched),
            'Publicatiedatums verschillen tussen bronnen; noemer niet veilig vastgesteld.')
    selected = [r for r in matched if laws[r['numac']]['classifier_selected']]
    ab_selected = [r for r in selected if r['ab'] is True]
    require(all(r['read_success'] for r in ab_selected),
            'AB-verdict zonder foutloze lezing binnen classifiercohort; trechter vraagt onderzoek.')
    cohort = {'register_matched': len(matched), 'register_outside_corpus': len(register_facts)-len(matched),
              'register_outside_classifier': len(register_facts)-len(selected),
              'classifier_in_register': len(selected),
              'classifier_not_in_register': corpus['classifier_selected']-len(selected),
              'classifier_read': sum(r['read_success'] for r in selected),
              'classifier_ab': len(ab_selected),
              'classifier_ab_with_accepted': sum(r['accepted'] for r in ab_selected),
              'detected_ab_share_of_corpus': len(ab_selected)/corpus['corpus_acts'] if corpus['corpus_acts'] else None,
              'disclaimer': DISCLAIMER}
    scopes = Counter(r['ab_scope'] for r in register_facts if r['ab'] is True)
    scope_rows = [{'scope': scope, 'acts': count, 'share_of_ab_acts': count/register['acts_ab']}
                  for scope, count in sorted(scopes.items(), key=lambda pair: (pair[0] is None, pair[0] or ''))]
    return cohort, scope_rows
