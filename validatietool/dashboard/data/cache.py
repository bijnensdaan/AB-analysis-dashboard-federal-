"""Onveranderlijke JSON-snapshots; pas na verificatie atomair publiceren.

De digest detecteert beschadigde cachebestanden. Er worden geen credentials opgeslagen.
Een cachehit opent geen databaseverbinding; verversen gebeurt alleen expliciet.
"""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .connection import SQL_ROOT

FORMAT_VERSION = 1
LOGIC_VERSION = 1
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / 'data' / 'dashboard_snapshots'


class CacheError(RuntimeError):
    pass


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError('Niet ondersteund snapshotveld.')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=json_value).encode('utf-8')


def query_revision():
    digest = hashlib.sha256(str(LOGIC_VERSION).encode())
    for path in sorted(SQL_ROOT.glob('*.sql')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def selection_key(settings, selection):
    return hashlib.sha256(canonical({'source':settings.cache_identity(), 'selection':selection.as_dict(),
                                    'format':FORMAT_VERSION, 'queries':query_revision()})).hexdigest()


class SnapshotCache:
    def __init__(self, root=DEFAULT_CACHE):
        self.root = Path(root)

    def _folder(self, key):
        if not re.fullmatch(r'[0-9a-f]{64}', key):
            raise CacheError('Ongeldige cachesleutel.')
        return self.root / key

    def load(self, key):
        folder = self._folder(key)
        try:
            name = (folder / 'LATEST').read_text(encoding='utf-8').strip()
            if not re.fullmatch(r'[0-9a-f]{32}\.json', name):
                raise CacheError('Ongeldige snapshotverwijzing.')
            envelope = json.loads((folder / name).read_text(encoding='utf-8'))
            payload = envelope['snapshot']
            if hashlib.sha256(canonical(payload)).hexdigest() != envelope['sha256']:
                raise CacheError('Snapshotcontrolewaarde wijkt af; cache is beschadigd.')
            if (payload['cache_key'] != key or payload['format_version'] != FORMAT_VERSION or
                    payload['query_revision'] != query_revision() or payload['verified'] is not True):
                raise CacheError('Snapshotversie of verificatie is ongeldig.')
            return payload
        except FileNotFoundError:
            raise CacheError('Geen complete snapshot voor deze selectie. Gebruik --ververs voor live controle.') from None
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise CacheError('Snapshotbestand is ongeldig of beschadigd.') from None

    def publish(self, key, payload):
        if payload.get('verified') is not True or payload.get('cache_key') != key:
            raise CacheError('Ongecontroleerde snapshot wordt niet gepubliceerd.')
        folder = self._folder(key)
        folder.mkdir(parents=True, exist_ok=True)
        name = payload['snapshot_id'] + '.json'
        if not re.fullmatch(r'[0-9a-f]{32}\.json', name):
            raise CacheError('Ongeldige snapshot-ID.')
        # Alleen nieuwe immutable snapshotbestanden; LATEST is het enige vervangbare bestand.
        envelope = {'snapshot':payload, 'sha256':hashlib.sha256(canonical(payload)).hexdigest()}
        with (folder / name).open('xb') as output:
            output.write(canonical(envelope))
            output.flush()
            os.fsync(output.fileno())
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, delete=False,
                                             prefix='.latest-', suffix='.tmp') as pointer:
                temp_name = pointer.name
                pointer.write(name + '\n')
                pointer.flush()
                os.fsync(pointer.fileno())
            os.replace(temp_name, folder / 'LATEST')
        finally:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()
        return folder / name
