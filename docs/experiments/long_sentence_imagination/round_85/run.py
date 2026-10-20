"""HTTP execution/evidence only; the driver workflow lives in the IBL source."""
import argparse
import json
from pathlib import Path
import time
import uuid
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-20_85회차'
DOC = Path(__file__).resolve().parent


def api(path, body=None, timeout=180):
    request = urllib.request.Request('http://127.0.0.1:8765' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except TimeoutError as error:
        return {'transport_unknown': True, 'error': str(error), 'note': 'Do not resubmit; recover the ticket/run.'}
    except urllib.error.HTTPError as error:
        return {'http_error': error.code, 'body': error.read().decode()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['check', 'base', 'variation', 'submit', 'poll'])
    parser.add_argument('--version', default='v0')
    parser.add_argument('--label', default='base')
    parser.add_argument('--post-repair', action='store_true')
    args = parser.parse_args()
    global OUT
    if args.post_repair:
        OUT = OUT / 'post_repair'
    for folder in ['runs', 'trainer', 'ai/base', 'ai/variation']:
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    label = args.label
    if args.mode == 'submit':
        import sqlite3
        db = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
        last = db.execute('select max(id) from episode_log').fetchone()[0]
        text = (DOC / ('request.txt' if label == 'base' else 'variation.txt')).read_text()
        clean_inputs = OUT / 'inputs_clean' / label
        clean_inputs.mkdir(parents=True, exist_ok=True)
        (clean_inputs / 'request.txt').write_text(text)
        text += f'\n자료 위치: {clean_inputs}/\n산출물 저장 위치: {OUT}/ai/{label}/'
        body = {'message': text, 'origin': 'training', 'background': True}
        (OUT / f'runs/ai_{label}_request.json').write_text(json.dumps({'last_episode': last, 'body': body}, ensure_ascii=False, indent=2))
        result = api('/system-ai/chat', body, 60)
        (OUT / f'runs/ai_{label}_accepted.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        return
    if args.mode == 'poll':
        ticket = json.loads((OUT / f'runs/ai_{label}_accepted.json').read_text())
        result = api(ticket['status_url'] + '?wait=20', timeout=40)
        (OUT / f'runs/ai_{label}_status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False)[:5000])
        return
    variation = args.mode == 'variation' or label == 'variation'
    label = ('variation' if variation else 'base') + '_' + args.version
    body = {'code': (DOC / f'base_{args.version}.ibl').read_text(), 'origin': 'training',
            'edition': 2, 'project_id': 'study', 'ticket': uuid.uuid4().hex,
            'inputs': {'target': 'L85_missing_pc_20261020' if variation else '__local__',
                       'window': 2147483646 if variation else None,
                       'out': str(OUT / 'trainer' / f'{label}.json')}}
    if args.mode == 'check':
        body['check'] = True
        label += '_check2'
    path = OUT / 'runs' / (label + '.json')
    record = {'request': body, 'started': time.time()}
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    result = api('/ibl/execute', body)
    record.update(response=result, seconds=time.time() - record['started'])
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(json.dumps({k: result.get(k) for k in ['ok','success','run_status','error','issues','resume','transport_unknown']}, ensure_ascii=False))
    print('HTTP_SECONDS', record['seconds'])


if __name__ == '__main__':
    main()
