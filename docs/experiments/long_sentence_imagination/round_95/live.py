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
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-23_95회차'
RUNS = OUT / 'runs'
PROJECT = 'L95_harness_ai'
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
    result = api(f'/projects/{PROJECT}/agents', {'name': '인수검사',
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
                '합성 훈련 자료다. 자기 입력·출력만 읽고, 새 작업 파일과 임시 파일도 자기 출력 폴더 안에만 써 줘. '
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


def trainer(turn, version):
    deadline()
    tag = f'trainer_T{turn}_v{version}'
    assert not (RUNS / f'{tag}_result.json').exists(), 'do not rerun completed execution'
    body = {'code': (HERE / f'main_v{version}.ibl').read_text(), 'edition': 2,
            'project_id': str(ROOT), 'origin': 'training',
            'inputs': {'입력': str(OUT / 'trainer/inputs'),
                       '출력': str(OUT / 'trainer/artifacts'), '판본': turn}}
    if turn == 2:
        old = json.loads((RUNS / f'trainer_T1_v{version}_result.json').read_text())
        body['reuse'] = {'run_id': old['resume']['run_id']}
    elif version == 2:
        old = json.loads((RUNS / 'trainer_T1_v1_result.json').read_text())
        body['reuse'] = {'run_id': old['resume']['run_id']}
    save(f'{tag}_request.json', body)
    checked = api('/ibl/execute', {**body, 'check': True})
    save(f'{tag}_check.json', checked)
    if not checked.get('ok'):
        print(json.dumps(checked, ensure_ascii=False)[:9000])
        return
    started = time.monotonic()
    result = api('/ibl/execute', body)
    save(f'{tag}_result.json', result)
    save(f'{tag}_timing.json', {'wall_s': time.monotonic() - started})
    print(json.dumps({k: result[k] for k in ('success', 'diagnostic', 'resume', 'reuse', 'value')
                      if k in result}, ensure_ascii=False)[:6000])


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


def probes():
    import shutil
    from prepare import dump, good
    deadline()
    assert not (OUT / 'positive').exists()
    results = []
    for label in ('positive', 'empty', 'missing_source'):
        lane = OUT / label
        shutil.copytree(OUT / 'trainer/inputs', lane / 'inputs',
                        ignore=(lambda path, names: ['J01.json'] if label == 'missing_source'
                                and Path(path).name == 'source' else []))
        (lane / 'artifacts').mkdir()
        for n in range(1, 25):
            value = good(n)
            value['compat'] = True
            if n == 3:
                value['items'][0]['amount'] += 2
            dump(lane / 'inputs/artifacts' / f'J{n:02}.json', value)
        dump(lane / 'inputs/receipts.json', {'items': [
            {'job': f'J{n:02}', 'attempt': 1, 'state': 'succeeded'} for n in range(1, 25)]})
        if label == 'empty':
            dump(lane / 'inputs/manifest.json', {'jobs': []})
        body = {'code': (HERE / 'main_v2.ibl').read_text(), 'edition': 2,
                'project_id': str(ROOT), 'origin': 'training',
                'inputs': {'입력': str(lane / 'inputs'), '출력': str(lane / 'artifacts'), '판본': 1}}
        save(f'{label}_request.json', body)
        checked = api('/ibl/execute', {**body, 'check': True})
        save(f'{label}_check.json', checked)
        assert checked.get('ok'), checked
        result = api('/ibl/execute', body)
        save(f'{label}_result.json', result)
        if label == 'missing_source':
            passed = result.get('success') is False and not list((lane / 'artifacts').iterdir())
        else:
            value = json.loads((lane / 'artifacts/audit_T1.json').read_text())
            expected_total = sum(sum(r['amount'] for r in good(n)['items'])
                                 for n in range(1, 25) if n != 9) + 2
            passed = result.get('success') is True and (
                value['release_ready'] is True and value['counts']['verified'] == 23
                and value['counts']['cancelled'] == 1 and value['verified_total'] == expected_total
                if label == 'positive' else value['release_ready'] is False
                and value['items'] == [] and value['verified_total'] == 0)
        results.append({'probe': label, 'passed': passed, 'success': result.get('success'),
                        'resume': result.get('resume'), 'diagnostic': result.get('diagnostic')})
    save('probes.json', results)
    print(json.dumps(results, ensure_ascii=False)[:5000])


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
        trainer(int(sys.argv[2]), int(sys.argv[3]))
    elif action == 'capture':
        capture()
    elif action == 'probes':
        probes()
