"""어휘 개념중복 압축 2단계 — 검색 통합 코퍼스 이관 (1회성, 2026-08-05).

  [sense:search_ddg]{...}      → [sense:search]{...}                      (ddg=기본 source, 키 생략)
  [sense:search_naver]{...}    → [sense:search]{source: "naver", ...}
  [sense:search_gnews]{...}    → [sense:search]{source: "gnews", ...}
  [sense:search_hn]{...}       → [sense:search]{source: "hn", ...}
  [sense:search_guardian]{...} → [sense:search]{source: "guardian", ...}

파라미터는 그대로 보존(display/page_size 는 액션의 aliases 가 count 로 흡수).
- ibl_usage.db ibl_examples ibl_code + nodes 치환 (재색인은 rebuild_index 별도)
- data/training/ibl_distilled.json 동기 치환

실행: python3 scripts/migrate_vocab_search_merge.py
(backend/ 가 아닌 scripts/ 에 두는 이유: 폰 번들 스캔 범위 밖 — force_exclude 선언 불요)
"""
import json
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # indiebizOS/
USAGE_DB = BASE / "data" / "ibl_usage.db"
DISTILLED = BASE / "data" / "training" / "ibl_distilled.json"

_SOURCED = {"search_naver": "naver", "search_gnews": "gnews",
            "search_hn": "hn", "search_guardian": "guardian"}


def transform(code: str) -> str:
    if not code:
        return code
    # ddg = 기본 source — 키 없이 액션명만 교체
    code = code.replace("[sense:search_ddg]", "[sense:search]")
    for old, src in _SOURCED.items():
        code = code.replace(f"[sense:{old}]{{}}", f'[sense:search]{{source: "{src}"}}')
        code = re.sub(rf"\[sense:{old}\]\{{", f'[sense:search]{{source: "{src}", ', code)
        code = re.sub(rf"\[sense:{old}\](?!\{{)", f'[sense:search]{{source: "{src}"}}', code)
    return code


_OLD = re.compile(r"\[sense:search_(ddg|naver|gnews|hn|guardian)\]")


def _nodes_of(code: str) -> str:
    return ",".join(sorted({m.group(1) for m in re.finditer(r"\[(\w+):\w+\]", code or "")}))


def migrate_db() -> int:
    conn = sqlite3.connect(USAGE_DB)
    rows = conn.execute("SELECT id, ibl_code, nodes FROM ibl_examples").fetchall()
    n = 0
    for rid, code, nodes in rows:
        if not code or not _OLD.search(code):
            continue
        new_code = transform(code)
        conn.execute("UPDATE ibl_examples SET ibl_code=?, nodes=? WHERE id=?",
                     (new_code, _nodes_of(new_code), rid))
        n += 1
    conn.commit()
    conn.close()
    return n


def migrate_distilled() -> int:
    if not DISTILLED.exists():
        return 0
    data = json.loads(DISTILLED.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("examples", [])
    n = 0
    for it in items:
        code = it.get("ibl_code") or it.get("code") or ""
        if _OLD.search(code):
            new_code = transform(code)
            if "ibl_code" in it:
                it["ibl_code"] = new_code
            else:
                it["code"] = new_code
            if "nodes" in it:
                it["nodes"] = _nodes_of(new_code)
            n += 1
    DISTILLED.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return n


if __name__ == "__main__":
    print(f"ibl_examples 치환: {migrate_db()}행")
    print(f"ibl_distilled 치환: {migrate_distilled()}건")
    print("다음: IBLUsageDB().rebuild_index() (재색인)")
