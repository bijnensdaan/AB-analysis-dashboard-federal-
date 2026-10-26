"""Open het lokale dashboard; hergebruik een bestaande server op de vaste poort."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
URL='http://localhost:8780/#overview'


def server_status():
    """Maak onderscheid tussen ons dashboard, een vrije poort en een ander proces."""
    try:
        with socket.create_connection(('127.0.0.1',8780),timeout=.5):pass
    except OSError:
        return 'absent'
    try:
        with urlopen('http://127.0.0.1:8780/api/meta',timeout=3) as response:
            meta=json.load(response)
        if (isinstance(meta,dict) and isinstance(meta.get('options'),dict)
                and isinstance(meta.get('control',{}).get('acts'),int)
                and isinstance(meta.get('snapshot_id'),str)):
            return 'dashboard'
    except (OSError,ValueError,TypeError):pass
    return 'other'


def ensure_running(wait_seconds=30):
    status=server_status()
    if status=='dashboard':return False
    if status=='other':raise RuntimeError('Poort 8780 wordt gebruikt door een andere of niet-reagerende toepassing. Er is geen proces gestopt.')
    temporary=ROOT/'tmp';temporary.mkdir(exist_ok=True)
    lock=temporary/'dashboard-start.lock'
    deadline=time.monotonic()+wait_seconds
    while True:
        try:
            handle=lock.open('x',encoding='utf-8')
            break
        except FileExistsError:
            if server_status()=='dashboard':return False
            try:
                if time.time()-lock.stat().st_mtime>60:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:continue
            if time.monotonic()>=deadline:raise RuntimeError('Een eerdere start is nog bezig. Probeer het opnieuw; zie tmp/dashboard-start.log.')
            time.sleep(.2)
    try:
        with handle:handle.write(str(time.time()))
        # Een andere start kan tussen de eerste controle en het slot klaar zijn.
        status=server_status()
        if status=='dashboard':return False
        if status=='other':raise RuntimeError('Poort 8780 is bezet. Er is geen proces gestopt.')
        with (temporary/'dashboard-start.log').open('ab') as log:
            process=subprocess.Popen([sys.executable,'-B',str(ROOT/'validatietool/start_dashboard.py'),
                '--geen-browser','--poort','8780'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        while time.monotonic()<deadline:
            if server_status()=='dashboard':return True
            if process.poll() is not None:raise RuntimeError('Het dashboard kon niet starten. Zie tmp/dashboard-start.log.')
            time.sleep(.2)
        raise RuntimeError('Het dashboard is nog niet bereikbaar. Zie tmp/dashboard-start.log.')
    finally:
        lock.unlink(missing_ok=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geen-browser',action='store_true',help='Controleer/start zonder een browsertab te openen.')
    args=parser.parse_args(argv)
    try:
        started=ensure_running()
        if not args.geen_browser:webbrowser.open(URL)
        if sys.stdout:print(('Dashboard gestart: ' if started else 'Dashboard draait al: ')+URL)
        return 0
    except (OSError,RuntimeError) as exc:
        message=str(exc)
        if sys.stderr:print(message,file=sys.stderr)
        elif sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,message,'Dashboard niet gestart',16)
        return 1


if __name__=='__main__':raise SystemExit(main())
