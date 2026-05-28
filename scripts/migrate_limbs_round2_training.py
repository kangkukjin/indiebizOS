#!/usr/bin/env python3
"""limbs 라운드 2 학습 데이터 마이그레이션 (2026-05-27).

13개 폐기 액션의 IBL 코드를 7개 통합 액션으로 재작성한다.
- 학습 JSON: data/training/ibl_training_balanced_20260516.json
- DB: data/ibl_usage.db (ibl_examples 테이블, FTS·vec 인덱스 동반 갱신은 별도)

알리아스(ibl_parser._ACTION_NAME_ALIASES)가 런타임 호환을 보장하므로
이 마이그레이션은 학습 코퍼스를 캐노니컬 어휘로 정규화하는 용도다.
"""
from __future__ import annotations
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "training" / "ibl_training_balanced_20260516.json"
DB_PATH = ROOT / "data" / "ibl_usage.db"

# (old_action, new_action, op_value, optional_param_rename {old: new})
MIGRATIONS = [
    ("dblclick", "click", "double", None),
    ("rightclick", "click", "right", None),
    ("back", "navigate", "back", None),
    ("forward", "navigate", "forward", None),
    ("get_html", "content", "html", None),
    ("console", "logs", "console", None),
    ("network_logs", "logs", "network", None),
    ("play", "music", "play", None),
    ("queue_add", "music", "add", None),
    ("skip", "music", "skip", None),
    ("queue", "music", "queue", None),
    ("stop", "music", "stop", None),
    ("youtube_download", "music", "download", None),
    ("radio_play", "radio", "play", {"station": "station_id"}),
    ("radio_stop", "radio", "stop", None),
    ("cctv_open", "cctv", "open", None),
    ("cctv_capture", "cctv", "capture", {"source": "name"}),
]


def _rewrite_block(code: str, old: str, new: str, op_value: str, rename: dict | None) -> str:
    """`[limbs:old]{params}` 또는 `[limbs:old]`를 `[limbs:new]{op: "...", params}`로."""
    # 파라미터가 있는 경우
    pat_with = re.compile(r"\[limbs:" + re.escape(old) + r"\]\{([^}]*)\}")

    def repl_with(m: re.Match) -> str:
        inner = m.group(1).strip()
        if rename:
            for k_old, k_new in rename.items():
                inner = re.sub(rf"\b{re.escape(k_old)}\s*:", f"{k_new}:", inner)
        # 기존 inner에 op 키가 있으면 (드물지만) 그대로 두고, 없으면 앞에 주입.
        if re.search(r"(?<![A-Za-z_])op\s*:", inner):
            new_inner = inner
        else:
            new_inner = f'op: "{op_value}"' + (", " + inner if inner else "")
        return "[limbs:" + new + "]{" + new_inner + "}"

    code = pat_with.sub(repl_with, code)

    # 파라미터가 없는 경우 (뒤에 { 없음)
    pat_bare = re.compile(r"\[limbs:" + re.escape(old) + r"\](?!\{)")
    code = pat_bare.sub(f'[limbs:{new}]{{op: "{op_value}"}}', code)
    return code


def migrate_code(code: str) -> str:
    for old, new, op_value, rename in MIGRATIONS:
        code = _rewrite_block(code, old, new, op_value, rename)
    return code


def main() -> int:
    # ── JSON 마이그레이션 ──────────────────────────────────────────
    if not JSON_PATH.exists():
        print(f"[migrate] JSON 없음: {JSON_PATH}")
        return 2

    with JSON_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    changed = 0
    for ex in data:
        before = ex.get("ibl_code", "")
        after = migrate_code(before)
        if before != after:
            ex["ibl_code"] = after
            changed += 1

    JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[migrate] JSON: {changed}개 갱신 / 전체 {len(data)}")

    # ── DB 마이그레이션 ────────────────────────────────────────────
    if not DB_PATH.exists():
        print(f"[migrate] DB 없음, 건너뜀: {DB_PATH}")
        return 0

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, ibl_code FROM ibl_examples")
    rows = cur.fetchall()
    db_changed = 0
    for row_id, code in rows:
        if not code:
            continue
        new = migrate_code(code)
        if new != code:
            cur.execute(
                "UPDATE ibl_examples SET ibl_code = ?, updated_at = datetime('now') WHERE id = ?",
                (new, row_id),
            )
            db_changed += 1
    con.commit()
    con.close()
    print(f"[migrate] DB: {db_changed}개 갱신 / 전체 {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
