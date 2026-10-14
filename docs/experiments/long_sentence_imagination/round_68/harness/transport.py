"""HTTP 전송만. 요청·응답·벽시계를 보존한다. 사용: transport.py LABEL (--code FILE|--request FILE) [--endpoint] [--timeout]"""
import argparse, json, time, urllib.error, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-14_68회차'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('label'); p.add_argument('--code'); p.add_argument('--request'); p.add_argument('--inputs')
    p.add_argument('--endpoint', default='/ibl/execute'); p.add_argument('--timeout', type=int, default=1500); p.add_argument('--dir', default='runs')
    a = p.parse_args()
    if a.request:
        payload = json.loads(Path(a.request).read_text())
    else:
        payload = {'code': Path(a.code).read_text(), 'edition': 2, 'origin': 'training', 'project_id': '수동모드'}
        if a.inputs: payload['inputs'] = json.loads(Path(a.inputs).read_text())
    started = time.time()
    req = urllib.request.Request('http://127.0.0.1:8765' + a.endpoint, data=json.dumps(payload, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=a.timeout) as r: result = json.load(r)
    except urllib.error.HTTPError as e: result = {'http_status': e.code, 'body': e.read().decode()}
    rec = {'request': payload, 'endpoint': a.endpoint, 'started': started, 'ended': time.time(), 'response': result}
    (OUT / a.dir).mkdir(parents=True, exist_ok=True)
    (OUT / a.dir / (a.label + '.json')).write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    v = result.get('value', result)
    s = json.dumps(v, ensure_ascii=False)
    print(json.dumps({'label': a.label, 'elapsed': round(rec['ended'] - started, 2), 'success': result.get('success'), 'error': result.get('error'), 'run_id': result.get('run_id'), 'value_len': len(s)}, ensure_ascii=False))
    print(s[:2200])
main()
