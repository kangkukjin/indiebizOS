"""읽기 전용 PC제어 상태 조회. 사용: python3 probe_pc.py DEVICE OUTPUT.json"""
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path


def main():
    device, output = sys.argv[1:]
    destination = Path(output)
    if destination.exists():
        raise SystemExit("기존 증거 파일은 덮어쓰지 않습니다.")
    rows = []
    for index in range(10):
        code = 'return [fn:PC제어]{대상:' + json.dumps(device) + ',요청:{action:"status"}}'
        request = urllib.request.Request(
            'http://127.0.0.1:8765/ibl/execute',
            data=json.dumps({'code': code, 'edition': 2, 'origin': 'user',
                             'project_id': '하드웨어'}).encode(),
            headers={'Content-Type': 'application/json'},
        )
        start = time.monotonic()
        with urllib.request.urlopen(request, timeout=150) as response:
            result = json.load(response)
        value = result.get('value') or {}
        row = {'round': index + 1, 'seconds': round(time.monotonic() - start, 4),
               'success': result.get('success'), 'status': value.get('status'),
               'verified': value.get('verified')}
        rows.append(row)
        destination.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(row), flush=True)
        if value.get('verified') is not True:
            break
    print(json.dumps({'n': len(rows),
                      'median': statistics.median(r['seconds'] for r in rows),
                      'max': max(r['seconds'] for r in rows)}))


if __name__ == '__main__':
    main()
