"""
webcam_nearby 액션 흡수 마이그레이션 (1회성, #27).

[sense:webcam_nearby] → [sense:cctv]{op: "webcam", ...}.
- 학습 JSON(ibl_training_balanced) ibl_code 치환
- ibl_usage.db ibl_examples ibl_code 치환 (재색인은 rebuild_index 별도)
- world_pulse.db action_health/self_checks 의 webcam_nearby/webcam(옛 잔재) 행 삭제

실행: cd backend && python3 migrate_webcam_action.py
"""
import json
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # indiebizOS/
TRAINING = BASE / "data" / "training" / "ibl_training_balanced_20260516.json"
WORLD_PULSE = BASE / "data" / "world_pulse.db"


def transform(code: str) -> str:
    if not code:
        return code
    # 빈 중괄호 먼저
    code = code.replace('[sense:webcam_nearby]{}', '[sense:cctv]{op: "webcam"}')
    # 파라미터 있는 경우 — 여는 중괄호 직후 op 삽입
    code = re.sub(r'\[sense:webcam_nearby\]\{', '[sense:cctv]{op: "webcam", ', code)
    # 파라미터 없는 경우 (뒤에 { 없음)
    code = re.sub(r'\[sense:webcam_nearby\](?!\{)', '[sense:cctv]{op: "webcam"}', code)
    return code


def migrate_training():
    if not TRAINING.exists():
        print(f"[training] 파일 없음: {TRAINING}")
        return
    data = json.loads(TRAINING.read_text(encoding="utf-8"))
    n = 0
    for item in data:
        code = item.get("ibl_code")
        if code and "webcam_nearby" in code:
            new = transform(code)
            if new != code:
                item["ibl_code"] = new
                n += 1
    TRAINING.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[training] {n}건 ibl_code 치환 → {TRAINING.name}")


def migrate_usage_db():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    print(f"[usage_db] 경로: {getattr(db, 'db_path', '?')}")
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT id, ibl_code FROM ibl_examples WHERE ibl_code LIKE '%webcam_nearby%'"
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
        d1 = conn.execute(
            "DELETE FROM action_health WHERE action IN ('webcam_nearby','webcam')"
        ).rowcount
        d2 = conn.execute(
            "DELETE FROM self_checks WHERE action IN ('webcam_nearby','webcam')"
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
