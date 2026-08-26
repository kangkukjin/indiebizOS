"""[engines:render]{op:"xlsx"} 장부 지각 시딩 (2026-08-27, RENDER_XLSX_HANDOFF Phase 4).

장부(xlsx/xlsm)의 피드백 2층(수식 재계산 값)·3층(겉모습) 개통에 맞춰:
단독 변주 · op 확장자 추론 · 편집→지각→심사 루프 · pdf_path 텍스트 통로($변수.필드) ·
criteria "sheet" 취향 파일 · 재시도 두 형태(repeat / goal).

실행: .venv/bin/python3 scripts/seed_render_xlsx.py
(system python3 은 sqlite_vec 가 없다 — .venv 필수)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if ".worktrees" in ROOT.parts:                       # 시딩은 라이브 원장에만 — 워크트리 사본 금지
    ROOT = Path(*ROOT.parts[:ROOT.parts.index(".worktrees")])
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INDIEBIZ_BASE_PATH", str(ROOT))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── 단문: 장부 투영 (재계산+픽셀화) ──
    ("재고장 엑셀이 지금 어떻게 보이는지 찍어봐",
     '[engines:render]{op: "xlsx", path: "재고장.xlsx"}',
     "engines", "single", "render,xlsx,장부,지각"),
    ("매출 장부 첫 두 쪽만 이미지로 뽑아줘",
     '[engines:render]{op: "xlsx", path: "매출장부.xlsx", pages: [1, 2]}',
     "engines", "single", "render,xlsx,pages"),
    ("근태표.xlsx 렌더해봐",                                     # op 생략 — 확장자 추론(Phase 1.5)
     '[engines:render]{path: "근태표.xlsx"}',
     "engines", "single", "render,xlsx,확장자추론"),
    ("Render the inventory ledger and show me how it looks",
     '[engines:render]{op: "xlsx", path: "inventory.xlsx"}',
     "engines", "single", "render,xlsx,english"),
    # ── 2층 텍스트 통로: 재계산 pdf_path 를 변수 필드로 읽기 ──
    ("정산표 수식이 실제로 계산된 값을 텍스트로 확인해줘",
     '$r = [engines:render]{op: "xlsx", path: "정산표.xlsx"}\n'
     '[self:read]{path: "${r.pdf_path}"}',
     "engines,self", "pipeline", "render,xlsx,재계산,변수필드,read"),
    # ── 지각→심사: criteria 취향 파일 "sheet" ──
    ("이 장부 렌더해서 장부 기준으로 쪽마다 심사해줘",
     '[engines:render]{op: "xlsx", path: "거래장부.xlsx"} >> '
     '[table:each]{do: "[engines:image_read]{op: \'critic\', image_path: \'$it.path\', '
     'intent: \'장부 $it.page 쪽이 잘림·수식 오류 없이 읽히는가\', criteria: \'sheet\'}"}',
     "engines,table", "pipeline", "검수,xlsx,critic,each,sheet기준"),
    # ── 편집→지각→심사: sheet 어휘와의 전체 반성 루프 ──
    ("재고장에 오늘 입고 추가하고 장부가 멀쩡한지 눈으로 확인해줘",
     '[self:sheet]{op: "append", path: "재고장.xlsx", items: [{"품목": "C형 부품", "수량": 30}]} >> '
     '[engines:render]{op: "xlsx", path: "재고장.xlsx"} >> '
     '[table:each]{do: "[engines:image_read]{op: \'critic\', image_path: \'$it.path\', '
     'intent: \'새 행이 표에 맞게 들어가고 합계가 성립하는가\', criteria: \'sheet\'}"}',
     "self,engines,table", "pipeline", "sheet,append,검수,반성루프"),
    # ── 얼린 문장(화면검수)과 루프 두 형태 ──
    ("화면검수 워크플로우로 이 장부 검사해줘",
     '[self:workflow]{op: "run", name: "화면검수", params: {path: "연차관리.xlsx", '
     'intent: "연차 관리 장부가 온전히 읽히는가", criteria: "sheet"}}',
     "self", "single", "workflow,검수,xlsx"),
    ("장부 검수가 통과할 때까지 서식을 다듬어줘",
     '[goal: "장부 검수 통과"]{success_condition: "렌더된 전 쪽의 critic 심사가 전부 passed", '
     'resources: ["sheet", "화면검수"], max_rounds: 3, report_to: "사용자"}',
     "goal", "single", "goal,검수루프,장부"),
    ("장부 렌더가 실패하면 한 번 더 시도하고 그래도 안 되면 알려줘",
     '$tries = 0\n$ok = 0\n[repeat: while $ok == 0 and $tries < 2, max: 2]{$tries = $tries + 1\n'
     '[try]{[engines:render]{op: "xlsx", path: "재고장.xlsx"}\n$ok = 1} '
     '[catch]{[self:notify_user]{message: "$tries 번째 장부 렌더 실패: $error.summary"}}}',
     "engines,self", "pipeline", "repeat,try,재시도,xlsx"),
]

if __name__ == "__main__":
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 - 시딩 중단(_index_batch 는 실패를 삼킨다)"
    import sqlite3
    conn = sqlite3.connect(str(ROOT / "data" / "ibl_usage.db"))
    existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    conn.close()
    batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
              "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
    print(f"시드 추가: {db.add_examples_batch(batch) if batch else 0}건 (중복 스킵 {len(NEW) - len(batch)}건)")
    dist_path = ROOT / "data" / "training" / "ibl_distilled.json"
    with open(dist_path, encoding="utf-8") as f:
        dist = json.load(f)
    have = {d.get("intent") for d in dist}
    added = 0
    for i, c, n, cat, t in NEW:
        if i not in have:
            dist.append({"intent": i, "ibl_code": c, "nodes": n, "category": cat,
                         "difficulty": 2, "source": "manual_seed"})
            added += 1
    if added:
        with open(dist_path, "w", encoding="utf-8") as f:
            json.dump(dist, f, ensure_ascii=False, indent=2)
    print(f"ibl_distilled: +{added}건 -> {len(dist)}건")
