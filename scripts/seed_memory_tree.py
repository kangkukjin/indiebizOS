"""심층 기억 주제 트리 어휘(recall/move/node) 해마 시딩 (2026-09-03).
라이브 실측: <memory_map> 에 가지가 보여도 실행자가 옛 습관대로 search 를 불렀다(해마에 recall 용례 0, search 41).
결정화된 통로가 지정되지 않으면 매 호 재발명된다 — 지도→recall 통로를 용례로 박는다 + search 영토 보존 대조 시드.
★실행: .venv 파이썬(sqlite_vec) + _load_model_sync 후 색인.
"""
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend"))
import boot_paths  # noqa: F401

SEEDS = [
    {"intent": "내 어머니 연세가 어떻게 되시지? (기억 지도에 '가족/어머니' 가지가 보인다 — 그 가지를 연다)",
     "ibl_code": '[self:memory]{op: "recall", node: "가족/어머니"}', "nodes": "self"},
    {"intent": "내 차 모델이 뭐였지? 지도의 기기·차량 가지를 열어 확인",
     "ibl_code": '[self:memory]{op: "recall", node: "사용자/기기·차량"}', "nodes": "self"},
    {"intent": "지난번에 정한 부동산 매물 조건이 뭐였지?",
     "ibl_code": '[self:memory]{op: "recall", node: "부동산"}', "nodes": "self"},
    {"intent": "내 기억에 어떤 가지들이 있는지 지도를 보여줘",
     "ibl_code": '[self:memory]{op: "recall"}', "nodes": "self"},
    {"intent": "어머니 건강 기록을 시간순으로 요약해줘",
     "ibl_code": '[self:memory]{op: "recall", node: "가족/어머니"} >> [table:brief]{instruction: "건강 관련 기억만 시간순 요약"}',
     "nodes": "self,table"},
    {"intent": "이건 기억해둬 — 부동산 보고서는 매주 월요일에만 받겠다 (가지를 붙여 저장)",
     "ibl_code": '[self:memory]{op: "save", node: "보고서/부동산 발굴", category: "의사결정", content: "부동산 보고서는 매주 월요일에만 받는다"}',
     "nodes": "self"},
    {"intent": "기억 123 은 가족 가지에 있어야 해, 옮겨줘",
     "ibl_code": '[self:memory]{op: "move", memory_id: 123, node: "가족"}', "nodes": "self"},
    {"intent": "라벨 프린터 모델을 어딘가 기억해뒀는데 어느 가지인지 모르겠다 — 검색",
     "ibl_code": '[self:memory]{op: "search", query: "라벨 프린터 모델"}', "nodes": "self"},
    {"intent": "AI 동향 보고서 가지 안에서 특별기고 규칙만 찾아줘",
     "ibl_code": '[self:memory]{op: "search", query: "특별기고 규칙", node: "보고서/AI 동향"}', "nodes": "self"},
]


def main():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    db._load_model_sync()          # ★벡터 침묵 누락 함정 — 모델 동기 로드 후 색인
    import sqlite3
    conn = sqlite3.connect(db.db_path if hasattr(db, "db_path") else os.path.join(_ROOT, "data", "ibl_usage.db"))
    have = {r[0] for r in conn.execute("SELECT ibl_code FROM ibl_examples").fetchall()}
    conn.close()
    batch = [dict(s, source="manual_seed", category="memory") for s in SEEDS if s["ibl_code"] not in have]
    print(f"시드 추가: {db.add_examples_batch(batch) if batch else 0}건 (중복 스킵 {len(SEEDS) - len(batch)}건)")


if __name__ == "__main__":
    main()
