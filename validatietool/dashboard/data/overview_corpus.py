"""Gecontroleerde corpusmetadata naast de ongewijzigde registersnapshot."""
from datetime import date,datetime,timezone
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
from ..logic.metrics import require
from ..logic.selection import Selection

SQL=Path(__file__).with_name('overview_sql')
ROOT=Path(__file__).resolve().parents[2]/'data/dashboard_corpus'
VERSION=1


def revision():
    return hashlib.sha256((SQL/'corpus_source.sql').read_bytes()+str(VERSION).encode()).hexdigest()


def folder_for(settings,store,root=ROOT):
    key=hashlib.sha256(canonical({'source':settings.cache_identity(),'register':store.manifest['snapshot_id'],'revision':revision()})).hexdigest()
    return Path(root)/key


def build_corpus(settings,store,root=ROOT):
    """Eén corpusverbinding; metadata en onafhankelijke broncontrole in dezelfde transactie.

    Bronmoment verschilt expliciet van het register. Gekoppelde NUMAC/datums
    worden gecontroleerd; er wordt geen atomaire tweedatabanksnapshot geclaimd.
    """
    folder=folder_for(settings,store,root);folder.mkdir(parents=True,exist_ok=True)
    identity=uuid.uuid4().hex;building=folder/(identity+'.building.sqlite');target=folder/(identity+'.sqlite')
    db=sqlite3.connect(building,uri=True)
    complete=False
    try:
        db.execute('CREATE TABLE corpus(numac TEXT PRIMARY KEY,pub_date TEXT,language TEXT,doc_type TEXT,classifier_selected INTEGER NOT NULL)')
        with read_session(settings,'corpus') as source:
            metadata=dict(source.metadata)
            with source.connection.cursor(name='overview_corpus') as cursor:
                cursor.itersize=1000;cursor.execute((SQL/'corpus_source.sql').read_text(encoding='utf-8'))
                while True:
                    rows=cursor.fetchmany(1000)
                    if not rows:break
                    db.executemany('INSERT INTO corpus VALUES (?,?,?,?,?)',[
                      [v.isoformat() if isinstance(v,(date,datetime)) else v for v in row] for row in rows])
            control=source.fetch('corpus_control',Selection().parameters())[0]
        counts=db.execute("SELECT count(*),count(DISTINCT numac),coalesce(sum(numac IS NULL OR trim(numac)=''),0),coalesce(sum(classifier_selected),0),min(pub_date),max(pub_date) FROM corpus").fetchone()
        expected=tuple(control[k].isoformat() if isinstance(control[k],date) else control[k] for k in ('corpus_rows','corpus_acts','corpus_missing_numac','classifier_selected','corpus_date_from','corpus_date_to'))
        require(counts==expected,'Corpusmetadata wijkt af van onafhankelijke broncontrole.')
        require(counts[0]==counts[1] and counts[2]==0,'Dubbele of ontbrekende corpus-NUMAC.')
        db.execute('CREATE INDEX corpus_date ON corpus(pub_date)');db.commit()
        db.execute('ATTACH DATABASE ? AS reg',(store.path.resolve().as_uri()+'?mode=ro',))
        mismatches=db.execute('''SELECT count(*) FROM reg.acts a JOIN corpus c USING(numac)
           WHERE a.pub_date IS NOT c.pub_date''').fetchone()[0]
        matched=db.execute('SELECT count(*) FROM reg.acts a JOIN corpus c USING(numac)').fetchone()[0]
        require(mismatches==0,'Publicatiedatums verschillen tussen register en corpus; niet gepubliceerd.')
        require(db.execute('PRAGMA quick_check').fetchone()[0]=='ok','Corpuscache is beschadigd.')
        complete=True
    finally:
        db.close()
        if not complete:building.unlink(missing_ok=True)
    os.replace(building,target)
    manifest={'version':VERSION,'snapshot_id':identity,'register_snapshot_id':store.manifest['snapshot_id'],
       'register_sqlite_sha256':store.manifest['sqlite_sha256'],'query_revision':revision(),'source':metadata,
       'control':control,'matched_register_acts':matched,'date_mismatches':mismatches,
       'atomic_across_databases':False,'full_text_loaded':False,'verified':True,
       'completed_utc':datetime.now(timezone.utc).isoformat(),'sqlite_sha256':file_hash(target)}
    (folder/(identity+'.json')).write_bytes(canonical(manifest))
    pointer=folder/(identity+'.tmp');pointer.write_text(identity,encoding='utf-8');os.replace(pointer,folder/'LATEST')
    return target,manifest


def load_corpus(settings,store,root=ROOT):
    folder=folder_for(settings,store,root)
    if not (folder/'LATEST').exists():return None
    try:
        identity=(folder/'LATEST').read_text(encoding='utf-8').strip()
        if not re.fullmatch('[0-9a-f]{32}',identity):raise CacheError('Ongeldige corpusverwijzing.')
        manifest=json.loads((folder/(identity+'.json')).read_text(encoding='utf-8'));path=folder/(identity+'.sqlite')
        if not (manifest['verified'] is True and manifest['version']==VERSION and manifest['snapshot_id']==identity and
                manifest['register_snapshot_id']==store.manifest['snapshot_id'] and manifest['query_revision']==revision() and
                manifest['register_sqlite_sha256']==store.manifest['sqlite_sha256'] and manifest['sqlite_sha256']==file_hash(path)):
            raise CacheError('Corpuscache is beschadigd of hoort bij een andere registerversie.')
        return path,manifest
    except (OSError,KeyError,ValueError,TypeError):raise CacheError('Corpuscache is onvolledig of onleesbaar.') from None
