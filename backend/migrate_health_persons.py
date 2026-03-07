"""
건강기록 DB person 프로필 통합 마이그레이션

"나"(id=1)와 "강국진"(id=4)이 같은 사람이므로:
1. person_id=1의 데이터를 person_id=4로 이전
2. 2026-01-09 중복 레코드 정리
3. 2023-08-03 10:00 중복 삭제 (09:00 시리즈와 동일 검진)
4. person "나" 삭제

실행: python3 migrate_health_persons.py
"""
import os
import sqlite3
import shutil
from pathlib import Path

BASE = Path(__file__).parent.parent
DB_PATH = BASE / "data" / "health" / "health_records.db"
BACKUP_PATH = DB_PATH.with_suffix('.db.premigrate')


def main():
    if not DB_PATH.exists():
        print(f"DB 없음: {DB_PATH}")
        return

    # 백업
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"백업: {BACKUP_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # person_id=1 ("나") 존재 확인
    row = conn.execute("SELECT id FROM persons WHERE id=1 AND name='나'").fetchone()
    if not row:
        print("person '나'(id=1) 없음 — 이미 마이그레이션됨")
        conn.close()
        return

    # person_id=4 ("강국진") 존재 확인
    row = conn.execute("SELECT id FROM persons WHERE id=4 AND name='강국진'").fetchone()
    if not row:
        print("person '강국진'(id=4) 없음 — 수동 확인 필요")
        conn.close()
        return

    # 1: 2023 검진(09:00) → person_id=4로 이전
    n = conn.execute("UPDATE measurements SET person_id=4 WHERE person_id=1 AND measured_at LIKE '2023-08-03 09%'").rowcount
    print(f"2023 검진(09:00) 이전: {n}건")

    # 2: 2023 중복(10:00) 삭제
    n = conn.execute("DELETE FROM measurements WHERE person_id=1 AND measured_at LIKE '2023-08-03 10%'").rowcount
    print(f"2023 검진(10:00) 중복 삭제: {n}건")

    # 3: 2026-01-09 person_id=1 중복 삭제
    n = conn.execute("DELETE FROM measurements WHERE person_id=1 AND measured_at LIKE '2026-01%'").rowcount
    print(f"2026-01-09 (person_id=1) 삭제: {n}건")

    # 4: person_id=4 내 2026-01-09 버전 중복 정리
    # id=7,8 (이전 수정 버전), id=10 (이전 기록), id=22 (중복)
    n = conn.execute("DELETE FROM measurements WHERE id IN (7, 8, 10, 22)").rowcount
    print(f"2026-01-09 버전 중복 삭제: {n}건")

    # 5: 나머지 테이블 이전
    for table in ['measurements', 'documents', 'symptoms', 'medications']:
        n = conn.execute(f"UPDATE {table} SET person_id=4 WHERE person_id=1").rowcount
        if n:
            print(f"{table} 이전: {n}건")

    # 6: person "나" 삭제
    conn.execute("DELETE FROM persons WHERE id=1")
    print("person '나' 삭제")

    conn.commit()

    # 결과 확인
    print("\n=== 마이그레이션 완료 ===")
    total = conn.execute("SELECT COUNT(*) FROM measurements WHERE person_id=4").fetchone()[0]
    print(f"강국진 measurements: {total}건")
    for p in conn.execute("SELECT id, name FROM persons ORDER BY id").fetchall():
        print(f"  person id={p['id']} name={p['name']}")

    conn.close()


if __name__ == "__main__":
    main()
