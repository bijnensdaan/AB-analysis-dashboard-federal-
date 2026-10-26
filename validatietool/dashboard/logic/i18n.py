"""Presentation-only localisation. Never traverse source records or quotations."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

CATALOG=Path(__file__).resolve().parents[1]/'ui/web/translations.en.json'


@lru_cache(maxsize=1)
def catalogue():
    translations=json.loads(CATALOG.read_text(encoding='utf-8'))
    patterns=[]
    for key in sorted(translations,key=len,reverse=True):
        patterns.append((r'(?<![\w])' if key[0].isalnum() else '')+re.escape(key)+(r'(?![\w])' if key[-1].isalnum() else ''))
    return translations,re.compile('|'.join(patterns))


def tr(value,language='nl'):
    if language!='en' or not isinstance(value,str):return value
    translations,pattern=catalogue()
    return pattern.sub(lambda m:translations[m.group(0)],value)


def localize_chart(data,language='nl'):
    if language!='en':return data
    result=deepcopy(data);result['ui_language']='en'
    for key in ('title','group'):result[key]=tr(result.get(key),language)
    result['notes']=[tr(n,language) for n in result['notes']]
    for key in ('display','coverage'):
        if result.get(key):
            for field in ('description','unit'):
                if field in result[key]:result[key][field]=tr(result[key][field],language)
    if result['chart_id'] not in {'actors','data_items','eu_instruments','amended','org'}:
        for row in result['rows']:row['label']=tr(row['label'],language)
    if result['chart_id']=='org':
        for row in result['rows']:
            if row['label']=='Onbekend':row['label']='Unknown'
    summary=result.get('filter_summary','')
    if summary=='Geen actieve filters; laatste verdict-run per act.':result['filter_summary']=tr(summary,language)
    else:
        result['filter_summary']=' | '.join(tr(p.partition(':')[0],language)+(':'+p.partition(':')[2] if ':' in p else '') for p in summary.split(' | '))
    return result


def localize_payload(route,payload,language='nl'):
    if language!='en' or not isinstance(payload,dict):return payload
    result=deepcopy(payload)
    if 'fout' in result:result['fout']=tr(result['fout'],language)
    if route=='/api/meta':
        for chart in result.get('charts',[]):
            for key in ('title','group'):chart[key]=tr(chart[key],language)
    elif route=='/api/overview':
        for key in ('classifier_disclaimer','scope_denominator'):result[key]=tr(result.get(key),language)
        for key in ('reason','run_note'):
            if key in result.get('corpus',{}):result['corpus'][key]=tr(result['corpus'][key],language)
    elif re.fullmatch(r'/api/act/\d+',route):
        explanation=result.get('explanation',{})
        if 'summary' in explanation:explanation['summary']=tr(explanation['summary'],language)
        if 'notes' in explanation:explanation['notes']=[tr(n,language) for n in explanation['notes']]
    elif re.fullmatch(r'/api/act/\d+/text',route):
        if 'message' in result:result['message']=tr(result['message'],language)
        if 'origin' in result.get('provenance',{}):result['provenance']['origin']=tr(result['provenance']['origin'],language)
    elif route.startswith('/api/flow/act/'):
        result['method']=tr(result.get('method'),language)
        for candidate in result.get('candidates',[]):candidate['evidence_level']=tr(candidate.get('evidence_level'),language)
    elif route.endswith('/evidence'):
        for proof in result.get('policy_proofs',[]):
            for field in ('label','beleidsdomein'):proof[field]=tr(proof.get(field),language)
    return result
