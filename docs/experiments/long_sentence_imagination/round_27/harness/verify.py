"""27회차 독립 대조 — 보고서 모양은 작성자마다 다르므로 파일 경로가 든 Record 와 접수증·상태 문자열을 걸어서 찾는다.
독립 기대: 빠른 2파일 7+20 통과, 어휘 6 통과(26회차 직접 pytest 로그와 같은 파일), 위임은 비어 있지 않은 요약 글.
사용: verify.py <report_1.json> <report_2.json> <새 script 작업 수> <새 위임 수> [--first-all-done]"""
import json, sys
from pathlib import Path
EXP = {'backend/test_preflight_restart.py': 7, 'backend/test_selfbuild_gate_2026_09_07.py': 20, 'backend/test_vocabulary_archive.py': 6}
VOCAB = 'backend/test_vocabulary_archive.py'
CLAIM_CANCELLED = {'취소됨', 'cancelled', '취소 완료'}
def scan(report):
    files, strings, refs = {}, [], []
    def walk(x):
        if isinstance(x, dict):
            f = x.get('file') or x.get('path') or x.get('파일')
            if isinstance(f, str) and f in EXP:
                p = x.get('passed', x.get('통과'))
                if f not in files or (p is not None and files[f] is None): files[f] = p
            if isinstance(x.get('kind'), str) and isinstance(x.get('task_id'), str): refs.append((x['kind'], x['task_id']))
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
        elif isinstance(x, str): strings.append(x)
    walk(report); return files, strings, set(refs)
p1, p2 = Path(sys.argv[1]), Path(sys.argv[2]); r1, r2 = json.loads(p1.read_text()), json.loads(p2.read_text())
f1, s1, k1 = scan(r1); f2, s2, k2 = scan(r2); first_all = '--first-all-done' in sys.argv
out = {'checks': []}
def check(name, ok, detail=''): out['checks'].append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:200]})
check('새 script 작업 정확히 2', sys.argv[3] == '2', sys.argv[3]); check('새 위임 정확히 1', sys.argv[4] == '1', sys.argv[4])
for f, n in EXP.items():
    if f == VOCAB and not first_all: check('1차: 어휘는 확정 수치 없음(안 끝남)', not f1.get(f), f1.get(f))
    else: check(f'1차: {f} 통과 {n}', f1.get(f) == n, f1.get(f))
    check(f'최종: {f} 통과 {n}', f2.get(f) == n, f2.get(f))
# 이 회차에서 실제로 취소된 작업은 없다(지원 종류 아님) — 상태 값으로 "취소됨"을 주장하면 거짓
check('1차: 취소됨을 상태 값으로 주장하지 않음', not any(s.strip() in CLAIM_CANCELLED for s in s1), [s for s in s1 if s.strip() in CLAIM_CANCELLED])
check('최종: 취소됨을 상태 값으로 주장하지 않음', not any(s.strip() in CLAIM_CANCELLED for s in s2), [s for s in s2 if s.strip() in CLAIM_CANCELLED])
check('1차: 안 끝난 일의 접수증(script) 보존', first_all or any(k == 'script' for k, _ in k1), sorted(k1))
check('최종: 위임 요약 글 있음', any(len(s) >= 40 and ('접수' in s or 'task_ref' in s) for s in s2))
check('최종: 접수증이 1차와 같은 작업', not k1 or k1 <= k2 or not (k2 - k1), sorted(k2 - k1))
out['all_ok'] = all(c['ok'] for c in out['checks']); print(json.dumps(out, ensure_ascii=False, indent=1))
