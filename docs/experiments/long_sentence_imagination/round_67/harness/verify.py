"""Independent fixture oracle; never provided to the system AI."""
import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-14_67회차'
def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
def expected(inputs, context):
    messages=load(inputs/'messages.json');cases=load(inputs/context);receipts=load(inputs/'receipts.json')
    plans=[];drafts=[]
    done={r['key'] for r in receipts if r['status']=='succeeded'}
    for c in cases:
        m=max((m for m in messages if m['visit_id']==c['id']),key=lambda m:datetime.fromisoformat(m['received_at'].replace('Z','+00:00')))
        cancelled=m['state']=='cancelled';route=None;departure=None
        routes=sorted((r for r in c['routes'] if r['walk']<=c['max_walk'] and r['cost']<=c['budget']),key=lambda r:(r['cost'],r['minutes'],r['id']))
        companion='본인 확정' if not c['self_busy'] else '누나 확정' if c['sister_reply']=='yes' else '동행 대기'
        if routes and not cancelled:
            route=routes[0]
            dt=datetime.fromisoformat(m['date'])+timedelta(minutes=m['minute']-c['arrival_buffer']-route['minutes']-(c['weather']['extra_minutes'] if c['weather']['rain'] else 0))
            departure={'date':dt.date().isoformat(),'minute':dt.hour*60+dt.minute}
        share='원문 충돌 확인 대기' if c['prescription']['text']!=c['visit_note']['text'] else '엄마 확인 대기' if not c['mother_confirmed'] else '공유 초안 준비'
        p={'id':c['id'],'message_id':m['id'],'date':m['date'],'minute':m['minute'],'cancelled':cancelled,
           'companion':'취소' if cancelled else companion,'route':None if not route else route['id'],'departure':departure,
           'reminder_date':None if cancelled else (datetime.fromisoformat(m['date'])-timedelta(days=1)).date().isoformat(),
           'questions':c['questions'],'prescription':c['prescription'],'visit_note':c['visit_note'],
           'share':'취소' if cancelled else share,'finish':'취소' if cancelled else '완료' if c['home_confirmed'] else '귀가 확인 대기',
           'cost':None if cancelled or not c['home_confirmed'] else sum(c['expenses']),
           'next_appointment':None if cancelled else c['next_appointment']}
        plans.append(p)
        if cancelled:continue
        kinds=[]
        if route and companion!='동행 대기':kinds.append('reminder')
        if share=='공유 초안 준비':kinds.append('share')
        for kind in kinds:
            key=f"{c['id']}:{kind}:{m['date']}:{m['minute']}"
            if key not in done:drafts.append(key)
    return plans,drafts

def normalized_agent(p):
    companion=p['companion'];route=p['route']
    who={'sister':'누나 확정','self':'본인 확정'}
    return {'id':p['visit_id'],'message_id':p['selected_message_id'],'date':p['appointment_date'],'minute':p['appointment_minute'],
            'cancelled':p['appointment_state']=='cancelled',
            'companion':'취소' if companion['status']=='cancelled' else who.get(companion.get('who'),'동행 대기'),
            'route':route.get('id') if route.get('status')=='selected' else None,
            'departure':{'date':p['departure_date'],'minute':p['departure_minute']} if p['departure_date'] else None,
            'reminder_date':p['eve_notice_date'],'questions':p['questions'],'prescription':p['prescription'],'visit_note':p['visit_note'],
            'share':{'ready':'공유 초안 준비','pending_mother_confirmation':'엄마 확인 대기','pending_guidance_check':'원문 충돌 확인 대기','cancelled':'취소'}.get(p['share_status'],p['share_status']),
            'finish':{'completed':'완료','pending_home_confirmation':'귀가 확인 대기','cancelled':'취소'}.get(p['closure_status'],p['closure_status']),
            'cost':p['cost_total'],'next_appointment':p['next_appointment']}

def verify(folder,context,inputs):
    raw=load(folder/'plan.json');draft=load(folder/'outbox.json');report=(folder/'report.md').read_text()
    agent=isinstance(raw,dict)
    if agent:
        actual=[normalized_agent(p) for p in raw['cases']];keys=[r['key'] for r in draft['drafts']]
    else:
        actual=[{**p,'route':p['route']['id'] if p['route'] else None} for p in raw];keys=[r['key'] for r in draft]
    exp,expkeys=expected(inputs,context);byid={p['id']:p for p in actual};errors=[]
    if len(byid)!=len(exp) or len(actual)!=len(exp):errors.append('case coverage/duplicate')
    for p in exp:
        a=byid.get(p['id'],{})
        for key,v in p.items():
            if a.get(key)!=v:errors.append({'id':p['id'],'field':key,'actual':a.get(key),'expected':v})
        if p['id'] not in report:errors.append('report missing '+p['id'])
    if sorted(keys)!=sorted(expkeys):errors.append({'drafts_actual':keys,'drafts_expected':expkeys})
    if len(set(keys))!=len(keys):errors.append('duplicate drafts')
    return {'folder':str(folder),'cases':len(actual),'drafts':len(keys),'passed':not errors,'errors':errors,
            'output_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--context',default='context.json');parser.add_argument('--inputs',default=str(OUT/'inputs'));a=parser.parse_args()
    result=verify(Path(a.folder),a.context,Path(a.inputs));print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['passed'] else 1)
