"""
memory_db.py - 에이전트별 메모리 SQLite 저장소
에이전트가 스스로 저장하고 필요할 때 검색해서 읽는 심층 메모리
"""
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict


def _get_db_path(project_path: str, agent_id: str) -> str:
    """에이전트별 메모리 DB 경로

    프로젝트 에이전트: projects/{project_id}/memory_{agent_name}.db
    시스템 AI: data/system_ai_state/memory_system_ai.db
    """
    from pathlib import Path

    project_dir = Path(project_path).resolve()

    # 시스템 AI인지 확인
    if str(project_dir).endswith("data") or project_dir == Path(".").resolve():
        from runtime_utils import get_base_path
        db_dir = get_base_path() / "data" / "system_ai_state"
        db_dir.mkdir(parents=True, exist_ok=True)
        return str(db_dir / "memory_system_ai.db")
    else:
        agent_name = agent_id.replace("agent_", "") if agent_id and agent_id.startswith("agent_") else agent_id
        return str(project_dir / f"memory_{agent_name}.db")


def get_db(project_path: str, agent_id: str):
    """DB 연결 및 테이블 초기화"""
    db_path = _get_db_path(project_path, agent_id)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            used_at DATETIME DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mem_keywords ON memories(keywords);
        CREATE INDEX IF NOT EXISTS idx_mem_category ON memories(category);
    ''')

    # 기존 DB에 used_at 컬럼이 없으면 추가
    try:
        conn.execute("SELECT used_at FROM memories LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE memories ADD COLUMN used_at DATETIME DEFAULT NULL")

    return conn


def save(project_path: str, agent_id: str,
         content: str, keywords: str = "", category: str = "") -> int:
    """메모리 저장"""
    conn = get_db(project_path, agent_id)
    try:
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO memories (category, keywords, content, created_at) VALUES (?, ?, ?, ?)",
            (category, keywords, content, now)
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def search(project_path: str, agent_id: str,
           query: str, category: str = None, limit: int = 10) -> List[Dict]:
    """키워드 기반 메모리 검색"""
    conn = get_db(project_path, agent_id)
    try:
        words = query.strip().split()
        if not words:
            return []

        conditions = []
        params = []
        for word in words:
            w = f"%{word}%"
            conditions.append("(keywords LIKE ? OR content LIKE ?)")
            params.extend([w, w])

        where = " OR ".join(conditions)

        if category:
            where = f"({where}) AND category = ?"
            params.append(category)

        first = f"%{words[0]}%"
        sql = f"""
            SELECT id, category, keywords,
                   SUBSTR(content, 1, 100) as preview,
                   created_at, used_at
            FROM memories
            WHERE {where}
            ORDER BY
                CASE WHEN keywords LIKE ? THEN 1 ELSE 2 END,
                created_at DESC
            LIMIT ?
        """
        params.extend([first, limit])

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def read(project_path: str, agent_id: str, memory_id: int) -> Optional[Dict]:
    """메모리 전문 조회 + used_at 갱신"""
    conn = get_db(project_path, agent_id)
    try:
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if not row:
            return None

        # 읽을 때마다 used_at 갱신
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE memories SET used_at = ? WHERE id = ?", (now, memory_id)
        )
        conn.commit()

        result = dict(row)
        result['used_at'] = now
        return result
    finally:
        conn.close()


def delete(project_path: str, agent_id: str, memory_id: int) -> bool:
    """메모리 삭제"""
    conn = get_db(project_path, agent_id)
    try:
        cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def count(project_path: str, agent_id: str) -> int:
    """메모리 총 개수"""
    conn = get_db(project_path, agent_id)
    try:
        return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        conn.close()
