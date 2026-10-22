"""Finite rehearsal transport; no business solution is given to the model."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: F401,E402
import datetime
import json
import shutil
import urllib.request

HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_94회차'
REPAIR = '--repair' in sys.argv
PLAN_FIX = '--plan-fix' in sys.argv
PROJECT = 'L94_repair_ai' if REPAIR else 'L94_ai'
LANE = 'ai_repair' if REPAIR else 'ai'
TRAINER = 'trainer_repair' if REPAIR else 'trainer'
RUNS = OUT / 'runs' / ('repair' if REPAIR else 'baseline')
# Baseline evidence predates the phase split.
if not REPAIR:
    RUNS = OUT / 'runs'
if PLAN_FIX:
    TRAINER = 'trainer_final'
    RUNS = OUT / 'runs/plan_fix'
PROGRAM = HERE / ('main_v2.ibl' if PLAN_FIX else 'main_v1.ibl')


def save(name, value):
    (RUNS / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))


def api(path, body=None):
    request = urllib.request.Request('http://127.0.0.1:8765' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=55) as response:
        return json.load(response)


def deadline():
    limit = datetime.datetime.fromisoformat(json.loads((OUT / 'start.json').read_text())['deadline'])
    assert datetime.datetime.now().astimezone() < limit, 'training deadline'


def create():
    deadline()
    if REPAIR:
        RUNS.mkdir(parents=True, exist_ok=True)
        for lane in (LANE, TRAINER):
            (OUT/lane/'inputs').mkdir(parents=True, exist_ok=True)
            (OUT/lane/'artifacts').mkdir(exist_ok=True)
            for name in ('A.json', 'B.json', 'manifest.json'):
                shutil.copyfile(OUT/'ai/inputs'/name, OUT/lane/'inputs'/name)
    assert not (RUNS / 'agent.json').exists()
    save('project.json', api('/projects', {'name': PROJECT}))
    result = api(f'/projects/{PROJECT}/agents', {'name': '계획실행',
        'role': '주어진 자료 검수와 계획 수행을 맡는 훈련 에이전트다. '
                '원문 요청의 입력·출력·범위·완료 조건을 지킨다. '
                '외부 발송·예약·구매·배포·설정 변경 없이 지정된 폴더에서 수행한다.'})
    save('agent.json', result['agent'])
    save('start_agent.json', api(f'/projects/{PROJECT}/agents/{result["agent"]["id"]}/start', {}))
    print('created', result['agent']['id'])


def request(turn):
    task = (HERE / 'task.md').read_text()
    heading = '## 자연어 요청 원문' if turn == 1 else '## 후속 요청 원문'
    message = task.split(heading + '\n', 1)[1].split('\n## ', 1)[0].strip()
    return message + (f'\n입력 폴더: {OUT/LANE/"inputs"}. 출력 폴더: {OUT/LANE/"artifacts"}. '
        '다른 실행자의 ai/ai_repair/trainer/trainer_repair/reference/runs 및 docs/experiments는 읽지 마. '
        '훈련 합성 자료이며 실제 출고·발송은 하지 마. 필요한 계획 작성과 파일 검수·생성은 '
        '이미 요청한 작업이므로 별도 계획 승인 질문 없이 진행해 줘.')


def submit(turn):
    deadline()
    ticket = RUNS / f'ai_T{turn}_accepted.json'
    assert not ticket.exists(), 'recover existing request'
    if turn == 2:
        previous = json.loads((RUNS / 'ai_T1_result.json').read_text())
        assert previous['state'] in ('succeeded', 'failed')
        snapshot = {}
        for p in (OUT / LANE / 'artifacts').rglob('*'):
            if p.is_file():
                import hashlib
                snapshot[str(p.relative_to(OUT/LANE/'artifacts'))] = {
                    'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'mtime_ns': p.stat().st_mtime_ns}
        save('ai_T1_files.json', snapshot)
        shutil.copyfile(OUT / 'reference/C.json', OUT / LANE / 'inputs/C.json')
    agent = json.loads((RUNS / 'agent.json').read_text())
    body = {'command': request(turn), 'origin': 'training', 'background': True}
    save(f'ai_T{turn}_request.json', body)
    result = api(f'/projects/{PROJECT}/agents/{agent["id"]}/command', body)
    save(ticket.name, result)
    print(json.dumps(result, ensure_ascii=False))


def poll(turn):
    ticket = json.loads((RUNS/f'ai_T{turn}_accepted.json').read_text())
    result = api(ticket['status_url'] + '?wait=20')
    terminal = result.get('state') in ('succeeded', 'failed', 'cancelled', 'interrupted')
    save(f'ai_T{turn}_' + ('result.json' if terminal else 'latest.json'), result)
    if terminal:
        states = {str(p.relative_to(ROOT)): json.loads(p.read_text())
                  for p in (ROOT/'projects'/PROJECT).rglob('*todo_state.json')}
        save(f'ai_T{turn}_todo_states.json', states)
    print(json.dumps(result, ensure_ascii=False)[:5000])


def stop():
    agent = json.loads((RUNS/'agent.json').read_text())
    save('stop_agent.json', api(f'/projects/{PROJECT}/agents/{agent["id"]}/stop', {}))
    print('stopped')


def start():
    agent = json.loads((RUNS/'agent.json').read_text())
    result = api(f'/projects/{PROJECT}/agents/{agent["id"]}/start', {})
    save('restart_agent.json', result)
    print('started')


def ibl(turn):
    deadline()
    if PLAN_FIX and turn == 1:
        RUNS.mkdir(parents=True, exist_ok=True)
        assert not (OUT/TRAINER).exists()
        (OUT/TRAINER/'inputs').mkdir(parents=True)
        (OUT/TRAINER/'artifacts').mkdir()
        for name in ('A.json', 'B.json', 'manifest.json'):
            shutil.copyfile(HERE/'fixtures'/name, OUT/TRAINER/'inputs'/name)
    if turn == 2:
        shutil.copyfile(OUT/'reference/C.json', OUT/TRAINER/'inputs/C.json')
    request_body = {'code': PROGRAM.read_text(), 'edition': 2,
        'project_id': str(ROOT), 'origin': 'training',
        'inputs': {'입력': str(OUT/TRAINER/'inputs'), '출력': str(OUT/TRAINER/'artifacts'), '판본': turn}}
    save(f'trainer_T{turn}_request.json', request_body)
    checked = api('/ibl/execute', {**request_body, 'check': True})
    save(f'trainer_T{turn}_check.json', checked)
    if not checked.get('ok'):
        print(json.dumps(checked, ensure_ascii=False)[:5000])
        return
    result = api('/ibl/execute', request_body)
    save(f'trainer_T{turn}_result.json', result)
    if turn == 1:
        import hashlib
        save('trainer_T1_files.json', {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
             'mtime_ns': p.stat().st_mtime_ns} for p in (OUT/TRAINER/'artifacts').glob('[AB].json')})
    print(json.dumps({k: result[k] for k in ('success', 'diagnostic', 'value', 'resume') if k in result}, ensure_ascii=False)[:4500])


def capture():
    import sqlite3
    from collections import defaultdict, Counter
    db = sqlite3.connect(f'file:{ROOT/"data/world_pulse.db"}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    summaries = []
    for turn in (1, 2):
        ticket = json.loads((RUNS/f'ai_T{turn}_accepted.json').read_text())
        task = ticket['task_id']
        events, episodes = [], []
        usage = defaultdict(Counter)
        for row in db.execute('select id,source,task_id,run_id,total_ms,ended_at from episode_log where task_id=?', (task,)):
            ep = dict(row)
            episodes.append(ep)
            for event in db.execute('select event_seq,kind,data from trajectory_event where episode_id=? order by event_seq', (ep['id'],)):
                data = json.loads(event['data'])
                kind = event['kind']
                if kind == 'model.usage' and data.get('accounting') == 'billable_usage':
                    for key in ('input', 'output', 'cache_read', 'cache_create'):
                        if isinstance(data.get(key), (int, float)):
                            usage[data.get('role', 'unknown')][key] += data[key]
                if kind in ('supervision.tool.started', 'supervision.tool.finished',
                            'supervision.evaluation.finished', 'supervision.tool.supervisor',
                            'model.usage', 'model.round', 'context.compacted',
                            'recall.presented', 'recall.used', 'cognition.route'):
                    events.append({'episode': ep['id'], 'seq': event['event_seq'], 'kind': kind, 'data': data})
        save(f'ai_T{turn}_events.json', events)
        summaries.append({'turn': turn, 'task_id': task, 'episodes': episodes,
                          'usage': {k: dict(v) for k, v in usage.items()}})
    db.close()
    save('episodes.json', summaries)
    print(json.dumps(summaries, ensure_ascii=False))


def variant():
    deadline()
    lane = OUT / ('trainer_final_invalid' if PLAN_FIX else 'trainer_invalid')
    assert not lane.exists()
    shutil.copytree(HERE/'fixtures', lane/'inputs')
    (lane/'artifacts').mkdir()
    (lane/'inputs/C.json').write_text(json.dumps({'items': [{'id': 'c1', 'qty': -1, 'price': 6}]}))
    body = {'code': PROGRAM.read_text(), 'edition': 2, 'origin': 'training',
            'project_id': str(ROOT), 'inputs': {'입력': str(lane/'inputs'),
                                               '출력': str(lane/'artifacts'), '판본': 1}}
    save('trainer_invalid_request.json', body)
    checked = api('/ibl/execute', {**body, 'check': True})
    save('trainer_invalid_check.json', checked)
    assert checked.get('ok'), checked
    result = api('/ibl/execute', body)
    save('trainer_invalid_result.json', result)
    assert result['success'] and not result['value']['ready']
    assert not (lane/'artifacts/final.json').exists()
    assert [s['status'] for s in result['value']['steps']] == [
        'completed', 'completed', 'completed', 'blocked', 'blocked']
    print('invalid C isolated, A/B completed, final withheld', result.get('resume'))


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'create':
        create()
    elif action == 'submit':
        submit(int(sys.argv[2]))
    elif action == 'poll':
        poll(int(sys.argv[2]))
    elif action == 'stop':
        stop()
    elif action == 'start':
        start()
    elif action == 'ibl':
        ibl(int(sys.argv[2]))
    elif action == 'capture':
        capture()
    elif action == 'variant':
        variant()
