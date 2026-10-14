"""Create synthetic, non-medical coordination fixtures; no production state changes."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-14_67회차'
DOC = Path(__file__).resolve().parents[1]
def save(path, obj, bom=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8-sig' if bom else 'utf-8')

cases=[]; messages=[]
for i in range(8):
    cid=f'V{i+1:02}'
    case={'id':cid,'max_walk':150,'budget':30000,'arrival_buffer':20,
          'self_busy':True,'sister_reply':'yes','questions':['지난 진료 이후 변화 확인','다음 방문 준비물 확인'],
          'routes':[{'id':'bus','minutes':45,'walk':400,'cost':1500},{'id':'taxi','minutes':35,'walk':30,'cost':18000}],
          'weather':{'rain':True,'extra_minutes':10,'source':'weather-'+cid},
          'prescription':{'text':'가상약 A: 원문 안내 확인 필요','source':'rx-'+cid},
          'visit_note':{'text':'가상약 A: 원문 안내 확인 필요','source':'note-'+cid},
          'mother_confirmed':True,'home_confirmed':True,'expenses':[18000,5000],
          'next_appointment':'2026-11-18T10:00:00+09:00'}
    cases.append(case)
    messages.extend([{'visit_id':cid,'id':cid+'-old','received_at':'2026-10-13T08:00:00+09:00','state':'booked','date':'2026-10-21','minute':600,'place':'가상병원'},
                     {'visit_id':cid,'id':cid+'-new','received_at':'2026-10-13T00:30:00Z','state':'booked','date':'2026-11-01','minute':540,'place':'가상병원'}])
cases[1]['sister_reply']=None
cases[2]['routes']=cases[2]['routes'][:1]
cases[3]['visit_note']['text']='가상약 A: 다른 안내가 적혀 있음'
cases[4]['mother_confirmed']=False
cases[5]['home_confirmed']=False
messages[-3]['state']='cancelled' # V07 newest
messages[-1]['minute']=20 # V08 departure crosses preceding month/day
# A successful earlier delivery and a failed attempt; only the successful key suppresses a draft.
receipts=[{'key':'V01:reminder:2026-11-01:540','status':'succeeded'},
          {'key':'V03:reminder:2026-11-01:540','status':'failed'}]
save(OUT/'inputs/messages.json',messages,True)
save(OUT/'inputs/context.json',cases)
save(OUT/'inputs/receipts.json',receipts)
variant=copy.deepcopy(cases)
variant[1]['sister_reply']='yes'; variant[2]['max_walk']=500
variant[3]['visit_note']=copy.deepcopy(variant[3]['prescription'])
variant[4]['mother_confirmed']=True; variant[5]['home_confirmed']=True
save(OUT/'inputs/context_variant.json',list(reversed(variant)))
# Plain encoding equivalent for an independent reader boundary diagnostic.
save(OUT/'inputs/messages_plain.json',messages)
request=(DOC/'request.txt').read_text()
(OUT/'task.md').write_text((DOC/'task.md').read_text())
base=f'\n입력 폴더: {OUT}/inputs. 사용할 입력은 messages.json, context.json, receipts.json 세 파일이다. 출력 폴더: {OUT}/agent/base. 다른 실행자의 trainer/harness/drafts와 정답·보고서는 보지 마. 일반 교재와 도구 계약은 조회해도 된다.'
save(OUT/'ai_base.request.json',{'message':request+base,'origin':'training','background':True})
save(OUT/'describe.request.json',{'code':'','edition':2,'describe':['self:read','self:write','table:sort'],'origin':'training','project_id':'수동모드'})
print(OUT)
