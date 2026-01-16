"""
system_ai_memory.py - 시스템 AI 메모리 관리
IndieBiz OS Core

시스템 AI의 기억 시스템:
- 시스템 메모: system_ai_memo.txt
- 대화 이력: SQLite DB (system_ai_memory.db)
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
MEMORY_DB_PATH = DATA_PATH / "system_ai_memory.db"
SYSTEM_MEMO_PATH = DATA_PATH / "system_ai_memo.txt"


def _get_connection():
    """WAL 모드가 적용된 DB 연결 반환"""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_memory_db():
    """메모리 DB 초기화"""
    DATA_PATH.mkdir(parents=True, exist_ok=True)

    conn = _get_connection()
    cursor = conn.cursor()

    # 대화 이력 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            importance INTEGER DEFAULT 0
        )
    """)

    # 중요 기억 테이블 (시스템 AI가 기억해야 할 것들)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_conversation(role: str, content: str, importance: int = 0) -> int:
    """대화 저장"""
    init_memory_db()

    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO conversations (timestamp, role, content, importance)
        VALUES (?, ?, ?, ?)
    """, (datetime.now().isoformat(), role, content, importance))

    conversation_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return conversation_id


def get_recent_conversations(limit: int = 10) -> List[Dict[str, Any]]:
    """최근 대화 조회"""
    init_memory_db()

    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, timestamp, role, content, summary, importance
        FROM conversations
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    conversations = []
    for row in reversed(rows):  # 시간순으로 정렬
        conversations.append({
            "id": row[0],
            "timestamp": row[1],
            "role": row[2],
            "content": row[3],
            "summary": row[4],
            "importance": row[5]
        })

    return conversations


def get_important_conversations(min_importance: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
    """중요 대화 조회"""
    init_memory_db()

    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, timestamp, role, content, summary, importance
        FROM conversations
        WHERE importance >= ?
        ORDER BY importance DESC, id DESC
        LIMIT ?
    """, (min_importance, limit))

    rows = cursor.fetchall()
    conn.close()

    return [{
        "id": row[0],
        "timestamp": row[1],
        "role": row[2],
        "content": row[3],
        "summary": row[4],
        "importance": row[5]
    } for row in rows]


def save_memory(category: str, title: str, content: str, source: str = None) -> int:
    """기억 저장"""
    init_memory_db()

    conn = _get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO memories (created_at, updated_at, category, title, content, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now, now, category, title, content, source))

    memory_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return memory_id


def get_memories(category: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """기억 조회"""
    init_memory_db()

    conn = _get_connection()
    cursor = conn.cursor()

    if category:
        cursor.execute("""
            SELECT id, created_at, updated_at, category, title, content, source
            FROM memories
            WHERE category = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """, (category, limit))
    else:
        cursor.execute("""
            SELECT id, created_at, updated_at, category, title, content, source
            FROM memories
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [{
        "id": row[0],
        "created_at": row[1],
        "updated_at": row[2],
        "category": row[3],
        "title": row[4],
        "content": row[5],
        "source": row[6]
    } for row in rows]


def load_system_memo() -> str:
    """시스템 메모 로드"""
    if SYSTEM_MEMO_PATH.exists():
        return SYSTEM_MEMO_PATH.read_text(encoding='utf-8').strip()
    return ""


# 하위 호환성을 위한 별칭
load_user_profile = load_system_memo


def get_memory_context(include_conversations: int = 5) -> str:
    """시스템 AI를 위한 메모리 컨텍스트 생성"""
    context_parts = []

    # 최근 대화 이력
    if include_conversations > 0:
        recent = get_recent_conversations(include_conversations)
        if recent:
            context_parts.append("# 최근 대화 이력")
            for conv in recent:
                role_name = "사용자" if conv["role"] == "user" else "시스템 AI"
                # 긴 내용은 요약
                content = conv["content"]
                if len(content) > 200:
                    content = content[:200] + "..."
                context_parts.append(f"- {role_name}: {content}")

    return "\n".join(context_parts) if context_parts else ""


# 모듈 로드 시 DB 초기화
init_memory_db()
