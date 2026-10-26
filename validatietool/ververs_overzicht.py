"""Maak alleen de corpusmetadata-cache voor het overzicht; register blijft intact."""
import json
import sys

from dashboard.data.config import Settings
from dashboard.data.actlist import ActListStore
from dashboard.data.actlist_snapshot import load_snapshot
from dashboard.data.overview_corpus import build_corpus


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    settings=Settings.load();store=ActListStore(*load_snapshot(settings),load_analysis=False)
    _,manifest=build_corpus(settings,store)
    print(json.dumps(manifest,ensure_ascii=False,indent=2,default=str))
    return 0


if __name__=='__main__':raise SystemExit(main())
