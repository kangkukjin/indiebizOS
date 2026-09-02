"""
건강기록 DB person 프로필 통합 마이그레이션

두 person 프로필이 같은 사람일 때(예: "나" 와 실명 프로필) 앞 것을 뒤 것으로 합친다:
1. from 프로필의 데이터를 to 프로필로 이전
2. 2026-01-09 중복 레코드 정리
3. 2023-08-03 10:00 중복 삭제 (09:00 시리즈와 동일 검진)
4. from 프로필 삭제

★사람의 이름은 코드에 두지 않는다 — 인자로 받는다(몸의 명사=코드, 세계의 명사=데이터).
실행: python3 migrate_health_persons.py --to-name <실명> [--from-name 나 --from-id 1 --to-id 4 --drop-ids 7,8,10,22]
"""
import argparse
import os
import sqlite3
import shutil
from pathlib import Path

BASE = Path(__file__).parent.parent
DB_PATH = BASE / "data" / "health" / "health_records.db"
BACKUP_PATH = DB_PATH.with_suffix('.db.premigrate')


def _args():
    ap = argparse.ArgumentParser(description="건강기록 person 프로필 통합")
    ap.add_argument("--from-id", type=int, default=1)
    ap.add_argument("--from-name", default="나")
    ap.add_argument("--to-id", type=int, default=4)
    ap.add_argument("--to-name", required=True, help="합쳐질 대상 프로필의 이름(실명)")
    ap.add_argument("--drop-ids", default="7,8,10,22", help="to 프로필 안에서 중복으로 지울 measurements id")
    return ap.parse_args()


def main():
    a = _args()
    FROM_ID, FROM_NAME, TO_ID, TO_NAME = a.from_id, a.from_name, a.to_id, a.to_name
    DROP_IDS = tuple(int(x) for x in a.drop_ids.split(",") if x.strip())
    if not DB_PATH.exists():
        print(f"DB 없음: {DB_PATH}")
        return

    # 백업
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"백업: {BACKUP_PATH}")

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row

    # from 프로필 존재 확인
    row = conn.execute("SELECT id FROM persons WHERE id=? AND name=?", (FROM_ID, FROM_NAME)).fetchone()
    if not row:
        print(f"person '{FROM_NAME}'(id={FROM_ID}) 없음 — 이미 마이그레이션됨")
        conn.close()
        return

    # to 프로필 존재 확인
    row = conn.execute("SELECT id FROM persons WHERE id=? AND name=?", (TO_ID, TO_NAME)).fetchone()
    if not row:
        print(f"person '{TO_NAME}'(id={TO_ID}) 없음 — 수동 확인 필요")
        conn.close()
        return

    # 1: 2023 검진(09:00) → to 프로필로 이전
    n = conn.execute("UPDATE measurements SET person_id=? WHERE person_id=? AND measured_at LIKE '2023-08-03 09%'", (TO_ID, FROM_ID)).rowcount
    print(f"2023 검진(09:00) 이전: {n}건")

    # 2: 2023 중복(10:00) 삭제
    n = conn.execute("DELETE FROM measurements WHERE person_id=? AND measured_at LIKE '2023-08-03 10%'", (FROM_ID,)).rowcount
    print(f"2023 검진(10:00) 중복 삭제: {n}건")

    # 3: 2026-01-09 from 프로필 중복 삭제
    n = conn.execute("DELETE FROM measurements WHERE person_id=? AND measured_at LIKE '2026-01%'", (FROM_ID,)).rowcount
    print(f"2026-01-09 (person_id={FROM_ID}) 삭제: {n}건")

    # 4: to 프로필 안의 2026-01-09 버전 중복 정리 (--drop-ids)
    if DROP_IDS:
        marks = ",".join("?" * len(DROP_IDS))
        n = conn.execute(f"DELETE FROM measurements WHERE id IN ({marks})", DROP_IDS).rowcount
        print(f"2026-01-09 버전 중복 삭제: {n}건")

    # 5: 나머지 테이블 이전
    for table in ['measurements', 'documents', 'symptoms', 'medications']:
        n = conn.execute(f"UPDATE {table} SET person_id=? WHERE person_id=?", (TO_ID, FROM_ID)).rowcount
        if n:
            print(f"{table} 이전: {n}건")

    # 6: from 프로필 삭제
    conn.execute("DELETE FROM persons WHERE id=?", (FROM_ID,))
    print(f"person '{FROM_NAME}' 삭제")

    conn.commit()

    # 결과 확인
    print("\n=== 마이그레이션 완료 ===")
    total = conn.execute("SELECT COUNT(*) FROM measurements WHERE person_id=?", (TO_ID,)).fetchone()[0]
    print(f"{TO_NAME} measurements: {total}건")
    for p in conn.execute("SELECT id, name FROM persons ORDER BY id").fetchall():
        print(f"  person id={p['id']} name={p['name']}")

    conn.close()


if __name__ == "__main__":
    main()
