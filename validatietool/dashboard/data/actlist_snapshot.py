"""Versiegebonden actlijstcache: alleen bron-SELECT, schrijven in een nieuwe lokale SQLite.

Fase-1-bestanden en hun queryrevision blijven ongemoeid. Alle runs blijven apart;
de actlijst kiest per act precies één verdict-run.
"""
from datetime import date,datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .cache import canonical, CacheError
from .connection import read_session
from ..logic.act_filters import norm
from ..logic.selection import Selection
from ..logic.metrics import require

ROOT=Path(__file__).resolve().parents[2]
SQL=Path(__file__).with_name('actlist_sql')
DEFAULT_ROOT=ROOT/'data/dashboard_actlists'
VERSION=1


def revision():
    digest=hashlib.sha256(str(VERSION).encode())
    for path in sorted(SQL.glob('*.sql')):
        digest.update(path.name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()


def source_queries():
    """Alle bronqueries zijn expliciete SELECT's in source.sql."""
    return dict(part.split('\n',1) for part in (p.strip() for p in (SQL/'source.sql').read_text(encoding='utf-8').split('-- @query ')[1:]))


def file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def cache_folder(settings,root=DEFAULT_ROOT):
    key=hashlib.sha256((settings.cache_identity()+revision()).encode()).hexdigest()
    return Path(root)/key


def build_snapshot(settings,root=DEFAULT_ROOT,enrich=None):
    """Alle bronextracties en controle-SQL in één read-only registertransactie."""
    folder=cache_folder(settings,root);folder.mkdir(parents=True,exist_ok=True)
    snapshot_id=uuid.uuid4().hex
    building=folder/(snapshot_id+'.building.sqlite')
    target=folder/(snapshot_id+'.sqlite')
    local=sqlite3.connect(building)
    manifest={'version':VERSION,'snapshot_id':snapshot_id,'query_revision':revision(),
              'tables':{},'full_act_text_loaded':False,'authority_mapping_available':False}
    try:
        local.executescript((SQL/'schema.sql').read_text(encoding='utf-8'))
        with read_session(settings,'register') as source:
            manifest['source']=dict(source.metadata)
            for table,query in source_queries().items():
                columns=[r[1] for r in local.execute('PRAGMA table_info('+table+')')]
                n=0
                with source.connection.cursor(name='actlist_'+table) as cursor:
                    cursor.itersize=500
                    cursor.execute(query)
                    while True:
                        rows=cursor.fetchmany(500)
                        if not rows:break
                        prepared=[]
                        for row in rows:
                            values=[v.isoformat() if isinstance(v,(date,datetime)) else v for v in row]
                            if table=='acts':values.extend([norm(row[1]),norm(row[2])])
                            elif table=='claims':values.append(norm(row[3]))
                            prepared.append(values)
                        local.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in columns)+')',prepared)
                        n+=len(prepared)
                manifest['tables'][table]=n
                print('Actlijstsnapshot:',table,n,flush=True)
            # Bestaande onafhankelijke controle uit fase 1, dezelfde brontransactie.
            manifest['control']=source.fetch('register_control',Selection().parameters())[0]
            manifest['runs']=source.fetch('run_catalog')
            if enrich is not None:
                enrich(source,local,manifest)
        local.executescript((SQL/'indexes.sql').read_text(encoding='utf-8'))
        local.commit()
        require(local.execute('PRAGMA quick_check').fetchone()[0]=='ok','Lokale cachecontrole faalt.')
        local_counts=local.execute('''SELECT count(*),sum(v.ab IS TRUE),sum(v.ab IS FALSE),sum(v.ab IS NULL)
          FROM verdicts v JOIN latest l USING(act_id,run_id)''').fetchone()
        expected=manifest['control']
        require(tuple(local_counts)==tuple(expected[k] for k in ('acts','acts_ab','acts_no_ab','acts_unknown')),
                'Actlijstverdicts wijken af van onafhankelijke bron-SQL.')
        duty_counts=local.execute('''SELECT count(*),sum(d.n_ab_claims>0),sum(d.status='accepted'),sum(d.status='needs_review')
          FROM duties d JOIN latest l USING(act_id,run_id)''').fetchone()
        require(tuple(duty_counts)==tuple(expected[k] for k in ('duties','duties_ab','duties_accepted','duties_needs_review')),
                'Actlijstbepalingen wijken af van onafhankelijke bron-SQL.')
        missing=local.execute('''SELECT count(*) FROM claims c LEFT JOIN acts a USING(act_id)
          WHERE a.act_id IS NULL''').fetchone()[0]
        require(missing==0,'Claim zonder act in lokale snapshot.')
        manifest['verified']=True
        manifest['completed_utc']=datetime.now(timezone.utc).isoformat()
    finally:
        local.close()
    os.replace(building,target)
    manifest['sqlite_sha256']=file_hash(target)
    (folder/(snapshot_id+'.json')).write_bytes(canonical(manifest))
    pointer=folder/(snapshot_id+'.pointer.tmp')
    pointer.write_text(snapshot_id,encoding='utf-8')
    os.replace(pointer,folder/'LATEST')
    return target,manifest


def load_snapshot(settings,root=DEFAULT_ROOT):
    """Cache laden zonder live verbinding; onvolledige snapshots niet publiceren."""
    import re
    folder=cache_folder(settings,root)
    try:
        identity=(folder/'LATEST').read_text(encoding='utf-8').strip()
        if not re.fullmatch(r'[0-9a-f]{32}',identity):raise CacheError('Ongeldige actlijstverwijzing.')
        manifest=json.loads((folder/(identity+'.json')).read_text(encoding='utf-8'))
        path=folder/(identity+'.sqlite')
        if (manifest.get('verified') is not True or manifest.get('version')!=VERSION or
                manifest.get('query_revision')!=revision() or manifest.get('snapshot_id')!=identity or
                file_hash(path)!=manifest.get('sqlite_sha256')):
            raise CacheError('Actlijstsnapshot is onvolledig of beschadigd.')
        return path,manifest
    except FileNotFoundError:
        raise CacheError('Geen actlijstsnapshot beschikbaar. Start eenmaal met --ververs.') from None
    except (KeyError,TypeError,ValueError):
        raise CacheError('Actlijstmanifest is ongeldig.') from None
