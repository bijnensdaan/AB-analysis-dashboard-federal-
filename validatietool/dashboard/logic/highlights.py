"""Citaatmarkeringen met uitsluitend exacte tekst plus witruimtetolerantie."""
import re


def normalized(text):
    words=list(re.finditer(r'\S+',text));chars=[];positions=[]
    for i,match in enumerate(words):
        if i:chars.append(' ');positions.append(match.start()-1)
        chars.extend(match.group());positions.extend(range(match.start(),match.end()))
    return ''.join(chars),positions


def highlight(text,detail):
    haystack,mapping=normalized(text)
    patterns=[]
    for duty in detail['duties']:
        if duty.get('n_ab_claims') is not None and duty['n_ab_claims']>0:
            ios=sorted({c['io_id'] for c in duty['claims'] if c.get('counts_as_ab') is True and c.get('io_id')})
            patterns.append((duty.get('canonical_quote') or '',{'target':'duty-'+str(duty['duty_id']),'io_ids':ios,'kind':'registerbepaling'}))
    for claim in detail['claims']:
        if claim.get('counts_as_ab') is True:
            targets=['duty-'+str(d) for d in claim['linked_duty_ids']] or ['loose-'+str(claim['obligation_id'])]
            for target in targets:patterns.append((claim.get('quote') or '',{'target':target,'io_ids':[claim['io_id']] if claim.get('io_id') else [],'kind':'positieve lezersclaim'}))
    ranges=[];unmatched=[]
    for quote,info in patterns:
        needle=' '.join(quote.split());start=0;found=False
        if not needle:continue
        while True:
            position=haystack.find(needle,start)
            if position<0:break
            ranges.append({'start':mapping[position],'end':mapping[position+len(needle)-1]+1,**info})
            found=True;start=position+1
        if not found:unmatched.append(info)
    events={}
    for index,item in enumerate(ranges):
        events.setdefault(item['start'],[[],[]])[0].append(index)
        events.setdefault(item['end'],[[],[]])[1].append(index)
    active=set();segments=[];previous=0
    for position,(starts,ends) in sorted(events.items()):
        if position>previous and active:
            selected=[ranges[i] for i in active]
            segments.append({'start':previous,'end':position,
                             'targets':sorted({r['target'] for r in selected}),
                             'io_ids':sorted({io for r in selected for io in r['io_ids']}),
                             'kinds':sorted({r['kind'] for r in selected})})
        active.difference_update(ends);active.update(starts);previous=position
    return {'segments':segments,'unmatched':unmatched,
            'matched_occurrences':len({(r['start'],r['end']) for r in ranges}),
            'method':'Exact citaat met tolerantie voor witruimte; geen fuzzy of juridische beoordeling.'}
