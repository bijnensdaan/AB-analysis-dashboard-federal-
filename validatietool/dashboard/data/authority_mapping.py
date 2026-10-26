"""Afzonderlijke, immutable orgaankoppeling bij exact één registersnapshot.

Alleen de begrensde hoofdingenquery leest PostgreSQL. Volledige tekst wordt niet
opgehaald. Register-SQLite blijft onveranderd; resultaten staan in een sidecar.
"""
from collections import Counter
from datetime import datetime,timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from .actlist_snapshot import file_hash
from .cache import CacheError,canonical
from .connection import read_session
from ..logic import authorities
from ..logic import policy_remit

ROOT=Path(__file__).resolve().parents[2]/'data/dashboard_authorities'
VERSION=1


def revision():
    return hashlib.sha256(Path(authorities.__file__).read_bytes()+Path(policy_remit.__file__).read_bytes()+(Path(__file__).parent/'sql/authority_headers.sql').read_bytes()).hexdigest()


def extract_headers(settings,store):
    """Eén begrensde SELECT; sluit bronverbinding vóór lokale herkenning."""
    with read_session(settings,'register') as source:
        rows=source.fetch('authority_headers')
        metadata=dict(source.metadata)
    return {'source':metadata,'register_snapshot_id':store.manifest['snapshot_id'],'prefix_limit':4096,'rows':rows}


def build_mapping(store,extraction,root=ROOT):
    """Teleenheid: elke act in deze registersnapshot, één rij ongeacht aantal runs.

    Live raw-/llm-hashes én NUMAC moeten bij de bestaande snapshot passen.
    Veranderde/ontbrekende bronrijen blijven onbekend; geen tijdreisclaim.
    """
    if extraction.get('register_snapshot_id')!=store.manifest['snapshot_id']:
        raise CacheError('Hoofdingextractie hoort bij een andere registersnapshot.')
    rows=extraction['rows'];headers={r['act_id']:r for r in rows}
    if len(headers)!=len(rows):raise CacheError('Dubbele act in hoofdingextractie.')
    with store.connect() as db:
        acts=[dict(r) for r in db.execute('SELECT act_id,numac FROM acts ORDER BY act_id')]
        metadata={r['act_id']:r for r in (json.loads(row[0]) for row in db.execute("SELECT data FROM detail_records WHERE kind='text_metadata'"))}
    duplicate_numacs={numac for numac,n in Counter(a['numac'] for a in acts).items() if n>1}
    results=[]
    for act in acts:
        head=headers.get(act['act_id']);meta=metadata.get(act['act_id'])
        valid=head is not None and meta is not None and head['numac']==act['numac'] and all(head.get(k)==meta.get(k) for k in ('raw_hash','llm_hash'))
        result=authorities.identify(head.get('prefix')) if valid else {'orgaan':'Onbekend','beleidsdomein':'Onbekend','authority_id':None,'status':'tekstversie_verschilt_of_ontbreekt','evidence':[]}
        if act['numac'] in duplicate_numacs:
            result={'orgaan':'Onbekend','beleidsdomein':'Onbekend','authority_id':None,'status':'dubbele_numac','evidence':[]}
        result['domain_method']='expliciete_diensthoofding' if result['beleidsdomein']!='Onbekend' else 'onbekend'
        result['domain_evidence']=list(result['evidence']) if result['beleidsdomein']!='Onbekend' else []
        if valid and act['numac'] not in duplicate_numacs and result['beleidsdomein']=='Onbekend' and result['status'] in ('gekoppeld','geen_herkende_hoofding'):
            remit=policy_remit.identify_remit(head.get('prefix'))
            if remit:result.update(remit)
        result.update(act)
        result['raw_hash']=meta.get('raw_hash') if meta else None
        result['llm_hash']=meta.get('llm_hash') if meta else None
        result['header_version_matches_snapshot']=valid
        result['prefix_sha256']=hashlib.sha256(head['prefix'].encode('utf-8')).hexdigest() if valid and head.get('prefix') is not None else None
        result['context']=head['prefix'][:360] if valid and head.get('prefix') else None
        results.append(result)
    total=len(results);matched=sum(r['status']=='gekoppeld' for r in results);domains=sum(r['beleidsdomein']!='Onbekend' for r in results)
    coverage={'unit':'unieke registeracts, alle acts in snapshot; geen corpuspercentage','acts':total,'orgaan_known':matched,
              'orgaan_unknown':total-matched,'orgaan_percent':100*matched/total if total else None,
              'domain_known':domains,'domain_unknown':total-domains,'domain_percent':100*domains/total if total else None,
              'statuses':dict(Counter(r['status'] for r in results)),'organs':dict(Counter(r['orgaan'] for r in results)),
              'domains':dict(Counter(r['beleidsdomein'] for r in results))}
    coverage['domain_methods']=dict(Counter(r['domain_method'] for r in results))
    identity=uuid.uuid4().hex;folder=Path(root)/store.manifest['snapshot_id'];folder.mkdir(parents=True,exist_ok=True)
    building=folder/(identity+'.building.sqlite');target=folder/(identity+'.sqlite')
    db=sqlite3.connect(building)
    try:
        db.execute('CREATE TABLE authority_map (act_id INTEGER PRIMARY KEY,numac TEXT NOT NULL,orgaan TEXT NOT NULL,beleidsdomein TEXT NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL)')
        db.executemany('INSERT INTO authority_map VALUES (?,?,?,?,?,?)',[(r['act_id'],r['numac'],r['orgaan'],r['beleidsdomein'],r['status'],json.dumps(r,ensure_ascii=False)) for r in results])
        db.execute('CREATE INDEX authority_organ ON authority_map(orgaan)');db.execute('CREATE INDEX authority_domain ON authority_map(beleidsdomein)')
        db.commit()
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise CacheError('Koppeltabel is beschadigd.')
    finally:db.close()
    os.replace(building,target)
    manifest={'version':VERSION,'mapping_id':identity,'register_snapshot_id':store.manifest['snapshot_id'],
              'register_sqlite_sha256':store.manifest['sqlite_sha256'],'revision':revision(),
              'source':extraction['source'],'created_utc':datetime.now(timezone.utc).isoformat(),
              'prefix_limit':4096,'coverage':coverage,'sqlite_sha256':file_hash(target),
              'domain_method':'Brede dashboardrubriek uit een expliciete diensthoofding of één eenduidige voordragende ministerportefeuille; geen inhoudelijke classificatie. Algemene organen alleen leveren Onbekend op.',
              'full_act_text_loaded':False,'sources':authorities.SOURCES,'reference':authorities.REFERENCE}
    (folder/(identity+'.json')).write_bytes(canonical(manifest))
    temporary=folder/'LATEST.tmp';temporary.write_text(identity,encoding='utf-8');os.replace(temporary,folder/'LATEST')
    return target,manifest,results


def load_mapping(register_manifest,root=ROOT):
    folder=Path(root)/register_manifest['snapshot_id']
    if not (folder/'LATEST').exists():return None
    try:
        identity=(folder/'LATEST').read_text(encoding='utf-8').strip()
        if not re.fullmatch('[0-9a-f]{32}',identity):raise CacheError('Ongeldige orgaankoppeling.')
        manifest=json.loads((folder/(identity+'.json')).read_text(encoding='utf-8'))
        path=folder/(identity+'.sqlite')
        if not (manifest['version']==VERSION and manifest['mapping_id']==identity and manifest['revision']==revision() and
                manifest['register_snapshot_id']==register_manifest['snapshot_id'] and
                manifest['register_sqlite_sha256']==register_manifest['sqlite_sha256'] and file_hash(path)==manifest['sqlite_sha256']):
            raise CacheError('Orgaankoppeling is beschadigd of verouderd. Bouw de koppeling opnieuw.')
        return path,manifest
    except (OSError,KeyError,ValueError,TypeError):raise CacheError('Orgaankoppeling is onvolledig of onleesbaar.') from None


def export_csv(rows,path):
    """Excel-compatibele UTF-8-koppeltabel; citaten met bronposities apart als JSON."""
    fields=['act_id','numac','orgaan','beleidsdomein','authority_id','status','domain_method','header_version_matches_snapshot','raw_hash','llm_hash','evidence','domain_evidence']
    with Path(path).open('w',encoding='utf-8-sig',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for row in rows:writer.writerow({**row,'evidence':json.dumps(row['evidence'],ensure_ascii=False),'domain_evidence':json.dumps(row['domain_evidence'],ensure_ascii=False)})
