"""파일 목록 열 이름 시딩 (2026-08-30, ep2355·2356 열 이름 추측 부류).

실측: 에이전트가 파일 목록(self:list/file_find)의 열을 영어(name/size/mtime)로
추측해 sort/select 가 정직 에러로 한 라운드씩 죽었다(ep2355 select, ep2356 sort).
진실: 파일 목록의 table 열 = ["이름", "크기", "수정일", "경로"] (한글, 영어 의도여도 동일).
      sense 계열 items 의 표준 필드 = title/meta/summary/url (여긴 영어가 맞다).
desc 에는 열 이름이 없다 — 이 스키마 지식의 정본 통로는 해마 용례다
(no-switchization: 처방 = 시딩·desc 개선).

실행: .venv/bin/python3 scripts/seed_table_column_names.py
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
    # ── 파일 목록의 열 = 이름/크기/수정일/경로 ──
    ("다운로드 폴더에서 최근에 고친 파일 5개만 보여줘",
     '[self:list]{path: "~/Downloads"} >> [table:sort]{by: "수정일", desc: true} >> [table:take]{n: 5}',
     "self,table", "pipeline", "열이름,파일목록,수정일,최신"),
    ("이 폴더에서 용량 큰 파일 10개 찾아줘",
     '[self:list]{path: "."} >> [table:sort]{by: "크기", desc: true} >> [table:take]{n: 10}',
     "self,table", "pipeline", "열이름,파일목록,크기"),
    ("출력 폴더 파일 목록에서 이름과 수정일만 추려줘",
     '[self:list]{path: "outputs"} >> [table:select]{columns: ["이름", "수정일"]}',
     "self,table", "pipeline", "열이름,파일목록,select"),
    # ep2356 실패의 성공형 — 날짜 접두 파일명은 이름 내림차순 = 최신순
    ("공유창고 부동산 보고서 최신 3개 뭐 있는지 봐줘",
     '[self:list]{path: "공유창고/0/부동산 보고서"} >> [table:sort]{by: "이름", desc: true} >> '
     '[table:take]{n: 3} >> [table:select]{columns: ["이름", "크기"]}',
     "self,table", "pipeline", "열이름,파일목록,최신,보고서"),
    # ep2355 실패의 성공형 — file_find 도 같은 한글 열
    ("최근 AI 동향 보고서 파일 5개 찾아줘",
     '[self:file_find]{path: "outputs/ai_trend_reports", pattern: "ai_trend_report_*.md"} >> '
     '[table:sort]{by: "이름", desc: true} >> [table:take]{n: 5} >> '
     '[table:select]{columns: ["이름", "수정일"]}',
     "self,table", "pipeline", "열이름,file_find,최신,보고서"),
    # 영어 의도여도 파일 목록 열은 한글이다
    ("Show the 5 most recently modified files in the outputs folder",
     '[self:list]{path: "outputs"} >> [table:sort]{by: "수정일", desc: true} >> [table:take]{n: 5}',
     "self,table", "pipeline", "열이름,파일목록,수정일,english"),
    # 대조 쌍 — sense 계열 items 의 표준 필드는 영어(title/meta/summary/url)
    ("검색 결과를 제목 가나다순으로 정렬해서 보여줘",
     '[sense:search]{query: "AI 에이전트"} >> [table:sort]{by: "title"}',
     "sense,table", "pipeline", "열이름,items표준필드,title,정렬"),
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
