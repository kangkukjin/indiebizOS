"""어휘 개념중복 압축 1단계 — 싼 병합 5건 코퍼스 이관 (1회성, 2026-08-05).

  [self:fs_query]{...}           → [self:file_find]{...}          (params 그대로 — 스키마 유니온)
  [self:agents]{...} / [self:agents] → [others:agents]{...}       (nodes self→others 재계산)
  [self:run_pipeline]{...}       → [self:workflow]{op: "run", ...}
  [engines:image_critic]{...}    → [engines:image_read]{op: "critic", ...}
  [self:output]{op: "file", ...} → [self:write]{...}              (op 키 제거, path/content 보존)

- ibl_usage.db ibl_examples ibl_code + nodes 치환 (재색인은 rebuild_index 별도)
- data/training/ibl_distilled.json 동기 치환

실행: cd backend && python3 migrate_vocab_cheap_merges.py
"""
import json
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # indiebizOS/
USAGE_DB = BASE / "data" / "ibl_usage.db"
DISTILLED = BASE / "data" / "training" / "ibl_distilled.json"


def transform(code: str) -> str:
    if not code:
        return code
    # 1) fs_query → file_find (params 그대로)
    code = code.replace("[self:fs_query]", "[self:file_find]")
    # 2) self:agents → others:agents (bare 형태 포함)
    code = code.replace("[self:agents]", "[others:agents]")
    # 3) run_pipeline → workflow{op: run}
    code = code.replace("[self:run_pipeline]{}", '[self:workflow]{op: "run"}')
    code = re.sub(r"\[self:run_pipeline\]\{", '[self:workflow]{op: "run", ', code)
    code = re.sub(r"\[self:run_pipeline\](?!\{)", '[self:workflow]{op: "run"}', code)
    # 4) image_critic → image_read{op: critic}
    code = code.replace("[engines:image_critic]{}", '[engines:image_read]{op: "critic"}')
    code = re.sub(r"\[engines:image_critic\]\{", '[engines:image_read]{op: "critic", ', code)
    code = re.sub(r"\[engines:image_critic\](?!\{)", '[engines:image_read]{op: "critic"}', code)
    # 5) output op:file → write (op 키만 제거 — 앞/중간/단독 위치 모두)
    def _output_file_to_write(m):
        params = m.group(1)
        params = re.sub(r"""op:\s*["']file["']\s*,\s*""", "", params, count=1)
        params = re.sub(r"""\s*,\s*op:\s*["']file["']""", "", params, count=1)
        params = re.sub(r"""^op:\s*["']file["']$""", "", params.strip(), count=1)
        return "[self:write]{" + params + "}"
    code = re.sub(r"\[self:output\]\{([^}]*op:\s*[\"']file[\"'][^}]*)\}",
                  _output_file_to_write, code)
    return code


_OLD = re.compile(r"\[self:fs_query\]|\[self:agents\]|\[self:run_pipeline\]"
                  r"|\[engines:image_critic\]|\[self:output\]\{[^}]*op:\s*[\"']file[\"']")


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
