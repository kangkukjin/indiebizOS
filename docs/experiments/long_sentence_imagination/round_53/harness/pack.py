"""git 에 넣을 증거 정리 — runs/ 의 큰 실행 기록을 요약본으로 evidence/ 에, 탐침은 응답을 줄이고, 법령정보 API 사용자 식별값(OC=)을 가린다. 사용: pack.py"""
import json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
OUT = HERE.parents[3] / 'outputs/long_sentence_imagination/2026-10-11_53회차'
def scrub(s): return re.sub(r'OC=[^&"\\\s]+', 'OC=(가림)', s)
def cut(v, n):
    s = json.dumps(v, ensure_ascii=False)
    return v if len(s) <= n else {'_truncated': len(s), 'head': s[:n]}
for p in sorted((OUT / 'runs').glob('trainer_*.json')):
    d = json.loads(p.read_text()); r = d['response']; u = r.get('usage') or {}
    keep = {'label': p.stem, 'task_id': (d.get('request') or {}).get('task_id'), 'reuse_request': (d.get('request') or {}).get('reuse'), 'budget_request': (d.get('request') or {}).get('budget'),
            'elapsed': round(d['ended'] - d['started'], 2), 'success': r.get('success'), 'status': r.get('status'), 'issues': [{k: i.get(k) for k in ('code', 'message', 'hint')} | {'line': i['location']['line']} for i in (r.get('issues') or [])],
            'error': r.get('error'), 'value': cut(r.get('value'), 9000), 'usage': {k: u.get(k) for k in ('steps', 'rows', 'elapsed_ms', 'model', 'limits')},
            'reuse': cut(r.get('reuse'), 2500), 'continuation': cut(r.get('continuation'), 2500), 'warnings': cut(r.get('warnings'), 1500)}
    (HERE / 'evidence' / (p.stem + '.json')).write_text(scrub(json.dumps(keep, ensure_ascii=False, indent=1)))
for p in sorted((HERE / 'evidence').glob('probe_*.json')):
    d = json.loads(p.read_text())
    if 'response' not in d: continue      # 이미 줄인 것 — 다시 줄이면 값이 사라진다
    r = d.get('response') or {}
    slim = {'code': d.get('code'), 'elapsed': d.get('elapsed'), 'success': r.get('success'), 'issues': r.get('issues') and [{k: i.get(k) for k in ('code', 'message')} for i in r['issues']], 'value': cut(r.get('value'), 3000)}
    p.write_text(scrub(json.dumps(slim, ensure_ascii=False, indent=1)))
for p in sorted((HERE / 'evidence').glob('ai_*')):
    if p.suffix in ('.json', '.md', '.txt'): p.write_text(scrub(p.read_text()))
left = [p.name for p in (HERE / 'evidence').iterdir() if 'OC=' in p.read_text() and 'OC=(가림)' not in p.read_text()]
print('packed', len(list((HERE / 'evidence').iterdir())), 'files; unscrubbed:', left, 'bytes', sum(p.stat().st_size for p in (HERE / 'evidence').iterdir()))
