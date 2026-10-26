"""Grafiekdefinities en transparante afleidingen; geen herclassificatie."""
import hashlib
import json
from .act_filters import norm

# Eén bron voor querydocumentatie, titels, eenheden en de grafiekkeuze.
CHARTS={
 'flow':('Informatiestromen · alle bepalingen','flow','duties','Informatiestromen'),
 'flow_ab':('Informatiestromen · AB-bepalingen','flow','duties','Informatiestromen'),
 'actors':('Letterlijke dragers en ontvangers','bar','duties','Informatiestromen'),
 'funnel':('Van corpus naar accepted','funnel','acts','Evolutie en selectie'),
 'ab_year':('AB-acts per publicatiejaar','combo','acts','Evolutie en selectie'),
 'scope_year':('Onderneming en burger door de tijd','stack','acts','Evolutie en selectie'),
 'io':('AB-bepalingen per IO-type','bar','duties','Verdelingen'),
 'io_year':('IO-type per jaar','heatmap','duties','Verdelingen'),
 'org':('AB-acts per overheidsorgaan','bar','acts','Verdelingen'),
 'domain':('AB-acts per beleidsrubriek','bar','acts','Verdelingen'),
 'frequency':('Frequentie van AB-bepalingen','bar','duties','Verdelingen'),
 'level_io':('Bestuursniveau en IO-type','heatmap','duties','Verdelingen'),
 'source':('EU-bron en nationale bron','bar','duties','Bronnen en uitvoering'),
 'eu_instruments':('EU-instrumenten volgens bronverwijzing','bar','duties','Bronnen en uitvoering'),
 'data_items':('Meest gevraagde datavelden','bar','duties','Bronnen en uitvoering'),
 'admin_actions':('Administratieve handelingen','bar','duties','Bronnen en uitvoering'),
 'act_relation':('Wat de act doet','bar','acts','Bronnen en uitvoering'),
 'amended':('Meest gewijzigde acts volgens lezers','bar','acts','Bronnen en uitvoering'),
}
CLAIM_CHARTS={'flow','flow_ab','actors','io','io_year','frequency','level_io','source','eu_instruments','data_items','admin_actions'}
ACTOR_LABELS={'private_business':'Onderneming','private_individual':'Burger','private_person':'Burger','public_body':'Overheidsinstantie',
 'public_authority':'Overheidsinstantie','semi_public':'Semipublieke instantie','third_party':'Derde','none':'Geen ontvanger / bewaren',
 'mixed':'Gemengde ontvangers','unclear':'Onduidelijk',None:'Niet opgeslagen','':'Niet opgeslagen'}


def point_id(chart,x,y=None):
    return hashlib.sha256(json.dumps([chart,x,y],ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()[:32]


def selections(filters):
    return list(zip(filters.chart_id.split(','),filters.point_id.split(','))) if filters.chart_id else []


def with_point(filters,chart,point):
    from dataclasses import replace
    pairs=selections(filters)
    if (chart,point) not in pairs:pairs.append((chart,point))
    return replace(filters,chart_id=','.join(c for c,p in pairs),point_id=','.join(p for c,p in pairs))


def actor_label(kind):return ACTOR_LABELS.get(kind,kind or 'Niet opgeslagen')


def matching_steps(duties,claims):
    """Exacte naam-aansluitingen binnen één act/run; GEEN bewezen informatieketens.

    Alle duties, ook niet-AB: anders zou een openbare tussenstap verdwijnen.
    Alleen witruimte/case normaliseren. Generieke rollen worden niet gekoppeld.
    """
    by_id={d['duty_id']:d for d in duties};by_recipient={};edges=[];seen={}
    for c in claims:
        for did in c.get('linked_duty_ids',[]):
            if did not in by_id:continue
            key=(did,norm(c.get('duty_bearer')),norm(c.get('recipient')))
            proof={k:c.get(k) for k in ('obligation_id','reading_id','quote','io_id','data_items','counts_as_ab','io_reason','ab_reason','rule_reason')}
            if key in seen:
                edge=seen[key];edge['sources'].append(proof)
                edge['data_items']=sorted(set(edge['data_items'])|set(c.get('data_items') or []))
                continue
            edge={'duty_id':did,'claim_id':c['obligation_id'],'bearer':c.get('duty_bearer'),'recipient':c.get('recipient'),
                  'bearer_kind':c.get('duty_bearer_kind'),'recipient_kind':c.get('recipient_kind'),
                  'quote':c.get('quote'),'provision':c.get('provision'),'io_id':c.get('io_id'),
                  'data_items':c.get('data_items') or [],'counts_as_ab':c.get('counts_as_ab'),
                  'duty_counts_as_ab':by_id[did].get('n_ab_claims') is not None and by_id[did]['n_ab_claims']>0}
            edge['sources']=[proof];seen[key]=edge
            edges.append(edge)
            if edge['recipient']:by_recipient.setdefault(norm(edge['recipient']),[]).append(edge)
    generic={'','unknown','onbekend','none','n/a','government','overheid','public authority','bevoegde overheid','de bevoegde overheid','het publiek','de overheid','derde','third party'}
    pairs=[];pair_seen=set()
    for second in edges:
        key=norm(second['bearer'])
        if key in generic:continue
        for first in by_recipient.get(key,[]):
            if first['duty_id']==second['duty_id']:continue
            identity=(first['duty_id'],second['duty_id'],key)
            if identity in pair_seen:continue
            pair_seen.add(identity)
            shared={norm(x) for x in first['data_items'] if isinstance(x,str)} & {norm(x) for x in second['data_items'] if isinstance(x,str)}
            pairs.append({'first':first,'second':second,'shared_data_items':sorted(shared),
                          'evidence_level':'exacte actornaam; doorgeven van dezelfde gegevens niet vastgesteld'})
    pairs.sort(key=lambda p:(not bool(p['shared_data_items']),p['first']['duty_id'],p['second']['duty_id']))
    return {'edges':edges,'candidates':pairs,'confirmed_chains':None,
            'method':'Alleen aansluitende letterlijke actornamen binnen dezelfde act/run. Geen koppeling tussen acts, geen actor-ID of informatiepakket-ID beschikbaar.'}
