"""union/merge 죽은 분기 규약 시딩 (2026-08-30 언어 개정, ep2355).

기본 = 죽은 분기 건너뛰고 신고(branches_skipped) — 문장에 아무것도 안 적어도 된다.
전부-아니면-실패가 필요할 때만 on_error:"stop" 을 적는다.

실행: .venv/bin/python3 scripts/seed_union_dead_branch.py
(system python3 은 sqlite_vec 가 없다 — .venv 필수)
"""
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
    ("뉴스 사이트 몇 곳을 긁어서 모아줘, 한두 곳이 안 열려도 되는 것만 합치면 돼",
     '([sense:crawl]{url: "https://news.example.com/a"} >> [table:take]{n: 30}) & '
     '([sense:crawl]{url: "https://news.example.com/b"} >> [table:take]{n: 30}) & '
     '([sense:crawl]{url: "https://news.example.com/c"} >> [table:take]{n: 30}) >> '
     '[table:union] >> [table:dedup]{by: "title"}',
     "sense,table", "pipeline", "union,죽은분기,부분결합,크롤"),
    ("두 소스를 합치되 하나라도 실패하면 합치지 말고 실패로 알려줘",
     '[sense:search]{source: "gnews", query: "AI"} & [sense:search]{source: "naver", query: "AI"} >> '
     '[table:union]{on_error: "stop"}',
     "sense,table", "pipeline", "union,on_error,stop,전부아니면실패"),
    ("검색 결과 여러 개를 제목 중복 없이 한 목록으로, 실패한 검색은 빼고",
     '[sense:search]{query: "부동산 전세"} & [sense:search]{source: "naver", query: "전세 시세"} >> '
     '[table:merge]{by: "title"}',
     "sense,table", "pipeline", "merge,죽은분기,부분결합,중복제거"),
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
