"""Leesbare afleidingen met behoud van oorspronkelijke registeruitkomsten."""
from collections import Counter
import json
import re

COMPARE_FIELDS=('quote','provision','duty_bearer','duty_bearer_kind','recipient','recipient_kind',
                'action','io_id','cost_category','data_items','admin_actions','trigger','frequency',
                'keep_available','is_new_here','counts_as_ab','ab_scope','duty_origin','source_kind',
                'source_ref','io_reason','ab_reason','rule_reason')


def disagreements(claims):
    """Alleen feitelijke veldverschillen, inclusief NULL versus ingevuld."""
    return [field for field in COMPARE_FIELDS if len({json.dumps(c.get(field),sort_keys=True,ensure_ascii=False) for c in claims})>1]


def explain_verdict(verdict,duties,claims):
    """Beschrijf opgeslagen bewijs; vul nooit ontbrekende juridische motivering in."""
    ab=verdict.get('ab')
    count=sum(d.get('n_ab_claims') is not None and d['n_ab_claims']>0 for d in duties)
    notes=[]
    if ab is None:
        summary='Het actverdict is onbekend. Ontbrekende of mislukte verwerking is geen oordeel “geen AB”.'
    elif ab:
        summary='Het opgeslagen actverdict is AB.'
    elif not duties and not claims:
        summary='Het opgeslagen actverdict is geen AB. In deze run zijn geen kandidaatclaims of registerbepalingen opgeslagen.'
    elif claims and all(c.get('counts_as_ab') is False for c in claims):
        if all(c.get('duty_origin')=='restates_elsewhere' for c in claims):
            summary='Het opgeslagen actverdict is geen AB. Alle opgeslagen claims zijn uitgesloten en als elders ingevoerd aangemerkt.'
        else:
            summary='Het opgeslagen actverdict is geen AB. De gevonden claims worden volgens hun opgeslagen meetelregels niet meegeteld; hun redenen staan hieronder.'
    else:
        summary='Het opgeslagen actverdict is geen AB. Onderliggende claims of bepalingen kunnen daarvan afwijken; beide blijven zichtbaar.'
    if ab is False and count:
        notes.append('Het actverdict is geen AB, maar '+str(count)+' registerbepalingen hebben n_ab_claims > 0. Het dashboard corrigeert geen van beide uitkomsten.')
    if ab is True and not count:
        notes.append('Het actverdict is AB, maar er zijn geen registerbepalingen met n_ab_claims > 0 in deze run.')
    if verdict.get('n_ab_obligations')!=count:
        notes.append('De opgeslagen verdictteller n_ab_obligations verschilt van de telling via duty. Beide worden afzonderlijk weergegeven.')
    return {'summary':summary,'stored_reason':verdict.get('reason'),'notes':notes,
            'ab_duties':count,'stored_verdict_count':verdict.get('n_ab_obligations'),
            'exclusion_rules':[{'rule':rule,'claims':n} for rule,n in Counter(c.get('rule_reason') or 'Geen rule_reason opgeslagen' for c in claims if c.get('counts_as_ab') is False).most_common()]}


def amended_links(readings,acts_by_numac):
    """Alleen exacte NUMAC's koppelen; geen fuzzy titelkoppeling of nieuwe identificatie."""
    output=[]
    for reading in readings:
        raw=reading.get('amended_acts')
        for reference in raw if isinstance(raw,list) else ([raw] if raw else []):
            text=reference if isinstance(reference,str) else json.dumps(reference,ensure_ascii=False)
            tokens=set(re.findall(r'(?<![A-Za-z0-9])\d{10}(?![A-Za-z0-9])',text))
            if text.strip() in acts_by_numac:tokens.add(text.strip())
            if isinstance(reference,dict):
                for field in ('numac','act_numac','NUMAC'):
                    if str(reference.get(field,'')) in acts_by_numac:tokens.add(str(reference[field]))
            output.append({'reading_id':reading['reading_id'],'model':reading['model_slug'],'reference':reference,
                           'links':[{'numac':n,'act_id':acts_by_numac[n]} for n in sorted(tokens) if n in acts_by_numac]})
    return output
