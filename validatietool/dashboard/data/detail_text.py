"""Tekst alleen op aanvraag; inhoud moet bij de metadata-snapshot horen."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading

from .cache import canonical,CacheError
from .repository import DashboardData
from .connection import DataSourceError


def content_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest() if text is not None else None


def matches(text,metadata):
    return all(content_hash(text.get(field))==metadata.get(key) for field,key in [('raw_text','raw_hash'),('llm_text','llm_hash')])


class DetailTextProvider:
    def __init__(self,settings,cache_root,legacy_path=None):
        self.settings=settings;self.root=Path(cache_root);self.lock=threading.Lock()
        self.legacy=Path(legacy_path) if legacy_path else Path(__file__).resolve().parents[2]/'data/representatie_v2.0/register.sqlite'

    def get(self,metadata):
        if metadata is None:return {'available':False,'message':'Geen tekstmetadata opgeslagen.'}
        key=hashlib.sha256(canonical(metadata)).hexdigest()
        with self.lock:
            target=self.root/(key+'.json')
            if target.exists():
                try:
                    envelope=json.loads(target.read_text(encoding='utf-8'))
                    data=envelope['data']
                    if envelope['sha256']!=hashlib.sha256(canonical(data)).hexdigest() or not matches(data['text'],metadata):
                        raise CacheError('Gecachete acttekst is beschadigd of hoort bij een andere versie.')
                    return data
                except (KeyError,ValueError,TypeError):raise CacheError('Ongeldig tekstcachebestand.') from None
            text=None;provenance=None
            # Hergebruik alleen wanneer BEIDE inhoudshashes exact bij de live metadata passen.
            if self.legacy.exists():
                db=sqlite3.connect(self.legacy.resolve().as_uri()+'?mode=ro',uri=True)
                try:
                    row=db.execute('SELECT raw_text,llm_text FROM act_text WHERE act_id=?',(metadata['act_id'],)).fetchone()
                    candidate=dict(zip(('raw_text','llm_text'),row)) if row else None
                finally:db.close()
                if candidate and matches(candidate,metadata):
                    text=candidate;provenance={'origin':'lokale bronexport, inhoud geverifieerd tegen registersnapshot',
                                              'content_matches_snapshot':True,'hash_algorithm':'md5, beide tekstvarianten'}
            if text is None:
                try:live=DashboardData(self.settings).act_text(metadata['act_id'])
                except DataSourceError:return {'available':False,'message':'Acttekst nog niet gecachet en de bronverbinding is niet beschikbaar. De detailmetadata blijft raadpleegbaar.'}
                candidate=live.get('text')
                if not candidate:return {'available':False,'message':'Geen acttekst gevonden in de bron.'}
                if not matches(candidate,metadata):
                    return {'available':False,'message':'De brontekst is gewijzigd sinds deze registersnapshot. Geen tekst met een andere versie gemarkeerd; ververs de snapshot voor de nieuwe versie.'}
                text={key:candidate[key] for key in ('raw_text','llm_text')}
                provenance={'origin':'live read-only opvraag','read_source':live['source'],'content_matches_snapshot':True}
            result={'available':True,'text':text,'provenance':provenance}
            self.root.mkdir(parents=True,exist_ok=True)
            temporary=target.with_suffix('.tmp')
            temporary.write_bytes(canonical({'data':result,'sha256':hashlib.sha256(canonical(result)).hexdigest()}))
            os.replace(temporary,target)
            return result
