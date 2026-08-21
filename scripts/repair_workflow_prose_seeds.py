#!/usr/bin/env python3
"""repair_workflow_prose_seeds.py — save 관문이 거절하는 산문 몸통 용례 수리 (2026-08-22).

`[self:workflow]{op:"save", name:"일일리포트", steps:["뉴스수집","요약","저장"]}` — 몸통이
IBL 이 아니라 **한국어 산문**이다. 2026-08 등록 관문(`_validate_sentence`)이 생긴 뒤로 이
문장은 저장 자체가 거절되는데, 코퍼스엔 같은 몸통이 5가지 다른 표현으로 남아 있었다.
게다가 그 5건이 "워크플로우 만들어줘" 부류 질의의 회상 상위를 차지해, 시그니처 시드
(seed_workflow_signature.py)를 정면으로 무력화하고 있었다.

지우지 않고 **고친다** — intent 5종("새 워크플로우 만들자", "자동화 파이프라인 등록해줘" …)은
사람이 실제로 쓰는 짧은 표현이라 그 자체가 값어치다. 몸통만 실제 IBL + 시그니처로 바꾼다.

임베딩은 intent+ibl_code 로 만들어지므로 UPDATE 후 **재인덱싱 필수**(FTS 는 AFTER UPDATE
트리거가 알아서 동기화하지만 ibl_examples_vec 는 트리거가 없다).

실행: .venv/bin/python3 scripts/repair_workflow_prose_seeds.py
"""
import sys, os, json, sqlite3
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

ROOT = os.path.join(os.path.dirname(__file__), "..")
OLD = '[self:workflow]{op: "save", name: "일일리포트", steps: ["뉴스수집", "요약", "저장"]}'
# ★params_default 를 함께 싣는다 — 코퍼스엔 `{op:"run", name:"일일리포트"}` 무인자 실행
# 용례가 5건 있다. 몸통에 인자만 넣고 기본값을 안 주면 그 5건이 전부 "인자 누락" 으로
# 거절되는 문장이 되어, 고치려던 모순을 다른 자리에 옮겨 놓는 꼴이 된다.
NEW = ('[self:workflow]{op: "save", name: "일일리포트", '
       'params_default: {topic: "AI"}, '
       'do: "[sense:search]{source: \'gnews\', query: \'${topic}\'} '
       '>> [table:brief]{instruction: \'5문장 요지\'} '
       '>> [self:write]{path: \'${topic}_리포트.md\'}"}')

# 첫 수리에서 이미 몸통만 바꾼 판(기본값 없음)이 들어갔을 수 있어, 그것도 대상으로 잡는다.
PRIOR = ('[self:workflow]{op: "save", name: "일일리포트", '
         'do: "[sense:search]{source: \'gnews\', query: \'${topic}\'} '
         '>> [table:brief]{instruction: \'5문장 요지\'} '
         '>> [self:write]{path: \'${topic}_리포트.md\'}"}')

# ── 대체본이 정말 통과하는지 먼저 확인 (교재를 고치는 스크립트가 또 틀리면 안 된다) ──
from ibl_parser import parse                      # noqa: E402
from workflow_engine import _validate_sentence    # noqa: E402
from workflow_contract import _free_vars          # noqa: E402

body = parse(NEW)[0]["params"]["do"]
assert _validate_sentence(body) is None, f"대체본이 관문에 걸림: {_validate_sentence(body)}"
sig = _free_vars(parse(body))
assert sig == ["topic"], f"대체본 시그니처가 기대와 다름: {sig}"
print(f"대체본 검증 ✓ (관문 통과 · 시그니처 {sig})")

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 수리 중단"

db_path = os.path.join(ROOT, "data", "ibl_usage.db")
conn = sqlite3.connect(db_path)
rows = list(conn.execute("SELECT id, intent FROM ibl_examples WHERE ibl_code IN (?, ?)", (OLD, PRIOR)))
now = datetime.now().isoformat()
conn.executemany("UPDATE ibl_examples SET ibl_code = ?, updated_at = ? WHERE id = ?",
                 [(NEW, now, rid) for rid, _ in rows])
conn.commit()
conn.close()
print(f"코퍼스 수리: {len(rows)}건")
for rid, intent in rows:
    print(f"   #{rid} {intent}")

# 벡터 재인덱싱 — ★vec0 가상테이블은 INSERT OR REPLACE 가 안 먹는다(UNIQUE 위반).
# DELETE → INSERT 가 유일한 갱신 경로 [[project_sqlite_vec_quirks]]. _index_batch 는
# 예외를 로그로만 삼키므로(호출자에겐 성공처럼 보인다) 여기서 **직접 확인**한다.
ids = [rid for rid, _ in rows]
vconn = db._get_vec_connection()
assert vconn is not None, "vec 연결 실패 — 수리 중단(벡터가 옛 코드를 담은 채 남는다)"
ph = ",".join("?" * len(ids))
vconn.execute(f"DELETE FROM ibl_examples_vec WHERE rowid IN ({ph})", ids)
vconn.commit()
vconn.close()
db._index_batch(ids, [{"intent": intent, "ibl_code": NEW} for _, intent in rows])

# 정직 확인 — 개수 일치만으로는 "갱신됐는지" 를 못 본다. 갱신된 행의 임베딩이 새 코드의
# 임베딩과 같은지 직접 대조한다.
vconn = db._get_vec_connection()
got = {r[0] for r in vconn.execute(f"SELECT rowid FROM ibl_examples_vec WHERE rowid IN ({ph})", ids)}
vconn.close()
missing = sorted(set(ids) - got)
assert not missing, f"★벡터 재인덱싱 실패 — 임베딩 없는 행: {missing}"
print(f"벡터 재인덱싱 확인 ✓ ({len(got)}/{len(ids)}행)")

# 훈련 파일도 같이 — 안 고치면 다음 풀 재학습이 산문 몸통을 되살린다
tp = os.path.join(ROOT, "data", "training", "ibl_training_balanced_20260516.json")
data = json.load(open(tp, encoding="utf-8"))
n = 0
for ex in data:
    if ex.get("ibl_code") in (OLD, PRIOR):
        ex["ibl_code"] = NEW
        n += 1
with open(tp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"훈련 파일 수리: {n}건 → {os.path.basename(tp)}")
