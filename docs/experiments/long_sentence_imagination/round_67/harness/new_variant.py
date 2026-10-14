"""Additional whole-program variant: year rollover, no route, retained provenance."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-14_67회차'
new=OUT/'inputs_new';new.mkdir(exist_ok=True)
def load(name):
    return json.loads((OUT/'inputs'/name).read_text(encoding='utf-8-sig'))
messages=load('messages.json');cases=load('context_variant.json');receipts=load('receipts.json')
for row in messages:
    if row['id']=='V01-new':row.update(date='2027-01-01',minute=5)
for row in cases:
    if row['id']=='V01':row['weather']['rain']=False
    if row['id']=='V02':row['self_busy']=False
    if row['id']=='V03':row['routes']=[]
    if row['id']=='V04':
        row['prescription']['text']='원문 안\\r\\n줄바꿈과 \ufeff표식'
        row['visit_note']['text']=row['prescription']['text']
    if row['id']=='V06':row['home_confirmed']=False
for name,value in [('messages',messages),('context',cases),('receipts',receipts+receipts[:1])]:
    (new/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8-sig' if name=='messages' else 'utf-8')
