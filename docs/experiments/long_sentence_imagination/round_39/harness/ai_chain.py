"""독립 AI 실행: /system-ai/chat background 접수 → status_url polling. 사용: ai_chain.py <label> <request.txt> [--timeout 1500]"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_39회차'


def post(path, body):
    req = urllib.request.Request('http://127.0.0.1:8765' + path, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def get(url):
    with urllib.request.urlopen('http://127.0.0.1:8765' + url if url.startswith('/') else url, timeout=60) as r:
        return json.load(r)


def main():
    label, path = sys.argv[1], sys.argv[2]
    timeout = int(sys.argv[sys.argv.index('--timeout') + 1]) if '--timeout' in sys.argv else 1500
    started = time.time()
    if path.startswith('task_'):   # 이미 접수된 작업에 붙어 기다리기만
        receipt = {'task_id': path, 'status_url': '/system-ai/tasks/' + path, 'state': 'attached'}
    else:
        message = Path(path).read_text()
        receipt = post('/system-ai/chat', {'message': message, 'origin': 'training', 'background': True})
    (OUT / 'runs' / f'ai_{label}_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=1))
    status_url = receipt.get('status_url')
    print('receipt', json.dumps({k: receipt.get(k) for k in ('task_id', 'state', 'status_url')}, ensure_ascii=False), flush=True)
    last = None
    while time.time() - started < timeout:
        last = get(status_url + ('&' if '?' in status_url else '?') + 'wait=20')
        st = last.get('status') or last.get('state')
        if st in ('succeeded', 'failed', 'cancelled'):
            break
        time.sleep(5)   # wait= 가 즉시 반환될 때 빈 루프로 포트를 소진하지 않도록
    (OUT / 'runs' / f'ai_{label}_status.json').write_text(json.dumps(last, ensure_ascii=False, indent=1))
    print(json.dumps({'label': label, 'elapsed': round(time.time() - started, 1), 'status': (last or {}).get('status') or (last or {}).get('state'),
                      'result_head': str((last or {}).get('result'))[:1500]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
