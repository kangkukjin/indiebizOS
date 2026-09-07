"""굳은 몸의 이름 회수 — 개인 명사가 박힌 본문에서 alias 를 뗀다 (2026-09-07 이름 전수 감사).

관측(이름 붙은 용례 44건 전수): 40건이 실행 0 인데 그 '실행 0' 은 한 부류가 아니었다. 그중 6건은
낡은 것도 헐거운 것도 아니고 **처음부터 다시 쓸 수 없는 몸** 이었다 — 본문에 `/Users/kangkukjin/…` 절대경로가
박히고 슬롯이 0 이라, 이름을 불러도 남의 그날 그 파일을 다시 만질 뿐이다. 전부 자동 작명 경로(category
`pipeline`/`single`)에서 태어났다: 관용구 증류는 `_phrase_private_reason` 을 부르는데 그 두 번째 경로는
안 불렀다(관문을 한쪽 길에만 단 부류). 관문은 같은 커밋에서 그 경로에도 달았고, 이 스크립트는 그 관문이
생기기 전에 이미 이름을 받은 것들을 **같은 자로** 쓸어낸다 — 사람이 고른 목록으로 쓸지 않는다.

본문·intent·topic·실행 이력은 건드리지 않는다. **떼는 것은 이름뿐**이다: 그 턴에 실제로 일어난 일이므로
용례로는 남을 값이 있고(회상의 낱말 채널), 다만 `[fn:이름]` 으로 다시 부를 수 있는 척하면 안 된다.

실행:
  .venv/bin/python backend/migrate_private_body_aliases.py --dry-run   # 미리보기만
  .venv/bin/python backend/migrate_private_body_aliases.py             # 실제 (스냅샷을 _backups 에 남긴다)
  .venv/bin/python backend/migrate_private_body_aliases.py --restore <스냅샷.json>   # 되돌리기
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: E402,F401

from ibl_idiom import _phrase_private_reason  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "ibl_usage.db"
SNAP_DIR = BASE / "data" / "_backups" / "2026-09-07_이름감사_굳은몸회수"


def _conn():
    c = sqlite3.connect(str(DB), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def targets(conn):
    """관문의 자가 잡는 이름 붙은 행 — 사람이 고른 범위가 아니라 관문이 고른 범위."""
    out = []
    for r in conn.execute("SELECT id, alias, intent, topic, category, success_count, fail_count, ibl_code "
                          "FROM ibl_examples WHERE COALESCE(alias,'') != ''"):
        why = _phrase_private_reason(r["ibl_code"])
        if why:
            out.append((dict(r), why))
    return out


def strip(dry: bool) -> int:
    conn = _conn()
    try:
        hits = targets(conn)
        if not hits:
            print("굳은 몸 이름 없음 — 할 일 없다.")
            return 0
        print(f"=== 이름 회수 대상 {len(hits)}건 {'(DRY-RUN)' if dry else ''} ===")
        ran = [h for h, _ in hits if (h["success_count"] or h["fail_count"])]
        for h, why in hits:
            mark = f'✓{h["success_count"]}/✗{h["fail_count"]}'
            print(f'  #{h["id"]:<6}{h["alias"]:<24}{h["topic"]:<22}{h["category"]:<9}{mark:<9}{why[:52]}')
        if ran:
            # 돈 적 있는 이름은 남의 실행 이력이다 — 이 스크립트의 관할이 아니다(사람이 판정할 것).
            print(f"\n중단: 실행 이력이 있는 이름 {len(ran)}건이 섞였다 — 손으로 판정할 것: "
                  f"{', '.join(x['alias'] for x in ran)}")
            return 0
        if dry:
            print("\n(dry-run — 아무것도 쓰지 않았다)")
            return 0
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        snap = SNAP_DIR / "stripped_aliases.json"
        snap.write_text(json.dumps([h for h, _ in hits], ensure_ascii=False, indent=1), encoding="utf-8")
        now = datetime.now().isoformat()
        conn.executemany("UPDATE ibl_examples SET alias='', updated_at=? WHERE id=?",
                         [(now, h["id"]) for h, _ in hits])
        conn.commit()
        print(f"\n이름 {len(hits)}건 회수. 스냅샷: {snap}")
        print("이어서 색인 갱신: .venv/bin/python -c \"from ibl_usage_db import IBLUsageDB; "
              "IBLUsageDB().rebuild_index()\"  (이름이 검색 텍스트에 섞여 있었다)")
        return len(hits)
    finally:
        conn.close()


def restore(path: str) -> int:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    conn = _conn()
    try:
        now = datetime.now().isoformat()
        conn.executemany("UPDATE ibl_examples SET alias=?, updated_at=? WHERE id=?",
                         [(r["alias"], now, r["id"]) for r in rows])
        conn.commit()
        print(f"이름 {len(rows)}건 복원.")
        return len(rows)
    finally:
        conn.close()


if __name__ == "__main__":
    if "--restore" in sys.argv:
        raise SystemExit(0 if restore(sys.argv[sys.argv.index("--restore") + 1]) else 1)
    strip("--dry-run" in sys.argv)
