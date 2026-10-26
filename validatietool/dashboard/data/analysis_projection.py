"""Immutable categorielidmaatschappen voor grafieken en exact dezelfde drill-down.

Geen nieuwe bronextractie: alle rich velden komen uit de goedgekeurde snapshot.
Elke membership verwijst naar act/run en waar nodig duty én oorspronkelijke claim.
"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from .cache import CacheError,canonical
from .actlist_snapshot import file_hash
from ..logic import analysis
from ..logic.detail import amended_links
from ..logic.act_filters import norm

ROOT=Path(__file__).resolve().parents[2]/'data/dashboard_analysis'
VERSION=1


def revision():
    return hashlib.sha256(Path(__file__).read_bytes()+Path(analysis.__file__).read_bytes()).hexdigest()


def build_projection(store,corpus=None,root=ROOT):
    identity=uuid.uuid4().hex;folder=Path(root)/store.manifest['snapshot_id'];folder.mkdir(parents=True,exist_ok=True)
    building=folder/(identity+'.building.sqlite');target=folder/(identity+'.sqlite')
    with store.connect() as source:
        acts={r['act_id']:dict(r) for r in source.execute('SELECT * FROM acts')}
        verdicts={(r['act_id'],r['run_id']):dict(r) for r in source.execute('SELECT * FROM verdicts')}
        duties={r['duty_id']:dict(r) for r in source.execute('SELECT * FROM duties')}
        links={}
        for r in source.execute('SELECT duty_id,obligation_id FROM duty_claims'):links.setdefault(r['obligation_id'],[]).append(r['duty_id'])
        reading_rows=[json.loads(r[0]) for r in source.execute("SELECT data FROM detail_records WHERE kind='reading'")]
        successful={(r['act_id'],r['run_id']) for r in source.execute('SELECT act_id,run_id FROM readings WHERE failed=0')}
        authority={r['act_id']:dict(r) for r in source.execute('SELECT act_id,orgaan,beleidsdomein FROM authorities.authority_map')} if store.authority_mapping else {}
        corpus_rows={}
        if corpus:
            source.execute('ATTACH DATABASE ? AS corpusdb',(corpus[0].resolve().as_uri()+'?mode=ro',))
            corpus_rows={r['numac']:dict(r) for r in source.execute('SELECT * FROM corpusdb.corpus')}
    db=sqlite3.connect(building);points={};members=[];n=0;linked_duties=set();complete=False
    db.execute('CREATE TABLE points(chart_id TEXT,point_id TEXT,x TEXT,y TEXT,label TEXT,PRIMARY KEY(chart_id,point_id))')
    db.execute('CREATE TABLE membership(chart_id TEXT,point_id TEXT,act_id INTEGER,run_id INTEGER,duty_id INTEGER,obligation_id INTEGER)')
    def flush():
        nonlocal n
        if members:db.executemany('INSERT INTO membership VALUES (?,?,?,?,?,?)',members);n+=len(members);members.clear()
    def add(chart,x,y,aid,run,did=None,cid=None,label=None):
        key=analysis.point_id(chart,x,y);pk=(chart,key)
        if pk not in points:points[pk]=(chart,key,x,y,label or str(x if y is None else str(x)+' → '+str(y)))
        members.append((chart,key,aid,run,did,cid))
        if len(members)>=3000:flush()
    try:
        for (aid,run),v in verdicts.items():
            a=acts[aid];year=a['pub_date'][:4] if a['pub_date'] else 'Onbekend';law=corpus_rows.get(a['numac'])
            add('funnel','corpus',None,aid,run) if law else None
            if law and law['classifier_selected']:
                add('funnel','selected',None,aid,run)
                if (aid,run) in successful:add('funnel','read',None,aid,run)
                if v['ab'] is not None and v['ab']==1:add('funnel','ab',None,aid,run)
            if v['ab']==1:
                add('ab_year',year,'register',aid,run)
                if law and law['classifier_selected']:add('ab_year',year,'classifier',aid,run)
                add('scope_year',year,v['ab_scope'] or 'Onbekend',aid,run)
                m=authority.get(aid,{})
                add('org',m.get('orgaan','Onbekend'),None,aid,run)
                add('domain',m.get('beleidsdomein','Onbekend'),None,aid,run)
        for did,d in duties.items():
            aid,run=d['act_id'],d['run_id'];v=verdicts.get((aid,run),{});law=corpus_rows.get(acts[aid]['numac'])
            if v.get('ab')==1 and law and law['classifier_selected'] and d['status']=='accepted' and d['n_ab_claims'] is not None and d['n_ab_claims']>0:
                add('funnel','accepted',None,aid,run,did)
        names={r['numac']:r['act_id'] for r in acts.values()}
        for r in reading_rows:
            aid,run=r['act_id'],r['run_id']
            if (aid,run) not in verdicts:continue
            add('act_relation',r.get('act_relation') or 'Niet opgeslagen',None,aid,run)
            for ref in amended_links([r],names):
                value=ref['reference']
                label=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,sort_keys=True)
                # Alleen expliciete NUMAC's delen een groep; geen titelmatching.
                for item in ref['links'] or [{'numac':label}]:add('amended',item['numac'],None,aid,run,label=item['numac'])
        with store.connect() as source:
            for row in source.execute("SELECT data FROM detail_records WHERE kind='claim'"):
                c=json.loads(row[0]);aid,run=c['act_id'],c['run_id'];cid=c['obligation_id']
                if (aid,run) not in verdicts:continue
                a=acts[aid];year=a['pub_date'][:4] if a['pub_date'] else 'Onbekend'
                for did in links.get(cid,[]):
                    d=duties.get(did)
                    if not d or (d['act_id'],d['run_id'])!=(aid,run):continue
                    linked_duties.add(did)
                    bk=c.get('duty_bearer_kind') or 'Niet opgeslagen';rk=c.get('recipient_kind') or 'Niet opgeslagen'
                    add('flow',bk,rk,aid,run,did,cid)
                    add('actors',norm(c.get('duty_bearer')) or 'Niet opgeslagen',norm(c.get('recipient')) or ('Geen ontvanger / bewaren' if rk=='none' else 'Niet opgeslagen'),aid,run,did,cid,
                        label=(c.get('duty_bearer') or 'Niet opgeslagen')+' → '+(c.get('recipient') or 'Niet opgeslagen'))
                    if d['n_ab_claims'] is None or d['n_ab_claims']<=0:continue
                    io=c.get('io_id') or 'Niet opgeslagen'
                    add('flow_ab',bk,rk,aid,run,did,cid)
                    add('io',io,None,aid,run,did,cid);add('io_year',year,io,aid,run,did,cid)
                    add('frequency',c.get('frequency') or 'Niet opgeslagen',None,aid,run,did,cid)
                    add('level_io',a['level'] or 'Onbekend',io,aid,run,did,cid)
                    add('source',c.get('source_kind') or 'Niet opgeslagen',None,aid,run,did,cid)
                    if (c.get('source_kind') or '').startswith('eu_'):add('eu_instruments',c.get('source_ref') or 'EU-bron zonder verwijzing',None,aid,run,did,cid)
                    for item in set(c.get('data_items') or []):
                        if isinstance(item,str) and norm(item):add('data_items',norm(item),None,aid,run,did,cid,label=item)
                    for item in set(c.get('admin_actions') or []):
                        if isinstance(item,str) and item.strip():add('admin_actions',item,None,aid,run,did,cid)
        # Duties zonder claims blijven zichtbaar als ontbrekende categorie, geen verzonnen actor.
        for did,d in duties.items():
            if did in linked_duties:continue
            aid,run=d['act_id'],d['run_id'];year=(acts[aid]['pub_date'] or 'Onbekend')[:4]
            add('flow','Niet opgeslagen','Niet opgeslagen',aid,run,did)
            add('actors','Niet opgeslagen','Niet opgeslagen',aid,run,did)
            if d['n_ab_claims'] is not None and d['n_ab_claims']>0:
                for chart in ('io','frequency','source'):add(chart,'Niet opgeslagen',None,aid,run,did)
                add('flow_ab','Niet opgeslagen','Niet opgeslagen',aid,run,did)
                add('io_year',year,'Niet opgeslagen',aid,run,did)
                add('level_io',acts[aid]['level'] or 'Onbekend','Niet opgeslagen',aid,run,did)
        flush();db.executemany('INSERT INTO points VALUES (?,?,?,?,?)',points.values())
        db.execute('CREATE INDEX membership_point ON membership(chart_id,point_id,act_id,run_id,duty_id,obligation_id)')
        db.execute('CREATE INDEX membership_act ON membership(act_id,run_id,chart_id)')
        db.execute('CREATE INDEX membership_duty ON membership(duty_id,obligation_id,chart_id)')
        db.commit()
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise CacheError('Grafiekprojectie faalt bij cachecontrole.')
        complete=True
    finally:
        db.close()
        if not complete:building.unlink(missing_ok=True)
    os.replace(building,target)
    manifest={'version':VERSION,'projection_id':identity,'register_snapshot_id':store.manifest['snapshot_id'],
              'register_sqlite_sha256':store.manifest['sqlite_sha256'],'authority_mapping_id':store.authority_mapping[1]['mapping_id'] if store.authority_mapping else None,
              'corpus_snapshot_id':corpus[1]['snapshot_id'] if corpus else None,'corpus_path':str(corpus[0].resolve()) if corpus else None,
              'corpus_sha256':corpus[1]['sqlite_sha256'] if corpus else None,'revision':revision(),'memberships':n,'points':len(points),
              'created_utc':datetime.now(timezone.utc).isoformat(),'sqlite_sha256':file_hash(target),'full_act_text_loaded':False}
    (folder/(identity+'.json')).write_bytes(canonical(manifest));temporary=folder/(identity+'.tmp');temporary.write_text(identity,encoding='utf-8');os.replace(temporary,folder/'LATEST')
    return target,manifest


def load_projection(register_manifest,authority_mapping=None,root=ROOT):
    folder=Path(root)/register_manifest['snapshot_id']
    if not (folder/'LATEST').exists():return None
    try:
        identity=(folder/'LATEST').read_text(encoding='utf-8').strip()
        if not re.fullmatch('[0-9a-f]{32}',identity):raise CacheError('Ongeldige grafiekverwijzing.')
        manifest=json.loads((folder/(identity+'.json')).read_text(encoding='utf-8'));path=folder/(identity+'.sqlite')
        if not (manifest['version']==VERSION and manifest['projection_id']==identity and manifest['revision']==revision() and
                manifest['register_snapshot_id']==register_manifest['snapshot_id'] and manifest['register_sqlite_sha256']==register_manifest['sqlite_sha256'] and
                manifest['authority_mapping_id']==(authority_mapping[1]['mapping_id'] if authority_mapping else None) and file_hash(path)==manifest['sqlite_sha256']):
            raise CacheError('Grafiekprojectie is beschadigd of verouderd; bouw de grafiekcache opnieuw.')
        if manifest['corpus_path']:
            corpus=Path(manifest['corpus_path'])
            if file_hash(corpus)!=manifest['corpus_sha256'] or (corpus.parent/'LATEST').read_text(encoding='utf-8').strip()!=manifest['corpus_snapshot_id']:
                raise CacheError('Grafiekcache hoort bij een andere corpusversie; bouw opnieuw.')
        return path,manifest
    except (OSError,KeyError,TypeError,ValueError):raise CacheError('Grafiekcache is onvolledig of onleesbaar.') from None
