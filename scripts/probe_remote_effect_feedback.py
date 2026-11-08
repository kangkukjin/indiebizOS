#!/usr/bin/env python3
"""Explicit Samsung0 acceptance and before/after measurement, using production APIs."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json
import sqlite3
import time
import urllib.request

OUT = ROOT / 'outputs/remote_effect_feedback_20261108'
DEVICE = '삼성0'
REQUEST = '삼성0에서 지금 나오는 음악 대신 김지연의 찬바람이 불면을 틀어줘. 한 곡만 재생해줘.'


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def read(name):
    return json.loads((OUT / (name + '.json')).read_text())


def api(path, body=None, timeout=240):
    req = urllib.request.Request('http://127.0.0.1:8765' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def remote(code, label):
    started = time.monotonic()
    code = '#!ibl edition=2\n' + code
    result = api('/ibl/execute', {'code': 'return [limbs:guestpc]{limb:$device,op:"ibl",code:$code,timeout:120}',
                                'edition': 2, 'inputs': {'device': DEVICE, 'code': code}})
    save(label, {'wall_s': time.monotonic() - started, 'response': result})
    if not result.get('success'):
        raise RuntimeError(str(result.get('diagnostic', result))[:1500])
    return result['value']['result']['value']


def snapshot(label):
    result = remote('return [limbs:youtube]{op:"queue"}', label)
    print(json.dumps(result, ensure_ascii=False)[:3000], flush=True)


def prepare(label):
    # Only after original_snapshot has been saved. Setup is excluded from timed AI work.
    read('original_snapshot')
    result = remote('$s=[limbs:youtube]{op:"stop"}\n'
                    '$p=[limbs:youtube]{op:"play",query:"https://www.youtube.com/watch?v=RhWfHc3MATo",count:1}\n'
                    'return {play:$p,queue:[limbs:youtube]{op:"queue"}}', label + '_setup')
    print(json.dumps(result, ensure_ascii=False)[:1800], flush=True)


def start(label):
    if (OUT / (label + '_start.json')).exists():
        raise RuntimeError('Existing request: poll it, do not resubmit')
    session = api('/chat-sessions', {'title': '삼성0 재생 비교 ' + label})
    save(label + '_session', session)
    sid = session.get('id') or session.get('session_id')
    if not sid:
        raise RuntimeError(str(session))
    started = time.time()
    result = api('/chat-sessions/' + sid + '/messages', {'message': REQUEST})
    save(label + '_start', {'started_at': started, 'request': REQUEST, **result})
    print(json.dumps(result, ensure_ascii=False), flush=True)


def poll(label):
    start_row = read(label + '_start')
    state = api('/chat-sessions/' + start_row['session_id'])
    save(label + '_latest', state)
    turn = state.get('turn') or {}
    print(json.dumps({'turn': turn, 'messages': state.get('messages', [])[-2:]}, ensure_ascii=False)[:5000])


def capture(label):
    state = read(label + '_latest')
    turn = state.get('turn') or {}
    if turn.get('state') != 'completed':
        raise RuntimeError('Turn has not completed')
    conn = sqlite3.connect('file:' + str(ROOT / 'data/world_pulse.db') + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute('SELECT * FROM episode_log WHERE user_message=? ORDER BY id DESC LIMIT 1', (REQUEST,))]
    if not rows or not rows[0]['ended_at']:
        raise RuntimeError('No completed episode')
    episode = {k: v for k, v in rows[0].items() if k != 'log'}
    events = [dict(r) for r in conn.execute('SELECT * FROM trajectory_event WHERE task_id=? ORDER BY ts,event_seq', (episode['task_id'],))]
    usage = [json.loads(r['data']) for r in events if r['kind'] == 'model.usage']
    unique = {u['usage_id']: u for u in usage if u.get('usage_id')}
    usage = list(unique.values())
    summary = {'episode': episode, 'session_id': read(label + '_start')['session_id'],
               'turn_state': turn.get('state'), 'wall_s': episode['total_ms'] / 1000,
               'input': sum(u.get('input', 0) for u in usage),
               'output': sum(u.get('output', 0) for u in usage),
               'cache_read': sum(u.get('cache_read', 0) for u in usage),
               'cache_create': sum(u.get('cache_create', 0) for u in usage),
               'usage': usage}
    summary['tokens'] = summary['input'] + summary['output']
    save(label + '_events', events)
    save(label + '_metrics', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'usage'}, ensure_ascii=False), flush=True)



def local(code, label, project_id=None):
    started = time.monotonic()
    result = api('/ibl/execute', {'code': code, 'edition': 2, **({'project_id': project_id} if project_id else {})})
    save(label, {'wall_s': time.monotonic() - started, 'response': result})
    if not result.get('success'):
        raise RuntimeError(str(result.get('diagnostic', result))[:1800])
    return result['value']


def info(label):
    result = local('return [limbs:guestpc]{limb:"삼성0",op:"info"}', label)
    apk = result['result'].get('apk_update') or result['result'].get('capabilities', {}).get('apk_update', {})
    print(json.dumps({k: apk.get(k) for k in ('version_code', 'installed_sha256', 'can_install')}, ensure_ascii=False))


def exercise(label):
    code = '\n'.join([
        '$initial=[limbs:youtube]{op:"stop"}',
        '$start=[limbs:youtube]{op:"play",query:"https://www.youtube.com/watch?v=RhWfHc3MATo",limit:1}',
        '$enqueue=[limbs:youtube]{op:"play",query:"https://www.youtube.com/watch?v=RhWfHc3MATo",limit:1}',
        '$replace=[limbs:youtube]{op:"play",query:"https://www.youtube.com/watch?v=jXy15NGpCSs",limit:1,if_playing:"replace"}',
        '$skip=[limbs:youtube]{op:"skip"}',
        '$stop=[limbs:youtube]{op:"stop"}',
        'return {initial:$initial,start:$start,enqueue:$enqueue,replace:$replace,skip:$skip,stop:$stop}',
    ])
    value = remote(code, label)
    effects = {k: v.get('observation') for k, v in value.items()}
    assert all(o and o['status'] == 'confirmed' for o in effects.values()), effects
    assert effects['enqueue']['scope'] == 'queue_membership'
    assert effects['replace']['actual']['queue_length'] == 1
    assert effects['replace']['actual']['video_id'] == 'jXy15NGpCSs'
    assert effects['skip']['actual']['video_id'] == 'RhWfHc3MATo'
    assert effects['stop']['actual']['playing'] is False
    assert effects['stop']['actual']['queue_length'] == 0
    assert len({o['operation_ref']['step_id'] for o in effects.values()}) == len(effects)
    print(json.dumps(effects, ensure_ascii=False), flush=True)


def settings(label):
    # Keep the user's current volume; the write still exercises native readback.
    value = local('$before=[fn:Android제어]{대상:"guestpc-fc7b12fba936",요청:{action:"volume_status"}}\n'
                  '$same=[fn:Android제어]{대상:"guestpc-fc7b12fba936",요청:{action:"volume",value:$before.result.actual}}\n'
                  'return {before:$before,after:$same}', label, project_id='하드웨어')
    for task in value.values():
        assert task['verified'] and task['result']['observation']['status'] == 'confirmed', task
    assert value['before']['result']['actual'] == value['after']['result']['actual']
    print(json.dumps(value, ensure_ascii=False)[:5000], flush=True)


def cleanup(label):
    result = remote('return [limbs:youtube]{op:"stop"}', label)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot', 'prepare', 'start', 'poll', 'capture', 'info', 'exercise', 'settings', 'cleanup'])
    parser.add_argument('label')
    args = parser.parse_args()
    globals()[args.command](args.label)


if __name__ == '__main__':
    main()
