"""Bouw grafiekcategorieën uit bestaande, gecontroleerde metadata; geen bronverbinding."""
import json
import sys
from dashboard.data.config import Settings
from dashboard.data.actlist import ActListStore
from dashboard.data.actlist_snapshot import load_snapshot
from dashboard.data.overview_corpus import load_corpus
from dashboard.data.analysis_projection import build_projection


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    settings=Settings.load();store=ActListStore(*load_snapshot(settings),load_analysis=False)
    _,manifest=build_projection(store,load_corpus(settings,store))
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
