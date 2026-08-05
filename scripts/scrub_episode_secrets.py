#!/usr/bin/env python3
"""
scrub_episode_secrets.py - episode_log/episode_summary 에 이미 영속된 자격증명 일괄 마스킹

에피소드 로거가 도구 결과(stdout)를 통째로 박제하면서 설정 파일의 apiKey 등이
평문으로 남은 과거 행을 logging_utils.mask_secrets 로 정리하는 1회성 스크립트.
(신규 기록은 episode_logger._finalize 가 저장 직전에 같은 함수로 마스킹한다)

마스킹 후 WAL 체크포인트 + VACUUM 으로 프리리스트/WAL 에 남은 평문 잔재까지 지운다.

사용: python3 scripts/scrub_episode_secrets.py [--db 경로] [--dry-run]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

try:
    import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)
except ImportError:
    pass
from logging_utils import mask_secrets  # noqa: E402


def scrub(db_path: Path, dry_run: bool = False) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30)
    changed = {"episode_log": 0, "episode_summary": 0}

    for table, cols in (
        ("episode_log", ("log", "user_message")),
        ("episode_summary", ("user_message",)),
    ):
        rows = conn.execute(f"SELECT id, {', '.join(cols)} FROM {table}").fetchall()
        for row in rows:
            row_id, values = row[0], row[1:]
            updates = {}
            for col, val in zip(cols, values):
                if val:
                    masked = mask_secrets(val)
                    if masked != val:
                        updates[col] = masked
            if updates:
                changed[table] += 1
                if not dry_run:
                    sets = ", ".join(f"{c} = ?" for c in updates)
                    conn.execute(
                        f"UPDATE {table} SET {sets} WHERE id = ?",
                        (*updates.values(), row_id),
                    )
                print(f"  {table} id={row_id}: {', '.join(updates)} 마스킹")

    if not dry_run:
        conn.commit()
        # 평문 잔재 제거 — 덮어쓴 옛 페이지가 WAL/프리리스트에 남지 않도록
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    conn.close()

    mode = "(dry-run) " if dry_run else ""
    print(f"{mode}완료: episode_log {changed['episode_log']}행, "
          f"episode_summary {changed['episode_summary']}행 마스킹")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    default_db = Path(__file__).resolve().parent.parent / "data" / "world_pulse.db"
    parser.add_argument("--db", type=Path, default=default_db)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        sys.exit(f"DB 없음: {args.db}")
    scrub(args.db, dry_run=args.dry_run)
