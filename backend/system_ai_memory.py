"""
system_ai_memory.py - 시스템 AI 메모리 관리
IndieBiz OS Core

시스템 AI의 기억 시스템:
- 시스템 메모: system_ai_memo.txt
- 대화 이력: SQLite DB (system_ai_memory.db)
- 태스크 관리: tasks 테이블 (위임 체인 지원)
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
MEMORY_DB_PATH = DATA_PATH / "system_ai_memory.db"
SYSTEM_MEMO_PATH = DATA_PATH / "system_ai_memo.txt"


def _get_connection():
    """WAL 모드가 적용된 DB 연결 반환"""
    conn = sqlite3.connect(str(MEMORY_DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _get_exclusive_connection():
    """배타적 트랜잭션용 연결 (위임 카운터 업데이트 등 Race Condition 방지)"""
    conn = sqlite3.connect(str(MEMORY_DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    try:
        conn.execute("BEGIN EXCLUSIVE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
            importance INTEGER DEFAULT 0,
            source TEXT
        )
    """)

    # 기존 테이블 마이그레이션 (source 컬럼 추가)
    cursor.execute("PRAGMA table_info(conversations)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'source' not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN source TEXT")
        print("[system_ai_memory] conversations.source 컬럼 추가됨")

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

    # 태스크 테이블 (시스템 AI 위임 체인 지원)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            requester TEXT,
            requester_channel TEXT,
            original_request TEXT,
            delegated_to TEXT,
            delegation_context TEXT,
            parent_task_id TEXT,
            pending_delegations INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            result TEXT,
            ws_client_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def save_conversation(role: str, content: str, importance: int = 0, source: str = None) -> int:
    """대화 저장

    Args:
        role: 역할 ('user', 'assistant', 'agent')
        content: 대화 내용
        importance: 중요도 (0-10)
        source: 발신자 정보 (예: 'user@gui', '스토리텔러@홍보', 'system_ai')

    Returns:
        저장된 대화 ID
    """
    init_memory_db()

    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO conversations (timestamp, role, content, importance, source)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), role, content, importance, source))

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


# ============ 태스크 관리 (시스템 AI 위임 체인) ============

def create_task(task_id: str, requester: str, requester_channel: str,
                original_request: str, delegated_to: str = "system_ai",
                delegation_context: str = None, parent_task_id: str = None,
                ws_client_id: str = None) -> int:
    """
    새 작업 생성

    Args:
        task_id: 작업 ID (예: "task_sysai_abc123")
        requester: 원래 요청자 (예: "user@gui")
        requester_channel: 요청 채널 ("gui", "system_ai" 등)
        original_request: 원래 요청 내용
        delegated_to: 위임 대상 (기본: "system_ai")
        delegation_context: 위임 컨텍스트 JSON
        parent_task_id: 부모 task ID (계층적 위임 추적)
        ws_client_id: WebSocket 클라이언트 ID (GUI 응답용)

    Returns:
        생성된 task의 DB ID
    """
    init_memory_db()
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks (task_id, requester, requester_channel,
                           original_request, delegated_to,
                           delegation_context, parent_task_id, ws_client_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (task_id, requester, requester_channel, original_request,
          delegated_to, delegation_context, parent_task_id, ws_client_id))
    conn.commit()
    result = cursor.lastrowid
    conn.close()
    return result


def get_task(task_id: str) -> Optional[Dict]:
    """작업 정보 조회"""
    init_memory_db()
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def complete_task(task_id: str, result: str = None) -> bool:
    """작업 완료 처리 - 태스크 삭제"""
    init_memory_db()
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


# delete_task는 complete_task의 별칭
delete_task = complete_task


def update_task_delegation(task_id: str, delegation_context: str,
                           increment_pending: bool = True) -> bool:
    """
    태스크의 위임 컨텍스트 업데이트 (Race Condition 방지)

    Args:
        task_id: 작업 ID
        delegation_context: 위임 컨텍스트 JSON
        increment_pending: pending_delegations 증가 여부
    """
    init_memory_db()
    with _get_exclusive_connection() as conn:
        cursor = conn.cursor()
        if increment_pending:
            cursor.execute("""
                UPDATE tasks
                SET delegation_context = ?,
                    pending_delegations = COALESCE(pending_delegations, 0) + 1
                WHERE task_id = ?
            """, (delegation_context, task_id))
        else:
            cursor.execute("""
                UPDATE tasks
                SET delegation_context = ?
                WHERE task_id = ?
            """, (delegation_context, task_id))
        return cursor.rowcount > 0


def decrement_pending_and_update_context(task_id: str,
                                          delegation_context: str) -> int:
    """
    pending_delegations 감소 + 컨텍스트 업데이트를 원자적으로 수행

    Returns:
        감소 후 남은 pending_delegations 값
    """
    init_memory_db()
    with _get_exclusive_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tasks
            SET delegation_context = ?,
                pending_delegations = MAX(0, COALESCE(pending_delegations, 0) - 1)
            WHERE task_id = ?
        """, (delegation_context, task_id))

        cursor.execute('SELECT pending_delegations FROM tasks WHERE task_id = ?', (task_id,))
        row = cursor.fetchone()
        return row[0] if row else 0


def clear_delegation_context(task_id: str) -> bool:
    """위임 컨텍스트 완전 클리어 (태스크 완료 시 사용)"""
    init_memory_db()
    with _get_exclusive_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tasks
            SET delegation_context = NULL,
                pending_delegations = 0
            WHERE task_id = ?
        """, (task_id,))
        print(f"[시스템 AI 메모리] 위임 컨텍스트 클리어: {task_id}")
        return cursor.rowcount > 0


def get_pending_tasks(delegated_to: str = None) -> List[Dict]:
    """대기 중인 작업 목록 조회"""
    init_memory_db()
    conn = _get_connection()
    cursor = conn.cursor()
    if delegated_to:
        cursor.execute("""
            SELECT * FROM tasks
            WHERE status = 'pending' AND delegated_to = ?
            ORDER BY created_at DESC
        """, (delegated_to,))
    else:
        cursor.execute("""
            SELECT * FROM tasks WHERE status = 'pending'
            ORDER BY created_at DESC
        """)
    result = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return result


# 모듈 로드 시 DB 초기화
init_memory_db()
