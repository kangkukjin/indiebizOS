"""Finite HTTP transport and evidence collection, not the task solution."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import datetime
import json
import sqlite3
import time
import urllib.request
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-23_96회차'
RUNS = OUT / 'runs'
PROJECT = 'L96_starcraft_ai'
TERMINAL = ('succeeded', 'failed', 'cancelled', 'interrupted')


def save(name, value):
    (RUNS / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def api(path, body=None):
    request = urllib.request.Request('http://127.0.0.1:8765' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=55) as response:
        return json.load(response)


def deadline():
    limit = datetime.datetime.fromisoformat(json.loads((OUT / 'start.json').read_text())['deadline'])
    assert datetime.datetime.now().astimezone() < limit, 'training deadline reached'


def create():
    deadline()
    assert not (RUNS / 'agent.json').exists()
    save('project.json', api('/projects', {'name': PROJECT}))
    result = api(f'/projects/{PROJECT}/agents', {'name': '전투재현',
        'role': '지정된 시험 자료의 검수와 후속 재개를 수행한다. 원문 요청의 범위·출력·완료 기준을 지킨다. '
                '외부 발송·예약·구매·배포·설정·제품 코드 변경 없이 지정 폴더에서 수행한다.'})
    save('agent.json', result['agent'])
    save('start_agent.json', api(f'/projects/{PROJECT}/agents/{result["agent"]["id"]}/start', {}))
    print('created', result['agent']['id'])


def submit(turn):
    deadline()
    assert not (RUNS / f'ai_T{turn}_accepted.json').exists(), 'recover existing request'
    if turn == 2:
        assert json.loads((RUNS / 'ai_T1_result.json').read_text())['state'] in TERMINAL
    task = (HERE / 'task.md').read_text()
    heading = '## 자연어 요청 원문' if turn == 1 else '## 후속 요청 원문'
    message = task.split(heading + '\n', 1)[1].split('\n## ', 1)[0].strip()
    message += (f'\n입력 폴더: {OUT/"ai/inputs"}. 출력 폴더: {OUT/"ai/artifacts"}. '
                '공식 웹 자료 사본과 합성 시험 조건이다. 자기 입력·출력만 읽고, 새 작업 파일과 임시 파일도 자기 출력 폴더 안에만 써 줘. '
                '다른 실행자의 trainer/reference/runs, docs/experiments의 초안·해법·정답은 읽지 마. '
                '네 자신의 직전 결과·절차·중간 참조는 재사용할 수 있어. 필요한 검수·파일 생성은 '
                '이미 요청한 작업이므로 별도 승인 질문 없이 수행해 줘.')
    agent = json.loads((RUNS / 'agent.json').read_text())
    body = {'command': message, 'origin': 'training', 'background': True}
    save(f'ai_T{turn}_request.json', body)
    result = api(f'/projects/{PROJECT}/agents/{agent["id"]}/command', body)
    save(f'ai_T{turn}_accepted.json', result)
    print(json.dumps(result, ensure_ascii=False))


def poll(turn):
    ticket = json.loads((RUNS / f'ai_T{turn}_accepted.json').read_text())
    result = api(ticket['status_url'] + '?wait=20')
    terminal = result.get('state') in TERMINAL
    save(f'ai_T{turn}_' + ('result.json' if terminal else 'latest.json'), result)
    print(json.dumps(result, ensure_ascii=False)[:6500])


def lifecycle(action):
    agent = json.loads((RUNS / 'agent.json').read_text())
    result = api(f'/projects/{PROJECT}/agents/{agent["id"]}/{action}', {})
    save(f'{action}_{time.time_ns()}.json', result)
    print(json.dumps(result, ensure_ascii=False))


def trainer(label):
    deadline()
    body = json.loads((RUNS / f'{label}_request.json').read_text())
    assert not (RUNS / f'{label}_result.json').exists(), 'recover existing result'
    checked = api('/ibl/execute', {**body, 'check': True})
    save(f'{label}_check.json', checked)
    if not checked.get('ok'):
        print(json.dumps(checked, ensure_ascii=False)[:10000])
        return
    began = time.monotonic()
    result = api('/ibl/execute', body)
    save(f'{label}_result.json', result)
    save(f'{label}_timing.json', {'wall_s': time.monotonic()-began})
    print(json.dumps({k:v for k,v in result.items() if k in ('success','diagnostic','resume','value','reuse')}, ensure_ascii=False)[:12000])


def capture():
    db = sqlite3.connect(f'file:{ROOT/"data/world_pulse.db"}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    summaries = []
    for turn in (1, 2):
        path = RUNS / f'ai_T{turn}_accepted.json'
        if not path.exists():
            continue
        ticket = json.loads(path.read_text())
        events, episodes = [], []
        usage = defaultdict(Counter)
        for row in db.execute('select id,source,task_id,run_id,total_ms,ended_at from episode_log where task_id=?', (ticket['task_id'],)):
            ep = dict(row)
            episodes.append(ep)
            for event in db.execute('select event_seq,kind,data from trajectory_event where episode_id=? order by event_seq', (ep['id'],)):
                data = json.loads(event['data'])
                kind = event['kind']
                if kind == 'model.usage' and data.get('accounting') == 'billable_usage':
                    for key in ('input', 'output', 'cache_read', 'cache_create'):
                        if isinstance(data.get(key), (int, float)):
                            usage[data.get('role', 'unknown')][key] += data[key]
                events.append({'episode': ep['id'], 'seq': event['event_seq'], 'kind': kind, 'data': data})
        save(f'ai_T{turn}_events.json', events)
        summaries.append({'turn': turn, 'task_id': ticket['task_id'], 'episodes': episodes,
                          'usage': {k: dict(v) for k, v in usage.items()}})
    db.close()
    save('episodes.json', summaries)
    print(json.dumps(summaries, ensure_ascii=False))



if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'create':
        create()
    elif action == 'submit':
        submit(int(sys.argv[2]))
    elif action == 'poll':
        poll(int(sys.argv[2]))
    elif action in ('stop', 'start'):
        lifecycle(action)
    elif action == 'ibl':
        trainer(sys.argv[2])
    elif action == 'capture':
        capture()
