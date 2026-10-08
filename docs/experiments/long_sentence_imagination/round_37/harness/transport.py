"""Round37 HTTP transport only; research composition belongs in IBL."""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DOC = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-08_37회차'


def request(label, payload=None, endpoint='/ibl/execute'):
    started = time.time()
    req = urllib.request.Request('http://127.0.0.1:8765' + endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=900) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        result = {'http_error': exc.code, 'body': exc.read().decode()}
    path = OUT / 'runs' / (label + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'request': payload, 'response': result,
        'started': started, 'ended': time.time(), 'endpoint': endpoint}, ensure_ascii=False, indent=2))
    print(json.dumps({'label': label, 'wall_s': time.time()-started,
        'saved': str(path), **{k: result[k] for k in ('success','ok','error','http_error','run_status',
            'state','task_id','status_url','resume','issues','warnings') if k in result}}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('--payload')
    parser.add_argument('--endpoint', default='/ibl/execute')
    args = parser.parse_args()
    request(args.label, json.loads(Path(args.payload).read_text()) if args.payload else None, args.endpoint)
