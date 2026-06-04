"""
Finance 액션 통합 마이그레이션 (1회성, 2026-06-03).

옛 16개 finance 액션 → [sense:stock]{op}/[sense:company]{op}.
- 학습 JSON(ibl_training_balanced, ibl_distilled) ibl_code 치환
- ibl_usage.db ibl_examples ibl_code 치환 (재색인은 rebuild_index 별도)
- world_pulse.db action_health/self_checks 의 옛 액션명 행 삭제

market 은 옛 kr_/us_ 접두 의미를 주입파라미터로 보존(무손실).
crypto 는 그대로 유지(변경 없음).

실행: cd backend && python3 migrate_finance_action.py
"""
import json
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # indiebizOS/
TRAINING_FILES = [
    BASE / "data" / "training" / "ibl_training_balanced_20260516.json",
    BASE / "data" / "training" / "ibl_distilled.json",
]
WORLD_PULSE = BASE / "data" / "world_pulse.db"

# 옛 액션 → (새 액션, 주입 op/market). 긴 키부터 처리해 부분일치 방지.
MAP = {
    "price":             ("stock",   {"op": "quote"}),
    "stock_info":        ("stock",   {"op": "info"}),
    "search_stock":      ("stock",   {"op": "search"}),
    "kr_price":          ("stock",   {"op": "price", "market": "kr"}),
    "us_price":          ("stock",   {"op": "price", "market": "us"}),
    "kr_investor":       ("stock",   {"op": "investors", "market": "kr"}),
    "kr_stock_investor": ("stock",   {"op": "investors"}),
    "news":              ("stock",   {"op": "news"}),
    "earnings":          ("stock",   {"op": "earnings"}),
    "kr_company":        ("company", {"op": "profile", "market": "kr"}),
    "us_company":        ("company", {"op": "profile", "market": "us"}),
    "kr_financial":      ("company", {"op": "financials", "market": "kr"}),
    "us_financial":      ("company", {"op": "financials", "market": "us"}),
    "kr_disclosure":     ("company", {"op": "disclosures", "market": "kr"}),
    "us_filing":         ("company", {"op": "disclosures", "market": "us"}),
}

# 옛 액션이 매핑된 KRX market 코드(STK/KSQ/ALL)를 보존하기 위해, kr_investor 등은
# 주입 market 을 "kr"로 두되 본문에 이미 market 파라미터가 있으면 그대로 둔다(파서와 동일 규칙).

LSORT = sorted(MAP.keys(), key=len, reverse=True)


def _inject_str(inj: dict) -> str:
    """{'op':'price','market':'kr'} → 'op: \"price\", market: \"kr\"'"""
    return ", ".join(f'{k}: "{v}"' for k, v in inj.items())


def transform(code: str) -> str:
    if not code:
        return code
    for old in LSORT:
        new, inj = MAP[old]
        injs = _inject_str(inj)
        # 빈 중괄호
        code = code.replace(f'[sense:{old}]{{}}', f'[sense:{new}]{{{injs}}}')
        # 파라미터 있는 경우 — 여는 중괄호 직후 주입
        code = re.sub(rf'\[sense:{old}\]\{{', f'[sense:{new}]{{{injs}, ', code)
        # 파라미터 없는 경우 (뒤에 { 없음)
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
            print(f"[training] list 아님, 건너뜀: {path.name}")
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
    print(f"[usage_db] 경로: {getattr(db, 'db_path', '?')}")
    like = " OR ".join(["ibl_code LIKE ?"] * len(MAP))
    params = [f'%[sense:{a}]%' for a in MAP]
    with db._get_connection() as conn:
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
    old_actions = list(MAP.keys())
    placeholders = ",".join(["?"] * len(old_actions))
    conn = sqlite3.connect(str(WORLD_PULSE))
    try:
        d1 = conn.execute(
            f"DELETE FROM action_health WHERE action IN ({placeholders})", old_actions
        ).rowcount
        d2 = conn.execute(
            f"DELETE FROM self_checks WHERE action IN ({placeholders})", old_actions
        ).rowcount
        conn.commit()
        print(f"[world_pulse] action_health {d1}건, self_checks {d2}건 삭제")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_training()
    migrate_usage_db()
    migrate_world_pulse()
    print('완료. 이어서: python3 -c "from ibl_usage_db import IBLUsageDB; print(IBLUsageDB().rebuild_index())"')
