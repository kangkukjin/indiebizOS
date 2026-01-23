"""
conversation_db.py - 대화 기록 및 태스크 관리 SQLite DB
IndieBiz OS Core

구조:
- agents: AI 에이전트 및 사용자
- messages: 에이전트 간 메시지
- tasks: 비동기 작업 추적 (위임 체인 지원)
"""

import sqlite3
import json
import threading
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, List, Dict


# ============ 히스토리 설정 ============
HISTORY_LIMIT_USER = 5       # 사용자 ↔ 에이전트 대화 히스토리
HISTORY_LIMIT_AGENT = 4      # 에이전트 ↔ 에이전트 내부 메시지 히스토리
RECENT_TURNS_RAW = 2         # 최근 N턴은 원본 유지 (마스킹 안 함)
MASK_THRESHOLD = 500         # 이 길이 이상이면 마스킹

# ============ 연결 풀 설정 ============
_connection_pools: Dict[str, List[sqlite3.Connection]] = {}  # db_path -> [connections]
_pool_lock = threading.Lock()
_MAX_POOL_SIZE = 5  # DB당 최대 연결 수


class ConversationDB:
    """대화 기록 및 태스크 데이터베이스"""

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

            # 태스크 테이블 (위임 체인 지원)
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

            # 기존 DB 마이그레이션
            self._migrate_tables(cursor)

            conn.commit()

    # 허용된 컬럼 이름 화이트리스트 (SQL 인젝션 방지)
    ALLOWED_COLUMNS = {
        'delegation_context': 'TEXT',
        'parent_task_id': 'TEXT',
        'pending_delegations': 'INTEGER DEFAULT 0',
        'ws_client_id': 'TEXT'
    }

    def _migrate_tables(self, cursor):
        """기존 DB 마이그레이션 (SQL 인젝션 방지를 위한 화이트리스트 사용)"""
        # tasks 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            # tasks 테이블이 없으면 생성
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
            print("[DB 마이그레이션] tasks 테이블 생성됨")
            return  # 새로 생성했으므로 컬럼 추가 불필요

        # 현재 테이블의 컬럼 정보 조회 (안전한 방식)
        cursor.execute("PRAGMA table_info(tasks)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        # 화이트리스트에 있는 컬럼만 추가
        for column_name, column_type in self.ALLOWED_COLUMNS.items():
            # 컬럼 이름 검증: 알파벳, 숫자, 언더스코어만 허용
            if not column_name.replace('_', '').isalnum():
                print(f"[DB 마이그레이션] 잘못된 컬럼명 무시: {column_name}")
                continue

            if column_name not in existing_columns:
                # 안전한 방식: 화이트리스트에서 가져온 값만 사용
                # SQLite는 컬럼명에 파라미터 바인딩을 지원하지 않으므로
                # 화이트리스트 검증 후 문자열 포매팅 사용
                safe_query = f'ALTER TABLE tasks ADD COLUMN {column_name} {column_type}'
                cursor.execute(safe_query)
                print(f"[DB 마이그레이션] tasks.{column_name} 열 추가됨")

    def _get_pooled_connection(self) -> sqlite3.Connection:
        """연결 풀에서 연결 가져오기"""
        with _pool_lock:
            pool = _connection_pools.get(self.db_path, [])
            if pool:
                conn = pool.pop()
                # 연결 유효성 확인
                try:
                    conn.execute("SELECT 1")
                    return conn
                except sqlite3.Error:
                    # 연결이 끊어졌으면 새로 생성
                    pass

        # 새 연결 생성
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _return_to_pool(self, conn: sqlite3.Connection):
        """연결을 풀에 반환"""
        with _pool_lock:
            pool = _connection_pools.setdefault(self.db_path, [])
            if len(pool) < _MAX_POOL_SIZE:
                pool.append(conn)
            else:
                conn.close()  # 풀이 가득 차면 연결 닫기

    @contextmanager
    def get_connection(self):
        """컨텍스트 매니저로 연결 관리 (연결 풀 사용)"""
        conn = self._get_pooled_connection()
        try:
            yield conn
        finally:
            self._return_to_pool(conn)

    @contextmanager
    def get_exclusive_connection(self):
        """배타적 트랜잭션용 연결 (위임 카운터 업데이트 등 Race Condition 방지)

        EXCLUSIVE 모드는 다른 연결의 읽기/쓰기를 모두 차단하여
        pending_delegations 같은 카운터의 원자적 업데이트를 보장합니다.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None  # autocommit 비활성화
        try:
            conn.execute("BEGIN EXCLUSIVE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ============ Agent 관리 ============

    def get_or_create_agent(self, name: str, agent_type: str = 'ai_agent') -> int:
        """에이전트 조회 또는 생성"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM agents WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return row[0]

            cursor.execute(
                "INSERT INTO agents (name, type) VALUES (?, ?)",
                (name, agent_type)
            )
            conn.commit()
            return cursor.lastrowid

    def get_agent_by_name(self, name: str) -> Optional[Dict]:
        """이름으로 에이전트 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agents WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # ============ Message 관리 ============

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

    def get_history_for_ai(self, agent_id: int, user_id: int = 1, limit: int = None) -> list:
        """AI용 대화 히스토리 (최신 순, Observation Masking 적용)

        JetBrains Research 기반: 최근 N턴은 원본 유지, 오래된 턴은 긴 내용 마스킹
        """
        if limit is None:
            limit = HISTORY_LIMIT_USER

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
            rows = cursor.fetchall()

            for idx, row in enumerate(rows):
                role = "assistant" if row[0] == agent_id else "user"
                content = row[1]

                # 최근 N턴은 원본 유지, 오래된 것은 마스킹
                if idx >= RECENT_TURNS_RAW and len(content) > MASK_THRESHOLD:
                    content = self._mask_long_content(content)

                messages.append({
                    "role": role,
                    "content": content
                })

            return list(reversed(messages))

    def _mask_long_content(self, content: str) -> str:
        """긴 콘텐츠를 플레이스홀더로 마스킹 (도구 결과 등)"""
        lines = content.split('\n')
        first_line = lines[0][:100] if lines else ""
        return f"[이전 응답: {first_line}... ({len(content)}자)]"

    # ============ Task 관리 (위임 체인 지원) ============

    def create_task(self, task_id: str, requester: str, requester_channel: str,
                    original_request: str, delegated_to: str,
                    delegation_context: str = None, parent_task_id: str = None,
                    ws_client_id: str = None) -> int:
        """
        새 작업 생성

        Args:
            task_id: 작업 ID (예: "task_abc123")
            requester: 원래 요청자 (예: "user@gui", "내과@internal")
            requester_channel: 요청 채널 ("gui", "internal", "email" 등)
            original_request: 원래 요청 내용
            delegated_to: 위임 대상 에이전트 이름
            delegation_context: 위임 컨텍스트 JSON (왜 이 일을 시키는지)
            parent_task_id: 부모 task ID (계층적 위임 추적)
            ws_client_id: WebSocket 클라이언트 ID (GUI 응답용)

        Returns:
            생성된 task의 DB ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (task_id, requester, requester_channel,
                                   original_request, delegated_to,
                                   delegation_context, parent_task_id, ws_client_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (task_id, requester, requester_channel, original_request,
                  delegated_to, delegation_context, parent_task_id, ws_client_id))
            conn.commit()
            return cursor.lastrowid

    def get_task(self, task_id: str) -> Optional[Dict]:
        """작업 정보 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def complete_task(self, task_id: str, result: str) -> bool:
        """작업 완료 처리 - 태스크 삭제"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 태스크 삭제 (위임 추적은 임시 상태이므로 완료 후 삭제)
            cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_task_delegation(self, task_id: str, delegation_context: str,
                               increment_pending: bool = True) -> bool:
        """
        태스크의 위임 컨텍스트 업데이트 (Race Condition 방지)

        Args:
            task_id: 작업 ID
            delegation_context: 위임 컨텍스트 JSON
            increment_pending: pending_delegations 증가 여부

        Note:
            EXCLUSIVE 트랜잭션을 사용하여 병렬 위임 시 카운터 손상 방지
        """
        with self.get_exclusive_connection() as conn:
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
            # commit은 get_exclusive_connection에서 자동 처리
            return cursor.rowcount > 0

    def decrement_pending_and_update_context(self, task_id: str,
                                              delegation_context: str) -> int:
        """
        pending_delegations 감소 + 컨텍스트 업데이트를 원자적으로 수행

        Args:
            task_id: 작업 ID
            delegation_context: 업데이트할 위임 컨텍스트 JSON

        Returns:
            감소 후 남은 pending_delegations 값

        Note:
            EXCLUSIVE 트랜잭션으로 읽기-수정-쓰기를 원자적으로 수행
        """
        with self.get_exclusive_connection() as conn:
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

    def decrement_pending_delegations(self, task_id: str) -> int:
        """
        pending_delegations 감소 및 현재 값 반환 (Race Condition 방지)

        Returns:
            감소 후 남은 pending_delegations 값
        """
        with self.get_exclusive_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET pending_delegations = MAX(0, COALESCE(pending_delegations, 0) - 1)
                WHERE task_id = ?
            """, (task_id,))

            cursor.execute('SELECT pending_delegations FROM tasks WHERE task_id = ?', (task_id,))
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_pending_tasks(self, delegated_to: str = None) -> List[Dict]:
        """대기 중인 작업 목록 조회"""
        with self.get_connection() as conn:
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
            return [dict(row) for row in cursor.fetchall()]

    def get_child_tasks(self, parent_task_id: str) -> List[Dict]:
        """자식 태스크 목록 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks
                WHERE parent_task_id = ?
                ORDER BY created_at ASC
            """, (parent_task_id,))
            return [dict(row) for row in cursor.fetchall()]

