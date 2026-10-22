"""Finite training transport. Task computation is in IBL or the independent AI."""
import argparse
import datetime
import json
import shutil
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_89회차'
PROJECT = 'L89_training'


def save(name, value):
    (OUT / 'runs' / f'{name}.json').write_text(json.dumps(value, ensure_ascii=False, indent=2))


def api(path, body=None, timeout=55):
    req = urllib.request.Request('http://127.0.0.1:8765' + path,
        data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as result:
        return json.load(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('label', nargs='?', default='1')
    args = parser.parse_args()
    if args.action in ('create', 'submit', 'ibl', 'train'):
        deadline = datetime.datetime.fromisoformat(json.loads((OUT / 'start.json').read_text())['deadline'])
        assert datetime.datetime.now().astimezone() < deadline, 'Experiment budget expired'
    if args.action == 'create':
        assert not (OUT / 'runs/agent.json').exists()
        save('project', api('/projects', {'name': PROJECT}))
        body = {'name': 'parallel_review', 'role': '사용자 요청을 자료 근거에 맞게 수행하고 한국어로 간결하게 답한다. 합성 자료 읽기와 지정 출력 폴더 쓰기만 하는 훈련이다. 실제 발송·배포·구매·예약·다른 프로젝트 변경은 하지 않는다.', 'allowed_nodes': ['self', 'table']}
        result = api(f'/projects/{PROJECT}/agents', body)
        save('agent', result)
        save('agent_start', api(f'/projects/{PROJECT}/agents/{result["agent"]["id"]}/start', {}))
        print(json.dumps(result, ensure_ascii=False))
        return
    if args.action == 'describe':
        result = api('/ibl/execute', {'code': '', 'describe': ['self:read', 'self:write', 'self:time'], 'edition': 2, 'project_id': PROJECT, 'origin': 'training'})
        save('contracts', result)
        print(json.dumps(result, ensure_ascii=False)[:16000])
        return
    if args.action in ('ibl', 'train'):
        if args.action == 'train':
            body = json.loads((OUT / 'runs' / f'{args.label}_check_request.json').read_text())
            body.update(origin='training', edition=2, project_id=PROJECT)
            check = api('/ibl/execute', body)
            save(args.label + '_check', {'request': body, 'response': check})
            if not check.get('ok'):
                print(json.dumps(check, ensure_ascii=False)[:5000])
                return
            save(args.label + '_request', check['execute_args'])
        body = json.loads((OUT / 'runs' / f'{args.label}_request.json').read_text())
        body.update(origin='training', edition=2, project_id=PROJECT)
        started = time.monotonic()
        result = api('/ibl/execute', body)
        save(args.label, {'request': body, 'response': result, 'seconds': time.monotonic() - started})
        value = result.get('value', {})
        if isinstance(value, dict) and 'summary' in value:
            value = {k: v for k, v in value['summary'].items() if k not in ('record_actions', 'actions')}
        print(json.dumps({'label': args.label, 'seconds': time.monotonic() - started,
            **{k: result[k] for k in ['ok', 'success', 'status', 'error', 'issues'] if k in result},
            'value': value, 'elapsed_ms': result.get('usage', {}).get('elapsed_ms'),
            'reuse': result.get('reuse')}, ensure_ascii=False)[:5500])
        return
    agent = json.loads((OUT / 'runs/agent.json').read_text())['agent']['id']
    route = f'/projects/{PROJECT}/agents/{agent}'
    if args.action == 'stop':
        result = api(route + '/stop', {})
        save('agent_stop', result)
        print(json.dumps(result))
    elif args.action == 'submit':
        n = int(args.label)
        assert not (OUT / 'runs' / f'T{n}_accepted.json').exists(), 'Recover existing ticket'
        if n > 1:
            prior = json.loads((OUT / 'runs' / f'T{n-1}_result.json').read_text())
            assert prior['state'] in ('succeeded', 'failed') and prior.get('pending_children', 0) == 0
        if n == 3:
            shutil.copyfile(OUT / 'staged/records_partial.json', OUT / 'inputs/records.json')
        if n == 4:
            shutil.copyfile(OUT / 'staged/records_restored.json', OUT / 'inputs/records.json')
        body = {'command': json.loads((OUT / 'reference/requests.json').read_text())['turns'][n-1], 'origin': 'training', 'background': True}
        save(f'T{n}_request', {'body': body, 'at': datetime.datetime.now().astimezone().isoformat()})
        result = api(route + '/command', body)
        save(f'T{n}_accepted', result)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == 'poll':
        ticket = json.loads((OUT / 'runs' / f'T{args.label}_accepted.json').read_text())
        result = api(ticket['status_url'] + '?wait=20')
        terminal = result.get('state') in ('succeeded', 'failed', 'cancelled')
        save(f'T{args.label}_' + ('result' if terminal else 'latest'), result)
        if terminal and not (OUT / 'snapshots' / f'T{args.label}').exists():
            shutil.copytree(OUT / 'ai', OUT / 'snapshots' / f'T{args.label}')
        print(json.dumps(result, ensure_ascii=False)[:6000])


if __name__ == '__main__':
    main()
