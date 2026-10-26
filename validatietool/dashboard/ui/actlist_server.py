"""Lokale read-only dashboardserver voor de actlijst."""
import argparse
import hashlib
import json
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys
import threading
from urllib.parse import parse_qs,urlsplit,urlencode
import webbrowser

from ..data.actlist import ActListStore
from ..data.actlist_snapshot import build_snapshot
from ..data.cache import CacheError
from ..data.config import Settings,ConfigurationError
from ..data.connection import DataSourceError
from ..logic.act_filters import ActFilters
from ..logic.metrics import VerificationError
from ..data.detail import DetailRepository
from ..data.detail_snapshot import enrich_details
from ..data.detail_text import DetailTextProvider
from ..data.repository import DashboardData
from ..data.overview import OverviewRepository
from ..data.overview_corpus import load_corpus
from ..logic.detail_export import markdown_export,pdf_export
from ..logic.analysis import CHARTS
from ..data.charts import ChartRepository,csv_export,chart_options,LARGE_CHARTS
from ..logic.i18n import localize_chart,localize_payload
import re

WEB=Path(__file__).with_name('web')
ASSETS=('/app.js','/style.css','/detail.js','/detail.css','/overview.js','/overview.css','/charts.js','/charts.css','/i18n.js','/translations.en.json')


def asset_body(asset):
    body=(WEB/asset.lstrip('/')).read_bytes()
    if asset=='/i18n.js':body=body.replace(b'/*__AB_CATALOG__*/{}',(WEB/'translations.en.json').read_bytes())
    return body


def index_body():
    """Nieuwe inhoud krijgt automatisch een nieuwe URL, ook bij oude browsercaches."""
    html=(WEB/'index.html').read_text(encoding='utf-8')
    for asset in ASSETS:
        version=hashlib.sha256(asset_body(asset)).hexdigest()[:16]
        html=html.replace('"'+asset+'"','"'+asset+'?v='+version+'"')
    return html.encode('utf-8')


class ActListHandler(SimpleHTTPRequestHandler):
    store=None
    detail=None
    eu_provider=None
    overview=None
    charts=None

    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(WEB),**kwargs)

    def log_message(self,format,*args):
        # Geen URL's met zoektermen of brontekst in de serverlog.
        pass

    def send(self,payload,status=200):
        payload=localize_payload(urlsplit(self.path).path,payload,getattr(self,'ui_language','nl'))
        body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)

    def end_headers(self):
        # Ook statische bestanden krijgen dezelfde beperking.
        if urlsplit(self.path).path in ('/',*ASSETS):
            self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def send_index(self,head=False):
        body=index_body()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        if not head:self.wfile.write(body)

    def send_file(self,body,content_type,filename):
        self.send_response(200)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)

    def do_POST(self):self.send({'fout':'Het dashboard is uitsluitend alleen-lezen.'},405)
    def do_PUT(self):self.do_POST()
    def do_PATCH(self):self.do_POST()
    def do_DELETE(self):self.do_POST()

    def do_GET(self):
        request=urlsplit(self.path)
        self.ui_language='nl'
        try:
            query=parse_qs(request.query,keep_blank_values=True,max_num_fields=50)
            languages=query.pop('ui_lang',['nl'])
            if len(languages)!=1 or languages[0] not in ('nl','en'):raise ValueError('Ongeldige interfacetaal.')
            self.ui_language=languages[0]
            request=request._replace(query=urlencode(query,doseq=True))
            if request.path=='/':return self.send_index()
            if request.path in ASSETS:
                if request.path=='/i18n.js':
                    body=asset_body(request.path)
                    self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8')
                    self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
                # Een eerder opgeslagen Last-Modified mag geen oude inhoud behouden.
                if 'If-Modified-Since' in self.headers:del self.headers['If-Modified-Since']
                return super().do_GET()
            if request.path=='/api/meta':
                payload=self.store.meta();payload['overview_available']=self.overview is not None
                payload['charts_available']=self.charts is not None and bool(self.store.analysis_projection)
                payload['charts']=[{'id':key,'title':value[0],'kind':value[1],'unit':value[2],'group':value[3],**chart_options(key)} for key,value in CHARTS.items()]
                return self.send(payload)
            chart_match=re.fullmatch(r'/api/chart/([a-z_]+)(?:/(export\.csv|export\.png|evidence))?',request.path)
            if chart_match:
                if self.charts is None:return self.send({'fout':'Grafieken zijn niet ingesteld.'},503)
                params=parse_qs(request.query,keep_blank_values=True,max_num_fields=40)
                if len(request.query)>6500 or any(len(v)!=1 for v in params.values()):raise ValueError('Ongeldige grafiekparameters.')
                top_value=params.pop('top',[None])[0]
                top=int(top_value) if top_value is not None else None
                point=params.pop('point',[''])[0]
                filters=ActFilters.from_params({k:v[0] for k,v in params.items()})
                chart,operation=chart_match[1],chart_match[2]
                if operation=='evidence':return self.send(self.charts.evidence(chart,point,filters))
                if chart in LARGE_CHARTS and top==0 and operation!='export.csv':
                    raise ValueError('Deze grote categorieënlijst is volledig beschikbaar via Volledige CSV; kies maximaal 50 voor de grafiek.')
                data=localize_chart(self.charts.get(chart,filters,top),self.ui_language)
                if operation=='export.csv':return self.send_file(csv_export(data),'text/csv; charset=utf-8',chart+'.csv')
                if operation=='export.png':return self.send_file(self.charts.image(chart,filters,top,'png',ui_language=self.ui_language),'image/png',chart+'.png')
                return self.send(data|{'svg':self.charts.image(chart,filters,top,ui_language=self.ui_language)})
            flow_match=re.fullmatch(r'/api/flow/act/(\d+)',request.path)
            if flow_match:
                if self.charts is None:return self.send({'fout':'Informatiestromen zijn niet ingesteld.'},503)
                params=parse_qs(request.query,keep_blank_values=True,max_num_fields=1)
                if set(params)-{'run_id'} or any(len(v)!=1 for v in params.values()):raise ValueError('Ongeldige actflowparameter.')
                run=int(params['run_id'][0]) if params.get('run_id',[''])[0] else None
                data=self.charts.flow_act(int(flow_match[1]),run)
                return self.send(data if data is not None else {'fout':'Act/run niet gevonden.'},200 if data is not None else 404)
            detail_match=re.fullmatch(r'/api/act/(\d+)(?:/(text|export\.md|export\.pdf))?',request.path)
            if detail_match:
                if self.detail is None:return self.send({'fout':'Actdetails zijn niet ingesteld.'},503)
                params=parse_qs(request.query,keep_blank_values=True,max_num_fields=3)
                if set(params)-{'run_id','variant'} or any(len(v)!=1 for v in params.values()):
                    raise ValueError('Ongeldige detailparameter.')
                act_id=int(detail_match[1]);run_id=int(params['run_id'][0]) if params.get('run_id',[''])[0] else None
                detail=self.detail.get(act_id,run_id)
                if detail is None:return self.send({'fout':'Geen actverdict gevonden voor deze act en run.'},404)
                operation=detail_match[2]
                if operation=='text':
                    return self.send(self.detail.text(act_id,run_id,params.get('variant',['raw'])[0]))
                if operation in ('export.md','export.pdf'):
                    text=self.detail.text(act_id,run_id,'raw')
                    body=markdown_export(detail,text,ui_language=self.ui_language) if operation=='export.md' else pdf_export(detail,text,ui_language=self.ui_language)
                    suffix='md' if operation=='export.md' else 'pdf'
                    numac=re.sub(r'[^A-Za-z0-9_-]','_',str(detail['act']['numac']))
                    return self.send_file(body,'text/markdown; charset=utf-8' if suffix=='md' else 'application/pdf',
                                          'act_'+numac+'_run_'+str(detail['run_id'])+'.'+suffix)
                return self.send(detail)
            eu_match=re.fullmatch(r'/api/eu/([A-Za-z0-9]{5,40})',request.path)
            if eu_match:
                if self.eu_provider is None:return self.send({'fout':'EU-bronverbinding is niet ingesteld.'},503)
                return self.send(self.eu_provider(eu_match[1]))
            if request.path in ('/api/acts','/api/overview'):
                if len(request.query)>6000:raise ValueError('Selectie is te lang.')
                params=parse_qs(request.query,keep_blank_values=True,max_num_fields=35)
                if any(len(v)!=1 for v in params.values()):raise ValueError('Dubbele filterparameter.')
                filters=ActFilters.from_params({k:v[0] for k,v in params.items()})
                if request.path=='/api/overview':
                    if self.overview is None:return self.send({'fout':'Overzicht is niet ingesteld.'},503)
                    return self.send(self.overview.get(filters))
                return self.send(self.store.list(filters))
            return self.send({'fout':'Onbekend pad.'},404)
        except ValueError as exc:self.send({'fout':str(exc)},400)
        except (CacheError,DataSourceError) as exc:self.send({'fout':str(exc)},503)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        except Exception:
            self.send({'fout':'De selectie kon niet worden geladen. Probeer opnieuw of start het dashboard opnieuw.'},500)

    def do_HEAD(self):
        path=urlsplit(self.path).path
        if path=='/':return self.send_index(head=True)
        if path not in ASSETS:
            return self.send_error(404)
        if 'If-Modified-Since' in self.headers:del self.headers['If-Modified-Since']
        super().do_HEAD()


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='AB-dashboard: alleen-lezen actlijst.')
    parser.add_argument('--ververs',action='store_true',help='Nieuwe registersnapshot maken vóór starten.')
    parser.add_argument('--alleen-verversen',action='store_true',help='Snapshot maken en stoppen.')
    parser.add_argument('--poort',type=int,default=8780)
    parser.add_argument('--geen-browser',action='store_true')
    parser.add_argument('--env')
    parser.add_argument('--cache-map')
    args=parser.parse_args(argv)
    if not 0<=args.poort<=65535:parser.error('Poort moet tussen 0 en 65535 liggen.')
    try:
        settings=Settings.load(args.env)
        root={'root':Path(args.cache_map)} if args.cache_map else {}
        if args.ververs or args.alleen_verversen:
            path,manifest=build_snapshot(settings,enrich=enrich_details,**root)
            store=ActListStore(path,manifest)
        else:store=ActListStore.load(settings,**root)
        if args.alleen_verversen:
            print('Actlijstsnapshot gecontroleerd:',store.manifest['snapshot_id']);return 0
        ActListHandler.store=store
        ActListHandler.overview=OverviewRepository(store,load_corpus(settings,store))
        try:eu_catalog=DashboardData(settings).snapshot()['eu_catalog']
        except CacheError:eu_catalog=[]
        ActListHandler.detail=DetailRepository(store,DetailTextProvider(settings,store.path.parent/'texts'),eu_catalog)
        ActListHandler.charts=ChartRepository(store,ActListHandler.overview,ActListHandler.detail)
        ActListHandler.eu_provider=staticmethod(DashboardData(settings).eu_text)
        server=ThreadingHTTPServer(('127.0.0.1',args.poort),ActListHandler)
        url=f'http://localhost:{server.server_port}/'
        print('AB-dashboard:',url,'· alleen-lezen · snapshot',store.manifest['source']['snapshot_utc'],flush=True)
        if not args.geen_browser:threading.Timer(.5,lambda:webbrowser.open(url)).start()
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
        return 0
    except (CacheError,ConfigurationError,DataSourceError,VerificationError,ValueError) as exc:
        print('Dashboard niet gestart: '+str(exc),file=sys.stderr);return 2
    except OSError:
        print('Dashboard niet gestart: bestand of lokale poort niet beschikbaar.',file=sys.stderr);return 2
