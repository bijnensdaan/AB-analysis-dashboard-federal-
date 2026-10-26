"""Publieke datalaag: gecontroleerde snapshots en afzonderlijke lazy tekstopvragen."""
from datetime import datetime, timezone
from collections import Counter
import json
import uuid

from ..logic.metrics import compare_metrics, derive, require
from ..logic.selection import Selection
from .cache import FORMAT_VERSION, SnapshotCache, canonical, query_revision, selection_key
from .config import Settings
from .connection import read_session


class DashboardData:
    def __init__(self, settings=None, cache=None):
        self.settings = settings if settings is not None else Settings.load()
        self.cache = cache if cache is not None else SnapshotCache()

    def snapshot(self, selection=None, refresh=False):
        """Default is cache-only. Verversen vergelijkt kerncijfers binnen dezelfde bronsnapshots."""
        selection = selection if selection is not None else Selection()
        key = selection_key(self.settings, selection)
        if not refresh:
            return self.cache.load(key)
        params = selection.parameters()
        with read_session(self.settings, 'register') as session:
            register = session.fetch('register_metrics', params)[0]
            control = session.fetch('register_control', params)[0]
            compare_metrics(register, control, 'Register')
            facts = session.fetch('register_facts', params)
            runs = session.fetch('run_catalog')
            if selection.run_id is not None:
                require(any(r['run_id'] == selection.run_id for r in runs), 'De gekozen run bestaat niet.')
            register_source = dict(session.metadata)
        # De eerste verbinding is al gesloten vóór de tweede begint.
        with read_session(self.settings, 'corpus') as session:
            corpus = session.fetch('corpus_metrics', params)[0]
            control = session.fetch('corpus_control', params)[0]
            compare_metrics(corpus, control, 'Corpus')
            corpus_facts = session.fetch('corpus_facts', params)
            eu_catalog = session.fetch('eu_catalog')
            corpus_source = dict(session.metadata)
        cohort, scopes = derive(register, corpus, facts, corpus_facts)
        start = datetime.fromisoformat(register_source['snapshot_utc'])
        end = datetime.fromisoformat(corpus_source['snapshot_utc'])
        payload = {'format_version':FORMAT_VERSION, 'snapshot_id':uuid.uuid4().hex,
                   'cache_key':key, 'query_revision':query_revision(), 'selection':selection.as_dict(),
                   'created_utc':datetime.now(timezone.utc).isoformat(),
                   'sources':{'register':register_source, 'corpus':corpus_source},
                   'source_time_difference_seconds':abs((end-start).total_seconds()),
                   'atomic_across_databases':False, 'register':register, 'corpus':corpus,
                   'classifier_cohort':cohort, 'scope_of_ab_acts':scopes, 'runs':runs,
                   'chosen_runs':dict(sorted(Counter(str(r['run_id']) for r in facts).items())),
                   'eu_catalog':eu_catalog, 'verified':True,
                   'verification':{'register':'register_control.sql: alle kerncijfers gelijk',
                                   'corpus':'corpus_control.sql: alle kerncijfers gelijk',
                                   'facts':'NUMAC, datums, leesstatus en somcontroles geslaagd'}}
        # Een cachehit en een verse snapshot hebben identieke JSON-types.
        payload = json.loads(canonical(payload))
        self.cache.publish(key, payload)
        return payload

    def act_text(self, act_id):
        """Laad tekst alleen expliciet. Eigen leestijd, geen historisch tekstsnapshot suggereren."""
        if type(act_id) is not int or act_id < 1:
            raise ValueError('Act-ID moet een positief geheel getal zijn.')
        with read_session(self.settings, 'register') as session:
            rows = session.fetch('act_text', {'act_id':act_id})
            return {'source':dict(session.metadata), 'text':rows[0] if rows else None,
                    'part_of_cached_snapshot':False}

    def eu_text(self, celex):
        """Alleen exact gevraagde bron laden; geen automatische koppeling op vrije tekst."""
        if not isinstance(celex, str) or not celex.strip() or len(celex) > 100:
            raise ValueError('Geef een geldige CELEX-sleutel op.')
        with read_session(self.settings, 'corpus') as session:
            return {'source':dict(session.metadata), 'sections':session.fetch('eu_text', {'celex':celex}),
                    'part_of_cached_snapshot':False}
