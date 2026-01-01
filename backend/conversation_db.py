"""
conversation_db.py - 대화 기록 SQLite DB
IndieBiz OS Core
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Optional


class ConversationDB:
    """대화 기록 데이터베이스"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """DB 초기화 및 테이블 생성"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 에이전트 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT DEFAULT 'ai_agent',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 메시지 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_agent_id INTEGER,
                    to_agent_id INTEGER,
                    content TEXT,
                    message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tool_calls TEXT,
                    contact_type TEXT DEFAULT 'gui',
                    FOREIGN KEY (from_agent_id) REFERENCES agents(id),
                    FOREIGN KEY (to_agent_id) REFERENCES agents(id)
                )
            """)

            # 태스크 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    requester TEXT,
                    requester_channel TEXT,
                    original_request TEXT,
                    delegated_to TEXT,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    ws_client_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)

            conn.commit()

    @contextmanager
    def get_connection(self):
        """컨텍스트 매니저로 연결 관리"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_or_create_agent(self, name: str, agent_type: str = 'ai_agent') -> int:
        """에이전트 조회 또는 생성"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 조회
            cursor.execute("SELECT id FROM agents WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return row[0]

            # 생성
            cursor.execute(
                "INSERT INTO agents (name, type) VALUES (?, ?)",
                (name, agent_type)
            )
            conn.commit()
            return cursor.lastrowid

    def save_message(self, from_agent_id: int, to_agent_id: int, content: str,
                     tool_calls: str = None, contact_type: str = 'gui') -> int:
        """메시지 저장"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (from_agent_id, to_agent_id, content, tool_calls, contact_type)
                VALUES (?, ?, ?, ?, ?)
            """, (from_agent_id, to_agent_id, content, tool_calls, contact_type))
            conn.commit()
            return cursor.lastrowid

    def get_messages(self, agent_id: int, limit: int = 50, offset: int = 0) -> list:
        """에이전트의 메시지 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, from_agent_id, to_agent_id, content, message_time, tool_calls
                FROM messages
                WHERE from_agent_id = ? OR to_agent_id = ?
                ORDER BY message_time DESC
                LIMIT ? OFFSET ?
            """, (agent_id, agent_id, limit, offset))

            return [{
                "id": row[0],
                "from_agent_id": row[1],
                "to_agent_id": row[2],
                "content": row[3],
                "timestamp": row[4],
                "tool_calls": row[5]
            } for row in cursor.fetchall()]

    def get_history_for_ai(self, agent_id: int, user_id: int = 1, limit: int = 20) -> list:
        """AI용 대화 히스토리 (최신 순)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT from_agent_id, content, message_time
                FROM messages
                WHERE (from_agent_id = ? AND to_agent_id = ?)
                   OR (from_agent_id = ? AND to_agent_id = ?)
                ORDER BY message_time DESC
                LIMIT ?
            """, (agent_id, user_id, user_id, agent_id, limit))

            messages = []
            for row in cursor.fetchall():
                role = "assistant" if row[0] == agent_id else "user"
                messages.append({
                    "role": role,
                    "content": row[1]
                })

            # 오래된 순으로 반전
            return list(reversed(messages))

    def create_task(self, task_id: str, requester: str, requester_channel: str,
                    original_request: str, delegated_to: str, ws_client_id: str = None):
        """태스크 생성"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (task_id, requester, requester_channel, original_request, delegated_to, ws_client_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, requester, requester_channel, original_request, delegated_to, ws_client_id))
            conn.commit()

    def complete_task(self, task_id: str, result: str):
        """태스크 완료"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET status = 'completed', result = ?, completed_at = CURRENT_TIMESTAMP
                WHERE task_id = ?
            """, (result, task_id))
            conn.commit()
