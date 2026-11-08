#!/usr/bin/env python3
"""Explicit local acceptance/AI comparison for retained IBL failure results.

All fixtures are disposable files under one dedicated project output directory.
Preparation is outside the measured request. No producer replies are mocked.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json
import shutil
import sqlite3
import time
import urllib.request
from datetime import datetime

OUT = ROOT / 'outputs/ibl_failure_feedback_20261108'
FIXTURE = ROOT / 'projects/앱모드/outputs/ibl_failure_feedback_20261108'


def save(label, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (label + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def read(label):
    return json.loads((OUT / (label + '.json')).read_text())


def api(path, body=None, timeout=240):
    request = urllib.request.Request('http://127.0.0.1:8765' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def ibl(code):
    return api('/ibl/execute', {'edition': 2, 'project_id': '앱모드', 'code': code})


def prepare(label):
    from openpyxl import Workbook
    FIXTURE.mkdir(parents=True, exist_ok=True)
    for name in ('inputs', 'copied', 'downloads'):
        path = FIXTURE / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir()
    for i in range(7):
        (FIXTURE / 'inputs' / f'item{i}.txt').write_text(f'fixture-{i}\n')
    (FIXTURE / 'copied/item0.txt').write_text('existing destination must survive\n')
    (FIXTURE / 'downloads/receipt_2.bin').mkdir()
    wb = Workbook()
    ws = wb.active
    ws.title = 'Checks'
    ws['A1'], ws['B1'], ws['C1'] = '=6*7', '=1/0', '=SUM(2,3)'
    wb.save(FIXTURE / 'formulas.xlsx')
    (FIXTURE / 'calculated.xlsx').unlink(missing_ok=True)
    if (OUT / 'calendar.json').exists():
        event = read('calendar')
        result = ibl('return [self:manage_events]' + json.dumps({
            'op': 'update', 'event_id': event['id'], 'time': '10:00', 'description': 'isolated IBL test'}, ensure_ascii=False))
    else:
        result = ibl('return [self:manage_events]' + json.dumps({
            'op': 'create', 'title': 'IBL 결과 보존 검증용', 'date': '2026-11-09',
            'time': '10:00', 'type': 'other', 'description': 'isolated IBL test'}, ensure_ascii=False))
        assert result.get('success'), result
        save('calendar', result['value']['event'])
    assert result.get('success'), result
    save(label + '_setup', {'event_id': read('calendar')['id'], 'fixture': str(FIXTURE)})
    print('prepared', label, flush=True)


def program():
    def call(name, **args):
        return '[' + name + ']' + json.dumps(args, ensure_ascii=False)
    expression = "for(let i=0;i<2;i++){let a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['file'+i]));a.download='receipt.bin';a.click();}"
    paths = [{'path': str(FIXTURE / 'inputs' / f'item{i}.txt')} for i in range(8)]
    browser = call('limbs:browser', op='evaluate', driver='playwright', expression=expression,
                   path=str(FIXTURE / 'downloads/receipt.bin'))
    copy = json.dumps(paths) + ' >> ' + call('self:copy', dest=str(FIXTURE / 'copied'), if_exists='rename')
    sheet = call('self:sheet', op='calculate', path=str(FIXTURE / 'formulas.xlsx'),
                 output=str(FIXTURE / 'calculated.xlsx'))
    event = call('self:manage_events', op='update', event_id=read('calendar')['id'], time='11:30')
    return '\n'.join(['#!ibl edition=2',
        call('limbs:browser', op='navigate', driver='playwright', url='about:blank', wait='load'),
        '$browser = [try] { ' + browser + ' } [catch] { $error }',
        '$copy = [try] { ' + copy + ' } [catch] { $error }',
        '$sheet = [try] { ' + sheet + ' } [catch] { $error }',
        '$calendar = ' + event,
        'return {browser:$browser,copy:$copy,sheet:$sheet,calendar:$calendar}'])


def direct(label):
    code = program()
    began = time.monotonic()
    result = ibl(code)
    save(label + '_direct', {'wall_s': time.monotonic() - began, 'code': code, 'response': result})
    print(json.dumps({'success': result.get('success'), 'value': result.get('value'),
                      'diagnostic': result.get('diagnostic')}, ensure_ascii=False)[:9000], flush=True)


def prompt():
    return ('검증용 파일과 일정만 다루는 IBL 실행 과제입니다. 아래 프로그램을 앱모드 문맥에서 그대로 한 번 실행하고 결과를 보고해 주세요. '
        '실패한 변경을 재실행하거나 원본·결과를 고치지 마세요. 결과가 부족하면 필요한 읽기만 하세요. '
        '최종 답변은 ① 브라우저 다운로드의 실제 저장 성공 파일명·바이트와 실패 원인 '
        '② 실제 복사된 파일명 전부와 실패 개수(기존 item0.txt는 복사 성공에 포함하지 않음) '
        '③ 계산된 Checks!A1·C1 값과 B1 오류 '
        '④ 저장된 일정 ID·날짜·시각을 포함하세요. 확인하지 못한 값은 미확인이라고 표시하세요.\n\n' + program())


def start(label):
    if (OUT / (label + '_start.json')).exists():
        raise RuntimeError('Already submitted; poll the existing turn')
    session = api('/chat-sessions', {'title': 'IBL 결과 보존 비교 ' + label})
    sid = session.get('id') or session.get('session_id')
    request = prompt()
    began = time.time()
    result = api('/chat-sessions/' + sid + '/messages', {'message': request})
    save(label + '_start', {'started_at': began, 'request': request, **result})
    print(json.dumps(result), flush=True)


def poll(label):
    row = read(label + '_start')
    state = api('/chat-sessions/' + row['session_id'])
    save(label + '_latest', state)
    print(json.dumps({'turn': state.get('turn'), 'messages': state.get('messages', [])[-1:]}, ensure_ascii=False)[:5000], flush=True)


def capture(label):
    row = read(label + '_start')
    state = read(label + '_latest')
    assert (state.get('turn') or {}).get('state') == 'completed', 'Still running'
    conn = sqlite3.connect('file:' + str(ROOT / 'data/world_pulse.db') + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    candidates = [dict(r) for r in conn.execute(
        'SELECT * FROM episode_log WHERE user_message=? ORDER BY id DESC LIMIT 10', (row['request'][:500],))]
    candidates = [e for e in candidates if abs(datetime.fromisoformat(e['started_at']).timestamp() - row['started_at']) < 10]
    # The ledger stores the first 500 message characters; bind by this request's start too.
    assert not (OUT / (label + '_metrics.json')).exists(), 'Already captured'
    assert len(candidates) == 1, 'Episode identity is ambiguous'
    episode = candidates[0]
    assert episode['ended_at'], 'Episode not finished'
    episode.pop('log', None)
    events = [dict(r) for r in conn.execute(
        'SELECT * FROM trajectory_event WHERE task_id=? ORDER BY ts,event_seq', (episode['task_id'],))]
    usage = [json.loads(r['data']) for r in events if r['kind'] == 'model.usage']
    usage = list({u['usage_id']: u for u in usage if u.get('usage_id')}.values())
    metrics = {'episode': episode, 'session_id': row['session_id'], 'wall_s': episode['total_ms'] / 1000,
               **{k: sum(u.get(k, 0) for u in usage) for k in ('input', 'output', 'cache_read', 'cache_create')}, 'usage': usage}
    metrics['tokens'] = metrics['input'] + metrics['output']
    save(label + '_events', events)
    save(label + '_metrics', metrics)
    print(json.dumps({k: v for k, v in metrics.items() if k != 'usage'}, ensure_ascii=False), flush=True)


def cleanup(label):
    event = read('calendar')
    result = ibl('return [self:manage_events]' + json.dumps({'op': 'delete', 'event_id': event['id']}))
    save(label + '_cleanup', result)
    assert result.get('success'), result
    save(label + '_removed_calendar', event)
    (OUT / 'calendar.json').unlink()
    print('test calendar event removed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'direct', 'start', 'poll', 'capture', 'cleanup'])
    parser.add_argument('label')
    args = parser.parse_args()
    globals()[args.command](args.label)
