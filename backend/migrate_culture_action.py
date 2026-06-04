"""
Culture 액션 통합 마이그레이션 (1회성, 2026-06-03).

옛 culture 액션 8개 → [sense:performance]{op}/[sense:book]{op}/[sense:classic]{op}.
- venue/genres/performance_regions → performance{op}
- recommended_books/kdc/library_regions → book{op}
- gutenberg_books/korean_classics → classic{op}
(performance/book/exhibit 는 이름 유지 + 기본 op라 변환 불필요.)

실행: cd backend && python3 migrate_culture_action.py
"""
import json
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TRAINING_FILES = [
    BASE / "data" / "training" / "ibl_training_balanced_20260516.json",
    BASE / "data" / "training" / "ibl_distilled.json",
]
WORLD_PULSE = BASE / "data" / "world_pulse.db"

MAP = {
    "venue":               ("performance", {"op": "venue"}),
    "genres":              ("performance", {"op": "genres"}),
    "performance_regions": ("performance", {"op": "regions"}),
    "recommended_books":   ("book",        {"op": "recommended"}),
    "kdc":                 ("book",        {"op": "codes", "code_type": "kdc"}),
    "library_regions":     ("book",        {"op": "codes", "code_type": "region"}),
    "gutenberg_books":     ("classic",     {"op": "western"}),
    "korean_classics":     ("classic",     {"op": "korean"}),
}
LSORT = sorted(MAP.keys(), key=len, reverse=True)


def _inject_str(inj: dict) -> str:
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


def _has_old(code: str) -> bool:
    return any(f'[sense:{a}]' in (code or "") for a in MAP)


def migrate_training():
    for path in TRAINING_FILES:
        if not path.exists():
            print(f"[training] 파일 없음: {path}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        n = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            code = item.get("ibl_code")
            if code and _has_old(code):
                new = transform(code)
                if new != code:
                    item["ibl_code"] = new
                    n += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[training] {n}건 ibl_code 치환 → {path.name}")


def migrate_usage_db():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    like = " OR ".join(["ibl_code LIKE ?"] * len(MAP))
    params = [f'%[sense:{a}]%' for a in MAP]
    with db._get_connection() as conn:
        rows = conn.execute(f"SELECT id, ibl_code FROM ibl_examples WHERE {like}", params).fetchall()
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
    old_actions = list(MAP.keys())
    ph = ",".join(["?"] * len(old_actions))
    conn = sqlite3.connect(str(WORLD_PULSE))
    try:
        d1 = conn.execute(f"DELETE FROM action_health WHERE action IN ({ph})", old_actions).rowcount
        d2 = conn.execute(f"DELETE FROM self_checks WHERE action IN ({ph})", old_actions).rowcount
        conn.commit()
        print(f"[world_pulse] action_health {d1}건, self_checks {d2}건 삭제")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_training()
    migrate_usage_db()
    migrate_world_pulse()
    print('완료. 이어서: python3 -c "from ibl_usage_db import IBLUsageDB; print(IBLUsageDB().rebuild_index())"')
