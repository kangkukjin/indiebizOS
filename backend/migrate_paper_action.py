"""
학술논문 + devdocs 액션 통합 마이그레이션 (1회성, 2026-06-03).

- search_openalex/arxiv/pubmed/semantic + download_arxiv/pubmed → [sense:paper]{op, source}
- search_library_docs/resolve_library → [sense:devdocs]{op}

실행: cd backend && python3 migrate_paper_action.py
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
    "search_openalex":     ("paper",   {"op": "search", "source": "openalex"}),
    "search_arxiv":        ("paper",   {"op": "search", "source": "arxiv"}),
    "search_pubmed":       ("paper",   {"op": "search", "source": "pubmed"}),
    "search_semantic":     ("paper",   {"op": "search", "source": "semantic"}),
    "download_arxiv":      ("paper",   {"op": "download", "source": "arxiv"}),
    "download_pubmed":     ("paper",   {"op": "download", "source": "pubmed"}),
    "search_library_docs": ("devdocs", {"op": "search"}),
    "resolve_library":     ("devdocs", {"op": "resolve"}),
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
    print("완료. rebuild_index 필요.")
