"""29회차 독립 대조 — 1차·최종 보고서와 홍보 tasks 행을 걸어 확인한다.
사용: verify.py <report_1.json> <report_2.json> <새 위임 행 수> [--first-all-done]"""
import json, sqlite3, sys
from pathlib import Path
root = Path(__file__).resolve().parents[5]
r1 = json.loads(Path(sys.argv[1]).read_text()); r2 = json.loads(Path(sys.argv[2]).read_text()); new_rows = int(sys.argv[3]); first_all = '--first-all-done' in sys.argv
CLAIM_CANCELLED = {'취소됨', 'cancelled', '취소 완료'}
def walk(x, strings, refs):
    if isinstance(x, dict):
        if isinstance(x.get('kind'), str) and isinstance(x.get('task_id'), str): refs.append((x['kind'], x['task_id'], x.get('owner')))
        for v in x.values(): walk(v, strings, refs)
    elif isinstance(x, list):
        for v in x: walk(v, strings, refs)
    elif isinstance(x, str): strings.append(x)
s1, k1, s2, k2 = [], [], [], []; walk(r1, s1, k1); walk(r2, s2, k2)
db = sqlite3.connect(root / 'projects/홍보/conversations.db')
def row(tid): return db.execute("select status from tasks where task_id=?", (tid,)).fetchone()
out = {'checks': []}
def check(name, ok, detail=''): out['checks'].append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:200]})
check('새 위임 정확히 2', new_rows == 2, new_rows)
check('1차: 접수증 2개(delegation)', len({t for k, t, _ in k1 if k == 'delegation'}) == 2, sorted(set(k1)))
check('1차: 취소됨을 주장하지 않음', not any(s.strip() in CLAIM_CANCELLED for s in s1), [s for s in s1 if s.strip() in CLAIM_CANCELLED])
running_claims = [s for s in s1 if '취소 불가' in s or '진행 중' in s]
check('1차: 안 끝난 일 표시가 있음(15초 기대) 또는 전부 끝남(변형)', first_all or bool(running_claims), running_claims)
check('1차: 접수증의 행이 실제로 존재', all(row(t) for k, t, _ in k1 if k == 'delegation'), [t for k, t, _ in k1 if k == 'delegation' and not row(t)])
long_texts = [s for s in s2 if len(s) >= 80]
check('최종: 요약 글 2개 이상(비어 있지 않음)', len(long_texts) >= 2, len(long_texts))
check('최종: 두 파일 이름 모두 등장', all(any(f in s for s in s2) for f in ('task_receipts.md', 'body_lifecycle.md')))
check('최종: 접수증 작업이 전부 completed', all((row(t) or ('?',))[0] == 'completed' for k, t, _ in (k2 or k1) if k == 'delegation'), [(t, row(t)) for k, t, _ in (k2 or k1) if k == 'delegation'])
check('최종: 접수증이 1차와 같은 작업(새 시작 없음)', not k2 or set(t for _, t, _ in k2) <= set(t for _, t, _ in k1), sorted(set(k2) - set(k1)))
out['all_ok'] = all(c['ok'] for c in out['checks']); print(json.dumps(out, ensure_ascii=False, indent=1))
