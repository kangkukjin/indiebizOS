"""
video 액션 통합 마이그레이션 (1회성, 2026-06-03).
video_info/transcript/languages/summarize_video → [sense:video]{op}.
실행: cd backend && python3 migrate_video_action.py
"""
import json, re, sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TRAINING_FILES = [
    BASE / "data" / "training" / "ibl_training_balanced_20260516.json",
    BASE / "data" / "training" / "ibl_distilled.json",
]
WORLD_PULSE = BASE / "data" / "world_pulse.db"

MAP = {
    "video_info":       ("video", {"op": "info"}),
    "video_transcript": ("video", {"op": "transcript"}),
    "video_languages":  ("video", {"op": "languages"}),
    "summarize_video":  ("video", {"op": "summarize"}),
}
LSORT = sorted(MAP.keys(), key=len, reverse=True)


def _inject_str(inj):
    return ", ".join(f'{k}: "{v}"' for k, v in inj.items())


def transform(code: str) -> str:
    if not code:
        return code
    for old in LSORT:
        new, inj = MAP[old]
        injs = _inject_str(inj)
        code = code.replace(f'[sense:{old}]{{}}', f'[sense:{new}]{{{injs}}}')
        code = re.sub(rf'\[sense:{old}\]\{{', f'[sense:{new}]{{{injs}, ', code)
        code = re.sub(rf'\[sense:{old}\](?!\{{)', f'[sense:{new}]{{{injs}}}', code)
    return code


def _has_old(code):
    return any(f'[sense:{a}]' in (code or "") for a in MAP)


def migrate_training():
    for path in TRAINING_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        n = 0
        for item in data:
            if isinstance(item, dict) and item.get("ibl_code") and _has_old(item["ibl_code"]):
                new = transform(item["ibl_code"])
                if new != item["ibl_code"]:
                    item["ibl_code"] = new
                    n += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[training] {n}건 → {path.name}")


def migrate_usage_db():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    like = " OR ".join(["ibl_code LIKE ?"] * len(MAP))
    params = [f'%[sense:{a}]%' for a in MAP]
    with db._get_connection() as conn:
        rows = conn.execute(f"SELECT id, ibl_code FROM ibl_examples WHERE {like}", params).fetchall()
        n = 0
        for rid, code in rows:
            new = transform(code)
            if new != code:
                conn.execute("UPDATE ibl_examples SET ibl_code=? WHERE id=?", (new, rid))
                n += 1
        conn.commit()
    print(f"[usage_db] {n}/{len(rows)}건")


def migrate_world_pulse():
    if not WORLD_PULSE.exists():
        return
    olds = list(MAP.keys())
    ph = ",".join(["?"] * len(olds))
    conn = sqlite3.connect(str(WORLD_PULSE))
    try:
        d1 = conn.execute(f"DELETE FROM action_health WHERE action IN ({ph})", olds).rowcount
        d2 = conn.execute(f"DELETE FROM self_checks WHERE action IN ({ph})", olds).rowcount
        conn.commit()
        print(f"[world_pulse] health {d1}, self_checks {d2} 삭제")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_training()
    migrate_usage_db()
    migrate_world_pulse()
    # 코드 호출처(시드/생성기) 동반 변환
    for fn in ["rebuild_usage_db.py", "ibl_usage_generator.py", "generate_missing_intents.py"]:
        p = Path(__file__).resolve().parent / fn
        if p.exists():
            p.write_text(transform(p.read_text(encoding="utf-8")), encoding="utf-8")
            print(f"[code] {fn} 변환")
    print("완료. rebuild_index 필요.")
