#!/usr/bin/env python3
"""
2026-06-04 IBL 사용성 감사 후속 — CORPUS_PARAM_ALLOW 노이즈 정리.

핸들러가 실제로 읽지 않는 군더더기 param을 코퍼스에서 제거(relabel):
  - sense:pew_research  topic     (고정 RSS 아카이브 — 검색 안 함)
  - self:blog           sort       (latest는 이미 기본 pub_date DESC — 중복)
  - engines:web         font       (edit_styles는 theme/colors/radius만 — font 미지원)
  - engines:web_site    reference  (update_site는 고정 필드만 갱신 — 미사용)

적용 표면: training json 2파일 + usage_db ibl_examples (rebuild_index 별도).
사용법: python scripts/migrate_allowlist_cleanup.py [--apply]
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAINING = [
    ROOT / "data/training/ibl_training_balanced_20260516.json",
    ROOT / "data/training/ibl_distilled.json",
]
DB_PATH = ROOT / "data/ibl_usage.db"

TARGETS = [
    ("sense:pew_research", "topic"),
    ("self:blog", "sort"),
    ("engines:web", "font"),
    ("engines:web_site", "reference"),
]


def _split_pairs(inner: str):
    """{...} 내부를 따옴표 인식하며 key:value 쌍으로 분해."""
    parts, buf, in_str, q = [], "", False, ""
    for ch in inner:
        if in_str:
            buf += ch
            if ch == q:
                in_str = False
        elif ch in "\"'":
            in_str, q, buf = True, ch, buf + ch
        elif ch == ",":
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    pairs = []
    for p in parts:
        if ":" in p:
            k, v = p.split(":", 1)
            pairs.append((k.strip(), v.strip()))
    return pairs


def drop_param(code: str, action: str, param: str) -> str:
    pat = re.compile(r"(\[" + re.escape(action) + r"\])\s*\{([^}]*)\}")

    def repl(m):
        pairs = _split_pairs(m.group(2))
        kept = [(k, v) for (k, v) in pairs if k != param]
        if len(kept) == len(pairs):
            return m.group(0)
        if not kept:
            return m.group(1)  # 비는 경우 bare 액션
        body = ", ".join(f"{k}: {v}" for k, v in kept)
        return f"{m.group(1)}{{{body}}}"

    return pat.sub(repl, code)


def transform(code: str) -> str:
    for action, param in TARGETS:
        code = drop_param(code, action, param)
    return code


def main():
    apply = "--apply" in sys.argv
    total = 0

    # 1) training json
    for path in TRAINING:
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = 0
        for row in data:
            old = row.get("ibl_code", "")
            new = transform(old)
            if new != old:
                changed += 1
                if changed <= 3:
                    print(f"  [{path.name}] {old}  ->  {new}")
                row["ibl_code"] = new
        print(f"{path.name}: {changed}건 변경")
        total += changed
        if apply and changed:
            bak = path.with_suffix(path.suffix + ".bak_allowlist")
            if not bak.exists():
                bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) usage_db ibl_examples
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, ibl_code FROM ibl_examples").fetchall()
    db_changed = 0
    for r in rows:
        old = r["ibl_code"]
        new = transform(old)
        if new != old:
            db_changed += 1
            if apply:
                conn.execute("UPDATE ibl_examples SET ibl_code=? WHERE id=?", (new, r["id"]))
    print(f"usage_db ibl_examples: {db_changed}건 변경")
    if apply:
        conn.commit()
    conn.close()

    print(f"\n총 {total + db_changed}건 ({'적용됨' if apply else 'DRY-RUN — --apply로 적용'})")
    if apply:
        print("다음: 서버 python에서 IBLUsageDB().rebuild_index() 필요")


if __name__ == "__main__":
    main()
