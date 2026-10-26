"""Detailmetadata als uitbreiding IN dezelfde transactie en lokale snapshot als de lijst."""
from pathlib import Path

from .cache import canonical
from ..logic.metrics import require

SQL=Path(__file__).with_name('detail_sql')
KEYS={'act':('act_id',),'verdict':('act_id','run_id'),'reading':('reading_id',),
      'duty':('duty_id',),'claim':('obligation_id',),'review':('decision_id',),
      'text_metadata':('act_id',),'io_type':('io_id',),'admin_action':('aa_id',),
      'admin_action_io_link':('aa_id','io_id'),'cost_category':('code',)}


def enrich_details(source,local,manifest):
    """Alleen bron-SELECT; JSON-veldtypen en oorspronkelijke motiveringen behouden."""
    local.execute('CREATE TABLE detail_records(kind TEXT,key TEXT,act_id INTEGER,run_id INTEGER,data TEXT,PRIMARY KEY(kind,key))')
    counts={}
    for part in (SQL/'source.sql').read_text(encoding='utf-8').split('-- @query ')[1:]:
        kind,query=part.strip().split('\n',1)
        count=0
        with source.connection.cursor(name='detail_'+kind) as cursor:
            cursor.itersize=300;cursor.execute(query)
            while True:
                rows=cursor.fetchmany(300)
                if not rows:break
                columns=[c.name for c in cursor.description]
                prepared=[]
                for row in rows:
                    item=dict(zip(columns,row))
                    key=':'.join(str(item[k]) for k in KEYS[kind])
                    prepared.append((kind,key,item.get('act_id'),item.get('run_id'),canonical(item).decode('utf-8')))
                local.executemany('INSERT INTO detail_records VALUES (?,?,?,?,?)',prepared)
                count+=len(prepared)
        counts[kind]=count
        print('Actdetailmetadata:',kind,count,flush=True)
    local.execute('CREATE INDEX detail_act ON detail_records(kind,act_id,run_id)')
    for detail,table in [('act','acts'),('verdict','verdicts'),('reading','readings'),('duty','duties'),('claim','claims')]:
        require(counts[detail]==manifest['tables'][table],'Detailmetadata en actlijst verschillen bij '+detail+'.')
    manifest['details_available']=True
    manifest['detail_format']=1
    manifest['detail_counts']=counts
