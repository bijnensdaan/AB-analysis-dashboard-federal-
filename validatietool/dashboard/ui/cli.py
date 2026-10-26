"""Nederlandse kerncijfercontrole voor fase 1; geen dashboardtabbladen vooruitbouwen."""
import argparse
from datetime import datetime
import json
import sys
from zoneinfo import ZoneInfo

from ..data.cache import CacheError, SnapshotCache
from ..data.config import ConfigurationError, Settings
from ..data.connection import DataSourceError
from ..data.repository import DashboardData
from ..logic.metrics import VerificationError
from ..logic.selection import Selection


def count(value):
    return f'{value:,}'.replace(',', '.')


def render(snapshot, cached):
    lines = ['AB-dashboard · fase 1 · ' + ('bestaande snapshot, geen live verbinding' if cached else 'live gecontroleerde snapshot'),
             'Snapshot-ID: ' + snapshot['snapshot_id']]
    for name, source in snapshot['sources'].items():
        timestamp = datetime.fromisoformat(source['snapshot_utc']).astimezone(ZoneInfo('Europe/Brussels'))
        lines.append(f"Bron {name}: {timestamp:%d-%m-%Y %H:%M:%S %Z} · alleen-lezen · {source['isolation']}")
    lines.append(f"Bronmomenten verschillen {snapshot['source_time_difference_seconds']:.2f} seconden; geen atomair snapshot over beide databanken.")
    lines.append('Selectie: ' + json.dumps(snapshot['selection'], ensure_ascii=False))
    rows = [('Corpusacts',snapshot['corpus']['corpus_acts']),
            ('Classifiergeselecteerd',snapshot['corpus']['classifier_selected'])]
    for name, label in [('acts','Registeracts'), ('acts_read','Gelezen acts'), ('acts_ab','Acts met AB'),
                        ('acts_no_ab','Acts zonder AB'), ('acts_unknown','Acts onbekend'),
                        ('duties','Bepalingen'), ('duties_ab','AB-bepalingen (duty.n_ab_claims > 0)'),
                        ('duties_accepted','Bepalingen accepted'), ('duties_needs_review','Bepalingen needs_review'),
                        ('duties_ab_accepted','AB-bepalingen accepted'), ('duties_ab_needs_review','AB-bepalingen needs_review')]:
        rows.append((label, snapshot['register'][name]))
    lines += [f'{label}: {count(value)}' for label, value in rows]
    labels = {'business':'Ondernemingen', 'citizen':'Burgers', 'both':'Beide', None:'Onbekende scope'}
    for row in snapshot['scope_of_ab_acts']:
        label = labels.get(row['scope'], 'Overige opgeslagen scope: ' + str(row['scope']))
        lines.append(f"Scope {label}: {count(row['acts'])} ({row['share_of_ab_acts']:.2%} van alle AB-acts)")
    lines.append('Scopepercentages beschrijven de opgeslagen scope binnen de registerselectie, inclusief onbekend; geen corpusraming.')
    cohort = snapshot['classifier_cohort']
    share = cohort['detected_ab_share_of_corpus']
    lines.append('Gedetecteerde AB-acts / corpusacts: ' + (f'{share:.2%}' if share is not None else 'niet beschikbaar'))
    lines.append(cohort['disclaimer'])
    lines.append(f"Corpusperiode: {snapshot['corpus']['corpus_date_from']} t/m {snapshot['corpus']['corpus_date_to']}; randjaren kunnen onvolledig zijn.")
    lines.append('Onafhankelijke SQL-controles: geslaagd. Geen actteksten geladen.')
    return '\n'.join(lines)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Kerncijfers uit gecontroleerde, alleen-lezen AB-dashboardsnapshot.')
    parser.add_argument('--ververs', action='store_true', help='Lees beide bronnen live en publiceer na SQL-controle.')
    parser.add_argument('--run', type=int, dest='run_id', help='Expliciete run; geen terugval naar andere runs.')
    parser.add_argument('--jaar-van', type=int, dest='year_from')
    parser.add_argument('--jaar-tot', type=int, dest='year_to')
    parser.add_argument('--env', help='Ander .env-bestand; bestaande bestanden worden niet aangepast.')
    parser.add_argument('--cache-map', help='Andere lokale snapshotmap.')
    parser.add_argument('--json', action='store_true', help='Snapshot als JSON, zonder credentials.')
    args = parser.parse_args(argv)
    try:
        settings = Settings.load(args.env)
        selection = Selection(args.run_id, args.year_from, args.year_to)
        data = DashboardData(settings, SnapshotCache(args.cache_map) if args.cache_map else None)
        snapshot = data.snapshot(selection, refresh=args.ververs)
        print(json.dumps(snapshot, ensure_ascii=False, indent=2) if args.json else render(snapshot, not args.ververs))
        return 0
    except (ConfigurationError, DataSourceError, CacheError, VerificationError, ValueError) as exc:
        print('Controle niet voltooid: ' + str(exc), file=sys.stderr)
        return 2
    except OSError:
        print('Controle niet voltooid: lokaal bestand kon niet worden gelezen of opgeslagen.', file=sys.stderr)
        return 2
