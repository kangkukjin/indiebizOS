"""
Web 액션 통합 마이그레이션 (1회성, 2026-06-03).

engines/web_builder 9개(+이전 스킴 잔재) → [engines:web]{op}/[engines:web_component]{op}/[engines:web_site]{op}.
web/web_component/web_site 는 이름 유지(또는 기본 op)라 그 자체는 변환 불필요.

실행: cd backend && python3 migrate_web_action.py
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

# 옛 액션 → (새 액션, 주입). 현 9개 + 이전 per-tool 스킴 잔재 모두.
MAP = {
    # 생애주기 → web
    "web_create_site": ("web", {"op": "create", "target": "site"}),
    "web_create_page": ("web", {"op": "create", "target": "page"}),
    "web_create":      ("web", {"op": "create"}),
    "web_build":       ("web", {"op": "build"}),
    "web_deploy":      ("web", {"op": "deploy"}),
    "web_preview":     ("web", {"op": "preview"}),
    "web_snapshot":    ("web", {"op": "snapshot"}),
    "web_live_check":  ("web", {"op": "check"}),
    # 컴포넌트 → web_component
    "web_catalog":          ("web_component", {"op": "catalog"}),
    "web_list_components":   ("web_component", {"op": "catalog", "kind": "components"}),
    "web_list_sections":     ("web_component", {"op": "catalog", "kind": "sections"}),
    "web_fetch_component":   ("web_component", {"op": "fetch"}),
    "web_add_component":     ("web_component", {"op": "add"}),
    # 레지스트리 → web_site
    "web_site_list":     ("web_site", {"op": "list"}),
    "web_site_register": ("web_site", {"op": "register"}),
    "web_site_remove":   ("web_site", {"op": "remove"}),
    "web_site_update":   ("web_site", {"op": "update"}),
}
# 길이 내림차순 — web_create_site 가 web_create 보다 먼저.
LSORT = sorted(MAP.keys(), key=len, reverse=True)


def _inject_str(inj):
    return ", ".join(f'{k}: "{v}"' for k, v in inj.items())


def transform(code: str) -> str:
    if not code:
        return code
    for old in LSORT:
        new, inj = MAP[old]
        injs = _inject_str(inj)
        code = code.replace(f'[engines:{old}]{{}}', f'[engines:{new}]{{{injs}}}')
        code = re.sub(rf'\[engines:{old}\]\{{', f'[engines:{new}]{{{injs}, ', code)
        code = re.sub(rf'\[engines:{old}\](?!\{{)', f'[engines:{new}]{{{injs}}}', code)
    return code


def _has_old(code: str) -> bool:
    return any(f'[engines:{a}]' in (code or "") for a in MAP)


def migrate_training():
    for path in TRAINING_FILES:
        if not path.exists():
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
    params = [f'%[engines:{a}]%' for a in MAP]
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
    print(f"[usage_db] {n}/{len(rows)}건 ibl_code 치환 (재색인 별도)")


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
        print(f"[world_pulse] action_health {d1}건, self_checks {d2}건 삭제")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_training()
    migrate_usage_db()
    migrate_world_pulse()
    print('완료. 이어서: rebuild_index()')
