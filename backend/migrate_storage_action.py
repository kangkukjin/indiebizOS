"""
storage/folder 액션 통합 마이그레이션 (1회성, #29).

[self:storage_scan]/[self:storage_summary]/[self:volumes] → [self:storage]{op: ...}
[self:folder_annotate]/[self:folder_annotations]    → [self:folder_note]{op: ...}
- 학습 JSON(ibl_training_balanced) ibl_code 치환
- ibl_usage.db ibl_examples ibl_code 치환 (재색인은 rebuild_index 별도)
- world_pulse.db action_health/self_checks 옛 액션행 삭제

실행: cd backend && python3 migrate_storage_action.py
"""
import json
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # indiebizOS/
TRAINING = BASE / "data" / "training" / "ibl_training_balanced_20260516.json"
WORLD_PULSE = BASE / "data" / "world_pulse.db"

# 옛 액션명 → (새 액션, op). 긴 이름 먼저(prefix 충돌 방지: folder_annotations 먼저).
MAP = [
    ("storage_summary", "storage", "summary"),
    ("storage_scan", "storage", "scan"),
    ("volumes", "storage", "volumes"),
    ("folder_annotations", "folder_note", "get"),
    ("folder_annotate", "folder_note", "set"),
]
OLD_NAMES = [m[0] for m in MAP]


def transform(code: str) -> str:
    if not code:
        return code
    for old, new, op in MAP:
        # 빈 중괄호
        code = code.replace(f'[self:{old}]{{}}', f'[self:{new}]{{op: "{op}"}}')
        # 파라미터 있는 경우 — 여는 중괄호 직후 op 삽입
        code = re.sub(r'\[self:' + old + r'\]\{', f'[self:{new}]{{op: "{op}", ', code)
        # 파라미터 없는 경우 (뒤에 { 없음)
        code = re.sub(r'\[self:' + old + r'\](?!\{)', f'[self:{new}]{{op: "{op}"}}', code)
    return code


def _has_old(code: str) -> bool:
    return any(re.search(r'\[self:' + n + r'[\]{ ]', code or '') for n in OLD_NAMES)


def migrate_training():
    if not TRAINING.exists():
        print(f"[training] 파일 없음: {TRAINING}")
        return
    data = json.loads(TRAINING.read_text(encoding="utf-8"))
    n = 0
    for item in data:
        code = item.get("ibl_code")
        if code and _has_old(code):
            new = transform(code)
            if new != code:
                item["ibl_code"] = new
                n += 1
    TRAINING.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[training] {n}건 ibl_code 치환 → {TRAINING.name}")


def migrate_usage_db():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    with db._get_connection() as conn:
        like = " OR ".join(["ibl_code LIKE ?"] * len(OLD_NAMES))
        params = [f"%self:{n}%" for n in OLD_NAMES]
        rows = conn.execute(
            f"SELECT id, ibl_code FROM ibl_examples WHERE {like}", params
        ).fetchall()
        n = 0
        for row in rows:
            rid, code = row[0], row[1]
            new = transform(code)
            if new != code:
                conn.execute("UPDATE ibl_examples SET ibl_code=? WHERE id=?", (new, rid))
                n += 1
        conn.commit()
    print(f"[usage_db] {n}/{len(rows)}건 ibl_code 치환 (재색인은 rebuild_index 별도)")


def migrate_world_pulse():
    if not WORLD_PULSE.exists():
        print(f"[world_pulse] 파일 없음: {WORLD_PULSE}")
        return
    conn = sqlite3.connect(str(WORLD_PULSE))
    try:
        ph = ",".join("?" * len(OLD_NAMES))
        d1 = conn.execute(
            f"DELETE FROM action_health WHERE action IN ({ph})", OLD_NAMES
        ).rowcount
        d2 = conn.execute(
            f"DELETE FROM self_checks WHERE action IN ({ph})", OLD_NAMES
        ).rowcount
        conn.commit()
        print(f"[world_pulse] action_health {d1}건, self_checks {d2}건 삭제")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_training()
    migrate_usage_db()
    migrate_world_pulse()
    print("완료. 이어서: python3 -c \"from ibl_usage_db import IBLUsageDB; print(IBLUsageDB().rebuild_index())\"")
