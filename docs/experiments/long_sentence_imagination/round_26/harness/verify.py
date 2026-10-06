"""26회차 독립 대조 — 직접 pytest 로그(expected/*.log)에서 파일별 통과 수를 세어 보고서와 비교한다.
사용: verify.py <report_1.json> <report_2.json> [--first-all-done]"""
import json, re, sys
from pathlib import Path
root = Path(__file__).resolve().parents[5]
o = root / 'outputs/long_sentence_imagination/2026-10-07_26회차'
def expected():
    per = {}
    for name in ('fast', 'data', 'vocab'):
        for line in (o / 'expected' / f'{name}.log').read_text().splitlines():
            m = re.match(r'^(PASSED|FAILED|ERROR) (backend/\S+?\.py)::', line)
            if m: per.setdefault(m.group(2), {'passed': 0, 'failed': 0, 'errors': 0})[{'PASSED': 'passed', 'FAILED': 'failed', 'ERROR': 'errors'}[m.group(1)]] += 1
    return per
def flat(report):
    """보고서 모양은 작성자마다 다르다 — 파일 경로가 든 Record 를 찾아 숫자 칸을 모은다."""
    found = {}
    def walk(x):
        if isinstance(x, dict):
            f = x.get('file') or x.get('path') or x.get('파일')
            if isinstance(f, str) and f.startswith('backend/'):
                row = {k: x.get(k, x.get(alt)) for k, alt in (('passed', '통과'), ('failed', '실패'), ('errors', '오류'))}
                # 최종 보고서가 '이전 1차 상태' 사본을 함께 보존하면(수치 없는 진행 중 행) 그것이 확정 행을 덮지 않게 한다
                if f not in found or (row['passed'] is not None and found[f]['passed'] is None): found[f] = row
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(report); return found
exp = expected(); out = {'expected_files': exp, 'checks': []}
r1, r2 = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
f1, f2 = flat(r1), flat(r2); vocab = 'backend/test_vocabulary_archive.py'; typo = 'backend/test_lsi26_없는파일.py'
def check(name, ok, detail=''): out['checks'].append({'check': name, 'ok': bool(ok), 'detail': detail})
first_all = '--first-all-done' in sys.argv
for f, e in exp.items():
    if f == vocab and not first_all:
        check('1차: 어휘는 수치 없음(진행 중)', f not in f1 or not f1[f].get('passed'), str(f1.get(f)))
    else:
        check(f'1차: {f} 통과 수', f1.get(f, {}).get('passed') == e['passed'], f"{f1.get(f)} vs {e}")
    check(f'최종: {f} 통과 수', f2.get(f, {}).get('passed') == e['passed'] and not f2[f].get('failed'), f"{f2.get(f)} vs {e}")
for label, fl in (('1차', f1), ('최종', f2)):
    t = fl.get(typo, {})
    check(f'{label}: 없는 파일은 통과 0', not t.get('passed'), str(t))
s1, s2 = json.dumps(r1, ensure_ascii=False), json.dumps(r2, ensure_ascii=False)
check('1차 본문에 진행 중 표시', first_all or '진행' in s1 or 'running' in s1 or 'pending' in s1)
check('최종: 모든 파일에 확정 수치', all(v.get('passed') is not None for v in f2.values()) and len(f2) >= 5, str({k: v.get('passed') for k, v in f2.items()}))
out['all_ok'] = all(c['ok'] for c in out['checks'])
print(json.dumps(out, ensure_ascii=False, indent=1))
