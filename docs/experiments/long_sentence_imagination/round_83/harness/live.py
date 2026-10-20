"""Finite command submission/polling; never launches a dependent turn automatically."""
import argparse
import datetime
import json
from pathlib import Path
import urllib.request
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-20_83회차'

def api(path, value=None, timeout=35):
    req=urllib.request.Request('http://localhost:8765'+path,
        data=None if value is None else json.dumps(value).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req,timeout=timeout))

def save(name,value):
    p=OUT/'runs'/f'{name}.json';p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2));return p

p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('name');p.add_argument('--turn',type=int,default=1);p.add_argument('--neutral',action='store_true');p.add_argument('--fresh',action='store_true');a=p.parse_args()
agents=json.loads((OUT/'agents.json').read_text())
label=f'{a.name}_t{a.turn}'
if a.action=='submit':
    if a.turn>1 and not a.fresh:
        prev=json.loads((OUT/'runs'/f'{a.name}_t{a.turn-1}_result.json').read_text())
        assert prev.get('state') in ('succeeded','failed'),prev
    reqs=json.loads((OUT/'requests.json').read_text())
    request=reqs[a.turn-1] if a.turn<=3 else '외부 타이머 콘센트는 쓰지 않을 거야. 정해진 시간이 지나면 쿠커 자체가 꺼져야 해. 분리해서 물세척할 수 있고 조작이 쉬우며 후기가 충분해야 한다는 조건은 그대로야.'
    if a.neutral and a.turn==3:request='앞서 말한 조건으로 다른 제품도 더 찾아서 비교해줘.'
    mode='think' if 'think' in a.name else 'execute'
    output=OUT/'ai'/a.name/f't{a.turn}.md';output.parent.mkdir(parents=True,exist_ok=True)
    scope=f'제공된 가상 시장 자료 {OUT / "inputs"} 를 사용해 판단해줘. 시작 자료는 index.json이야.' if not a.name.startswith('web') else '공개 웹 자료를 실제 조회해서 판단하고 근거 링크를 제시해줘.'
    command=f'#{mode} {request}\n{scope} 네 이전 결과는 재사용해도 돼. 다른 실행자의 결과나 trainer·harness·정답 자료는 읽지 마. 조회와 지정 출력 파일 저장만 하고 구매·결제·문의 발송·예약은 하지 마. 비교 결과를 간결하게 답하고 {output} 에도 저장해줘.'
    body={'command':command,'origin':'training','background':True}
    save(label+'_request',body)
    result=api(f'/projects/L83_training/agents/{agents[a.name]["id"]}/command',body)
    result['recorded_at']=datetime.datetime.now().astimezone().isoformat();save(label+'_accepted',result);print(json.dumps(result,ensure_ascii=False))
elif a.action=='poll':
    ticket=json.loads((OUT/'runs'/f'{label}_accepted.json').read_text())
    result=api(ticket['status_url']+'?wait=20')
    if result.get('state') in ('succeeded','failed','cancelled'):save(label+'_result',result)
    else:save(label+'_latest',result)
    print(json.dumps(result,ensure_ascii=False)[:6500])
