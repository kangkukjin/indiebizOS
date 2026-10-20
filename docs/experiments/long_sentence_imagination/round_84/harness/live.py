"""84회차 독립 AI 대화 접수·회수. 유한 대기, 종속 턴 자동 발사 없음.
사용: live.py init | submit <agent> <turn> | poll <agent> <turn>
turn: 1..5, 5b(운영자 답), v(변형), p(탐침: T5에서 대상 확인 문구 제거)"""
import argparse, datetime, json, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-20_84회차'
API = 'http://localhost:8765'
def api(path, value=None, timeout=35):
    req = urllib.request.Request(API + path, data=None if value is None else json.dumps(value).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=timeout))
def save(name, value):
    p = OUT / 'runs' / f'{name}.json'; p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)); return p
ORDER = ['1', '2', '3', '4', '5', '5b', 'v']
p = argparse.ArgumentParser(); p.add_argument('action'); p.add_argument('name', nargs='?'); p.add_argument('turn', nargs='?', default='1'); a = p.parse_args()
if a.action == 'init':
    role = '사용자 요청을 자료 근거에 맞게 수행하고 결과를 간결하게 전달한다. 이 세션은 자료 조회와 지정 출력 폴더 쓰기만 하는 훈련이다. 발송·구매·결제·예약·설정 변경은 하지 않는다.'
    project = api('/projects', {'name': 'L84_training'}); save('project', project)
    agents = {}
    for name in ['ai_execute', 'ai_probe']:
        data = api(f"/projects/{project['id']}/agents", {'name': name, 'role': role, 'allowed_nodes': ['sense', 'self', 'table']})
        agents[name] = {'id': data['agent']['id'], 'name': name}
    (OUT / 'agents.json').write_text(json.dumps({'project_id': project['id'], 'agents': agents}, ensure_ascii=False, indent=2)); print(json.dumps(agents)); raise SystemExit
meta = json.loads((OUT / 'agents.json').read_text()); reqs = json.loads((OUT / 'requests.json').read_text())
label = f'{a.name}_t{a.turn}'
if a.action == 'submit':
    idx = ORDER.index(a.turn) if a.turn in ORDER else None
    if idx and idx > 0:
        prev = json.loads((OUT / 'runs' / f'{a.name}_t{ORDER[idx-1]}_result.json').read_text())
        assert prev.get('state') in ('succeeded', 'failed'), prev.get('state')
    if a.turn in ('1', '2', '3', '4', '5'): text = reqs['turns'][int(a.turn) - 1]
    elif a.turn == '5b': text = reqs['t5_answer']
    elif a.turn == 'v': text = reqs['variant']
    elif a.turn == 'p': text = reqs['turns'][4].replace(' 먼저 어느 집단을 뜻하는지는 확인해 주세요.', '')
    else: raise SystemExit('unknown turn')
    outdir = OUT / 'ai' / a.name; outdir.mkdir(parents=True, exist_ok=True)
    scope = f"\n자료는 {OUT/'inputs'} 에 있는 사본이고 README.md가 색인이야. 산출물은 {outdir} 폴더에 저장해 줘. 네 이전 결과는 재사용해도 되지만 다른 실행자의 결과나 trainer·harness·reference 자료는 읽지 마. 실제 발송·구매·예약은 하지 말고 자료 조회와 지정 폴더 쓰기만 해."
    command = '#execute ' + text + (scope if a.turn == '1' else '')
    body = {'command': command, 'origin': 'training', 'background': True}
    save(label + '_request', body)
    result = api(f"/projects/{meta['project_id']}/agents/{meta['agents'][a.name]['id']}/command", body)
    result['recorded_at'] = datetime.datetime.now().astimezone().isoformat(); save(label + '_accepted', result); print(json.dumps(result, ensure_ascii=False))
elif a.action == 'poll':
    ticket = json.loads((OUT / 'runs' / f'{label}_accepted.json').read_text())
    result = api(ticket['status_url'] + '?wait=20', timeout=40)
    result['polled_at'] = datetime.datetime.now().astimezone().isoformat()
    if result.get('state') in ('succeeded', 'failed', 'cancelled'): save(label + '_result', result)
    else: save(label + '_latest', result)
    print(json.dumps({k: result.get(k) for k in ('state', 'task_id', 'polled_at')}, ensure_ascii=False)); print(str(result.get('result'))[:5000])
