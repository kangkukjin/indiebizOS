"""
blog 액션 통합 + kinsight 폐기 마이그레이션 (1회성, 2026-06-03).

- blog_posts/search/check_new/rebuild_index/stats → [self:blog]{op}
- kinsight/kinsight2 → 폐기 (코퍼스 항목 삭제, 옮길 곳 없음)

실행: cd backend && python3 migrate_blog_action.py
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
    "blog_posts":         ("blog", {"op": "posts"}),
    "blog_search":        ("blog", {"op": "search"}),
    "blog_check_new":     ("blog", {"op": "check_new"}),
    "blog_rebuild_index": ("blog", {"op": "rebuild_index"}),
    "blog_stats":         ("blog", {"op": "stats"}),
}
LSORT = sorted(MAP.keys(), key=len, reverse=True)
ABANDONED = ("kinsight", "kinsight2")  # 폐기 — 항목 삭제


def _inject_str(inj):
    return ", ".join(f'{k}: "{v}"' for k, v in inj.items())


def transform(code: str) -> str:
    if not code:
        return code
    for old in LSORT:
        new, inj = MAP[old]
        injs = _inject_str(inj)
        code = code.replace(f'[self:{old}]{{}}', f'[self:{new}]{{{injs}}}')
        code = re.sub(rf'\[self:{old}\]\{{', f'[self:{new}]{{{injs}, ', code)
        code = re.sub(rf'\[self:{old}\](?!\{{)', f'[self:{new}]{{{injs}}}', code)
    return code


def _is_abandoned(code):
    return any(f'[self:{a}]' in (code or "") for a in ABANDONED)


def migrate_training():
    for path in TRAINING_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        kept, dropped, changed = [], 0, 0
        for item in data:
            code = item.get("ibl_code", "") if isinstance(item, dict) else ""
            if _is_abandoned(code):
                dropped += 1
                continue  # kinsight 폐기 — 항목 제거
            if code:
                new = transform(code)
                if new != code:
                    item["ibl_code"] = new
                    changed += 1
            kept.append(item)
        path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[training] {changed}건 변환, {dropped}건 kinsight 삭제 → {path.name}")


def migrate_usage_db():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    with db._get_connection() as conn:
        # kinsight 폐기 — 행 삭제
        dl = conn.execute(
            "DELETE FROM ibl_examples WHERE ibl_code LIKE '%[self:kinsight]%' OR ibl_code LIKE '%[self:kinsight2]%'"
        ).rowcount
        like = " OR ".join(["ibl_code LIKE ?"] * len(MAP))
        params = [f'%[self:{a}]%' for a in MAP]
        rows = conn.execute(f"SELECT id, ibl_code FROM ibl_examples WHERE {like}", params).fetchall()
        n = 0
        for rid, code in rows:
            new = transform(code)
            if new != code:
                conn.execute("UPDATE ibl_examples SET ibl_code=? WHERE id=?", (new, rid))
                n += 1
        conn.commit()
    print(f"[usage_db] {n}건 변환, {dl}건 kinsight 삭제")


def migrate_world_pulse():
    if not WORLD_PULSE.exists():
        return
    olds = list(MAP.keys()) + list(ABANDONED)
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
    print("완료. rebuild_index 필요.")
