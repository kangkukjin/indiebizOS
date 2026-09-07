"""일회성 몸의 이름 회수 — 이번 값이 얼어 있고 아무도 부르지 않는 이름을 뗀다 (2026-09-07 등록만 감사).

`migrate_private_body_aliases.py`(홈 절대경로=개인정보)의 형제. 그쪽이 **개인정보**를 봤다면 이쪽은
**일회성**을 본다: 슬롯 0(부를 때 바꿀 것이 없다) · 슬롯 6개 이상(서명이 본문만큼 길다) · 슬롯으로 안
비운 경로 리터럴(남의 그날 그 파일). 판정은 `ibl_idiom.frozen_incident_reason` — 등록 관문이 쓰는
바로 그 자다. 사람이 고른 목록으로 쓸지 않는다.

세 조건을 **모두** 만족해야 뗀다:
  ① 상시 소개가 아니다(always_on=0) — 어휘급은 사람이 이미 골랐다
  ② 한 번도 안 돌았다(✓0/✗0) — 한 번이라도 돈 이름은 남긴다
  ③ 아무 데서도 `[fn:이름]` 으로 참조되지 않는다 — 가이드·문서·코퍼스·코드 전부
     (가이드가 부르는 이름은 '등록만' 층의 정당한 주민이다: 앱 버튼·명시 호출의 자리)
  ④ 그리고 관문이 '얼어 있다'고 말한다

본문·intent·topic·이력은 건드리지 않는다. **떼는 것은 이름뿐**이다 — 그 턴에 실제로 일어난 일이라
용례로는 남을 값이 있고, 다만 `[fn:이름]` 으로 다시 부를 수 있는 척하면 안 된다.

실행:
  .venv/bin/python backend/retire_frozen_aliases.py --dry-run
  .venv/bin/python backend/retire_frozen_aliases.py
  .venv/bin/python backend/retire_frozen_aliases.py --restore <스냅샷.json>
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: E402,F401

from ibl_idiom import frozen_incident_reason  # noqa: E402
from ibl_usage_db import parse_signature  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "ibl_usage.db"
SNAP_DIR = BASE / "data" / "_backups" / "2026-09-07_등록만감사_일회성회수"
#: 이름 참조를 찾는 곳 — 가이드·문서·프롬프트·코드·학습 코퍼스.
SCAN_DIRS = ("data/guides", "data/system_docs", "data/common_prompts", "data/training",
             "data/packages", "backend", "scripts", "docs")
SCAN_EXT = {".md", ".py", ".json", ".yaml", ".yml", ".txt"}


def _conn():
    c = sqlite3.connect(str(DB), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _referenced_names() -> set:
    """`[fn:이름]` 으로 어디선가 불리는 이름 — 그런 이름은 '등록만' 층의 정당한 주민이다."""
    import re
    pat = re.compile(r'\[fn:\s*([^\]\s]+)\s*\]')
    found = set()
    for d in SCAN_DIRS:
        root = BASE / d
        if not root.is_dir():
            continue
        for f in root.rglob("*"):
            if not f.is_file() or f.suffix not in SCAN_EXT:
                continue
            if "_backups" in f.parts or ".venv" in f.parts:
                continue
            try:
                found |= set(pat.findall(f.read_text(encoding="utf-8", errors="ignore")))
            except Exception:
                continue
    return found


def targets(conn):
    """관문의 자가 고른 범위 — 사람이 고른 범위가 아니다."""
    refs = _referenced_names()
    out = []
    for r in conn.execute(
            "SELECT id, alias, intent, topic, success_count, fail_count, ibl_code, "
            "COALESCE(signature,'') AS sig, COALESCE(always_on,0) AS on_ "
            "FROM ibl_examples WHERE COALESCE(alias,'') != ''"):
        if r["on_"]:
            continue                                              # ① 어휘급은 사람이 골랐다
        if (r["success_count"] or 0) + (r["fail_count"] or 0):
            continue                                              # ② 한 번이라도 돈 이름은 남긴다
        if r["alias"] in refs:
            continue                                              # ③ 누가 부르고 있다
        names, known = parse_signature(r["sig"])
        why = frozen_incident_reason(r["ibl_code"], names if known else [])
        if why:
            out.append((dict(r), why))
    return out, refs


def main() -> int:
    dry = "--dry-run" in sys.argv
    with _conn() as conn:
        rows, refs = targets(conn)
        print(f"참조되는 이름 {len(refs)}건은 대상에서 뺀다 — 가이드·문서·코드가 부르는 이름")
        print(f"관문이 고른 회수 대상 {len(rows)}건\n")
        for r, why in rows:
            print(f"  #{r['id']:>5} {r['alias']:22} [{r['topic']}]  {why}")
        if dry or not rows:
            print("\n(미리보기 — 아무것도 바꾸지 않았다)" if dry else "\n(대상 없음)")
            return 0
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        snap = SNAP_DIR / "stripped_aliases.json"
        snap.write_text(json.dumps(
            {"at": datetime.now().isoformat(), "rows": [{"id": r["id"], "alias": r["alias"], "why": w}
                                                        for r, w in rows]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        for r, _w in rows:
            conn.execute("UPDATE ibl_examples SET alias='' WHERE id=?", (r["id"],))
        conn.commit()
        print(f"\n✓ 이름 {len(rows)}건 회수 — 본문·이력은 그대로. 되돌림: --restore {snap}")
    return 0


def restore(path: str) -> bool:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    with _conn() as conn:
        for r in data.get("rows", []):
            conn.execute("UPDATE ibl_examples SET alias=? WHERE id=?", (r["alias"], r["id"]))
        conn.commit()
    print(f"✓ 이름 {len(data.get('rows', []))}건 복원")
    return True


if __name__ == "__main__":
    if "--restore" in sys.argv:
        raise SystemExit(0 if restore(sys.argv[sys.argv.index("--restore") + 1]) else 1)
    raise SystemExit(main())
