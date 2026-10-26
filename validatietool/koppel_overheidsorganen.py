"""Fase 4: expliciet hoofdingen lezen en een versiegebonden lokale koppeling maken."""
import argparse
import json
from pathlib import Path
import sys

from dashboard.data.actlist import ActListStore
from dashboard.data.actlist_snapshot import load_snapshot
from dashboard.data.config import Settings
from dashboard.data.authority_mapping import build_mapping,extract_headers,export_csv
from dashboard.data.cache import canonical


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extractie',type=Path,help='Bestaande begrensde live extractie hergebruiken; geen bronverbinding.')
    parser.add_argument('--uitvoer',type=Path,default=Path(__file__).resolve().parents[1]/'fase4')
    args=parser.parse_args();settings=Settings.load();store=ActListStore(*load_snapshot(settings),load_authorities=False,load_analysis=False)
    args.uitvoer.mkdir(parents=True,exist_ok=True)
    extraction=json.loads(args.extractie.read_text(encoding='utf-8')) if args.extractie else extract_headers(settings,store)
    if not args.extractie:(args.uitvoer/'hoofdingextractie.json').write_bytes(canonical(extraction))
    path,manifest,rows=build_mapping(store,extraction)
    export_csv(rows,args.uitvoer/'koppeltabel.csv')
    (args.uitvoer/'koppeltabel.json').write_bytes(canonical({'manifest':manifest,'rows':rows}))
    (args.uitvoer/'referentielijst.json').write_bytes(canonical({'sources':manifest['sources'],'reference':manifest['reference']}))
    print(json.dumps({'mapping_id':manifest['mapping_id'],'source':manifest['source'],'coverage':manifest['coverage']},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
