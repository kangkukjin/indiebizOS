"""
conversation_db.py - 대화 기록 및 태스크 관리 SQLite DB
IndieBiz OS Core

구조:
- agents: AI 에이전트 및 사용자
- messages: 에이전트 간 메시지
- tasks: 비동기 작업 추적 (위임 체인 지원)
- goals: 목적 기반 실행 관리 (Phase 26)
"""

import sqlite3
import json
import base64
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
                    contact_type TEXT DEFAULT 'gui',
                    FOREIGN KEY (from_agent_id) REFERENCES agents(id),
                    FOREIGN KEY (to_agent_id) REFERENCES agents(id)
                )
            """)

            # messages 테이블에 images 컬럼 추가 (마이그레이션)
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN images TEXT")
            except sqlite3.OperationalError:
                pass  # 이미 존재

            # 미사용 tool_calls 컬럼 정리 (dead column — 어떤 호출부도 값을 전달하지 않았음)
            try:
                cursor.execute("ALTER TABLE messages DROP COLUMN tool_calls")
            except sqlite3.OperationalError:
                pass  # 이미 없음

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

            # 목표 테이블 (Phase 26: Goal/Time/Condition)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    success_condition TEXT,
                    resources TEXT,
                    report_to TEXT,
                    deadline TEXT,
                    until_condition TEXT,
                    within_duration TEXT,
                    by_time TEXT,
                    every_frequency TEXT,
                    schedule_at TEXT,
                    max_rounds INTEGER NOT NULL,
                    max_cost REAL NOT NULL,
                    current_round INTEGER DEFAULT 0,
                    cumulative_cost REAL DEFAULT 0.0,
                    rounds_data TEXT,
                    strategy TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status)
            """)

            # 시도 기록 테이블 (Phase 26b: 전략 전환 + 라운드 메모리)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attempt_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    agent_id TEXT,
                    round_num INTEGER DEFAULT 1,
                    approach_category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    result TEXT DEFAULT 'failure',
                    lesson TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_attempt_task ON attempt_log(task_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_attempt_category ON attempt_log(task_id, approach_category)
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

    # messages 테이블 마이그레이션 컬럼 화이트리스트
    ALLOWED_MESSAGE_COLUMNS = {
        'delivered': 'INTEGER DEFAULT 1',
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

        # messages 테이블 마이그레이션
        cursor.execute("PRAGMA table_info(messages)")
        existing_msg_columns = {row[1] for row in cursor.fetchall()}

        for column_name, column_type in self.ALLOWED_MESSAGE_COLUMNS.items():
            if not column_name.replace('_', '').isalnum():
                continue
            if column_name not in existing_msg_columns:
                safe_query = f'ALTER TABLE messages ADD COLUMN {column_name} {column_type}'
                cursor.execute(safe_query)
                print(f"[DB 마이그레이션] messages.{column_name} 열 추가됨")

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

    def _save_images_to_files(self, message_id: int, images: list) -> str:
        """이미지를 파일로 저장하고 상대 경로 JSON 반환"""
        db_dir = Path(self.db_path).parent
        images_dir = db_dir / "images"
        images_dir.mkdir(exist_ok=True)

        paths = []
        for idx, img in enumerate(images):
            b64_data = img.get("base64", "")
            if not b64_data:
                continue
            media_type = img.get("media_type", "image/png")
            ext = "jpg" if "jpeg" in media_type else "png"
            filename = f"msg_{message_id}_{idx}.{ext}"
            filepath = images_dir / filename
            filepath.write_bytes(base64.b64decode(b64_data))
            paths.append(f"images/{filename}")

        return json.dumps(paths, ensure_ascii=False) if paths else None

    def _load_images_from_files(self, images_json: str) -> list:
        """파일에서 이미지를 base64로 로드"""
        if not images_json:
            return None
        db_dir = Path(self.db_path).parent
        paths = json.loads(images_json)
        images = []
        for rel_path in paths:
            filepath = db_dir / rel_path
            if filepath.exists():
                b64_data = base64.b64encode(filepath.read_bytes()).decode()
                ext = filepath.suffix.lower()
                media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
                images.append({"base64": b64_data, "media_type": media_type})
        return images if images else None

    def save_message(self, from_agent_id: int, to_agent_id: int, content: str,
                     images: list = None, contact_type: str = 'gui') -> int:
        """메시지 저장 (이미지 포함 가능)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (from_agent_id, to_agent_id, content, contact_type)
                VALUES (?, ?, ?, ?)
            """, (from_agent_id, to_agent_id, content, contact_type))
            conn.commit()
            message_id = cursor.lastrowid

            # 이미지가 있으면 파일로 저장 후 경로 업데이트
            if images:
                images_json = self._save_images_to_files(message_id, images)
                if images_json:
                    cursor.execute(
                        "UPDATE messages SET images = ? WHERE id = ?",
                        (images_json, message_id)
                    )
                    conn.commit()

            return message_id

    def save_message_undelivered(self, from_agent_id: int, to_agent_id: int, content: str,
                                 contact_type: str = 'gui') -> int:
        """미전달 메시지 저장 (WS 타임아웃 시 워커 스레드에서 호출)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (from_agent_id, to_agent_id, content, contact_type, delivered)
                VALUES (?, ?, ?, ?, 0)
            """, (from_agent_id, to_agent_id, content, contact_type))
            conn.commit()
            return cursor.lastrowid

    def get_undelivered_messages(self, agent_id: int, user_id: int) -> list:
        """미전달 메시지 조회 (특정 에이전트 → 사용자)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, from_agent_id, to_agent_id, content, message_time
                FROM messages
                WHERE from_agent_id = ? AND to_agent_id = ? AND delivered = 0
                ORDER BY message_time ASC
            """, (agent_id, user_id))
            return [{
                "id": row[0],
                "from_agent_id": row[1],
                "to_agent_id": row[2],
                "content": row[3],
                "timestamp": row[4]
            } for row in cursor.fetchall()]

    def mark_messages_delivered(self, message_ids: list) -> int:
        """메시지를 전달됨으로 표시"""
        if not message_ids:
            return 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(message_ids))
            cursor.execute(f"""
                UPDATE messages SET delivered = 1
                WHERE id IN ({placeholders})
            """, message_ids)
            conn.commit()
            return cursor.rowcount

    def get_messages(self, agent_id: int, limit: int = 50, offset: int = 0) -> list:
        """에이전트의 메시지 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, from_agent_id, to_agent_id, content, message_time
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
                "timestamp": row[4]
            } for row in cursor.fetchall()]

    def get_history_for_ai(self, agent_id: int, user_id: int = 1, limit: int = None) -> list:
        """AI용 대화 히스토리 (최신 순, Observation Masking 적용)

        JetBrains Research 기반: 최근 N턴은 원본 유지, 오래된 턴은 긴 내용 마스킹
        최근 턴의 이미지는 파일에서 로드하여 포함
        """
        if limit is None:
            limit = HISTORY_LIMIT_USER

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT from_agent_id, content, message_time, images
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
                images_json = row[3]

                # 최근 N턴은 원본 유지, 오래된 것은 마스킹
                if idx >= RECENT_TURNS_RAW and len(content) > MASK_THRESHOLD:
                    content = self._mask_long_content(content)

                msg = {
                    "role": role,
                    "content": content
                }

                # 최근 턴만 이미지 로드 (토큰 절약)
                if idx < RECENT_TURNS_RAW and images_json:
                    loaded_images = self._load_images_from_files(images_json)
                    if loaded_images:
                        msg["images"] = loaded_images

                messages.append(msg)

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
        """작업 완료 처리 — status 업데이트 + 도구 이력 저장 (세션 내 조회용)"""
        # 현재 스레드의 도구 호출 이력 수집
        tool_history_json = None
        try:
            from thread_context import get_tool_calls
            calls = get_tool_calls()
            if calls:
                import json
                tool_history_json = json.dumps(calls, ensure_ascii=False)
        except Exception:
            pass

        with self.get_connection() as conn:
            cursor = conn.cursor()
            # tool_history 컬럼 없으면 추가 (마이그레이션)
            try:
                cursor.execute("ALTER TABLE tasks ADD COLUMN tool_history TEXT")
            except Exception:
                pass  # 이미 존재
            # 원래 요청 내용 조회 (이벤트용)
            row = cursor.execute("SELECT original_request, delegated_to FROM tasks WHERE task_id = ?",
                                 (task_id,)).fetchone()
            original_req = dict(row).get("original_request", "")[:100] if row else ""
            delegated_to = dict(row).get("delegated_to", "") if row else ""

            cursor.execute("""
                UPDATE tasks
                SET status = 'completed', result = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    tool_history = ?
                WHERE task_id = ?
            """, (result[:500] if result else None, tool_history_json, task_id))
            conn.commit()
            updated = cursor.rowcount > 0

            # X-Ray 실시간 이벤트
            if updated:
                try:
                    from api_xray import push_xray_event
                    tools = json.loads(tool_history_json) if tool_history_json else []
                    push_xray_event("task_complete", {
                        "task_id": task_id,
                        "request": original_req,
                        "agent": delegated_to,
                        "tool_count": len(tools),
                    })
                except Exception:
                    pass

            return updated

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
                                              delegation_context: str = None,
                                              new_response: dict = None) -> int:
        """
        pending_delegations 감소 + 컨텍스트 업데이트를 원자적으로 수행

        Args:
            task_id: 작업 ID
            delegation_context: 업데이트할 위임 컨텍스트 JSON (하위 호환용)
            new_response: 새 응답 항목 dict (원자적 append용, delegation_context보다 우선)
                         예: {'child_task_id': '...', 'from_agent': '...', 'response': '...', 'completed_at': '...'}

        Returns:
            감소 후 남은 pending_delegations 값

        Note:
            EXCLUSIVE 트랜잭션으로 읽기-수정-쓰기를 원자적으로 수행.
            new_response가 주어지면 트랜잭션 내에서 read→append→write하여
            병렬 위임 시 responses[] 덮어쓰기 race condition 방지.
        """
        import json as _json

        with self.get_exclusive_connection() as conn:
            cursor = conn.cursor()

            if new_response:
                # 원자적 read-modify-write: 트랜잭션 내에서 현재 컨텍스트를 읽고 response 추가
                cursor.execute('SELECT delegation_context FROM tasks WHERE task_id = ?', (task_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    try:
                        ctx = _json.loads(row[0])
                        if 'responses' not in ctx:
                            ctx['responses'] = []
                        ctx['responses'].append(new_response)
                        delegation_context = _json.dumps(ctx, ensure_ascii=False)
                    except _json.JSONDecodeError:
                        pass  # fallback to provided delegation_context

            if delegation_context:
                cursor.execute("""
                    UPDATE tasks
                    SET delegation_context = ?,
                        pending_delegations = MAX(0, COALESCE(pending_delegations, 0) - 1)
                    WHERE task_id = ?
                """, (delegation_context, task_id))
            else:
                cursor.execute("""
                    UPDATE tasks
                    SET pending_delegations = MAX(0, COALESCE(pending_delegations, 0) - 1)
                    WHERE task_id = ?
                """, (task_id,))

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

    def clear_delegation_context(self, task_id: str) -> bool:
        """위임 컨텍스트 완전 클리어 (태스크 완료 시 사용)"""
        with self.get_exclusive_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET delegation_context = NULL,
                    pending_delegations = 0
                WHERE task_id = ?
            """, (task_id,))
            print(f"[ConversationDB] 위임 컨텍스트 클리어: {task_id}")
            return cursor.rowcount > 0

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

    # ============ Goal 관리 (Phase 26) ============

    def create_goal(self, goal_id: str, goal_data: dict) -> bool:
        """
        새 목표 생성

        Args:
            goal_id: 목표 ID (예: "goal_20260309_001")
            goal_data: 목표 데이터
                - name: 목표 이름
                - success_condition: 달성 조건
                - resources: 리소스 목록 (JSON array)
                - report_to: 보고 대상
                - deadline, until_condition, within_duration, by_time: 종료 통제
                - every_frequency, schedule_at: 빈도 통제
                - max_rounds: 최대 반복 횟수 (필수)
                - max_cost: 최대 비용 한도 USD (필수)
                - strategy: 전략 (if/case 등, JSON)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO goals (
                    goal_id, name, status, success_condition, resources,
                    report_to, deadline, until_condition, within_duration,
                    by_time, every_frequency, schedule_at,
                    max_rounds, max_cost, strategy
                ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                goal_id,
                goal_data.get('name', ''),
                goal_data.get('success_condition'),
                json.dumps(goal_data.get('resources', []), ensure_ascii=False)
                    if goal_data.get('resources') else None,
                goal_data.get('report_to'),
                goal_data.get('deadline'),
                goal_data.get('until_condition') or goal_data.get('until'),
                goal_data.get('within_duration') or goal_data.get('within'),
                goal_data.get('by_time') or goal_data.get('by'),
                goal_data.get('every_frequency') or goal_data.get('every'),
                goal_data.get('schedule_at') or goal_data.get('schedule'),
                goal_data.get('max_rounds', 100),
                goal_data.get('max_cost', 10.0),
                json.dumps(goal_data.get('strategy'), ensure_ascii=False)
                    if goal_data.get('strategy') else None
            ))
            conn.commit()
            return True

    def get_goal(self, goal_id: str) -> Optional[Dict]:
        """목표 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM goals WHERE goal_id = ?', (goal_id,))
            row = cursor.fetchone()
            if not row:
                return None
            result = dict(row)
            # JSON 필드 파싱
            if result.get('resources'):
                try:
                    result['resources'] = json.loads(result['resources'])
                except (json.JSONDecodeError, TypeError):
                    pass
            if result.get('rounds_data'):
                try:
                    result['rounds_data'] = json.loads(result['rounds_data'])
                except (json.JSONDecodeError, TypeError):
                    result['rounds_data'] = []
            if result.get('strategy'):
                try:
                    result['strategy'] = json.loads(result['strategy'])
                except (json.JSONDecodeError, TypeError):
                    pass
            return result

    def list_goals(self, status: str = None) -> List[Dict]:
        """
        목표 목록 조회

        Args:
            status: 상태 필터 ('pending', 'active', 'achieved', 'expired',
                    'limit_reached', 'cancelled'). None이면 전체 조회.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT goal_id, name, status, success_condition,
                           current_round, max_rounds, cumulative_cost, max_cost,
                           deadline, until_condition, every_frequency,
                           created_at, started_at, completed_at
                    FROM goals WHERE status = ?
                    ORDER BY created_at DESC
                """, (status,))
            else:
                cursor.execute("""
                    SELECT goal_id, name, status, success_condition,
                           current_round, max_rounds, cumulative_cost, max_cost,
                           deadline, until_condition, every_frequency,
                           created_at, started_at, completed_at
                    FROM goals
                    ORDER BY created_at DESC
                """)
            return [dict(row) for row in cursor.fetchall()]

    def update_goal_status(self, goal_id: str, status: str) -> bool:
        """
        목표 상태 업데이트

        Args:
            goal_id: 목표 ID
            status: 새 상태 ('pending', 'active', 'achieved', 'expired',
                    'limit_reached', 'cancelled')
        """
        valid_statuses = {'pending', 'active', 'achieved', 'expired',
                          'limit_reached', 'cancelled'}
        if status not in valid_statuses:
            return False

        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status == 'active':
                cursor.execute("""
                    UPDATE goals SET status = ?, started_at = ?
                    WHERE goal_id = ?
                """, (status, now, goal_id))
            elif status in ('achieved', 'expired', 'limit_reached', 'cancelled'):
                cursor.execute("""
                    UPDATE goals SET status = ?, completed_at = ?
                    WHERE goal_id = ?
                """, (status, now, goal_id))
            else:
                cursor.execute("""
                    UPDATE goals SET status = ? WHERE goal_id = ?
                """, (status, goal_id))
            conn.commit()
            return cursor.rowcount > 0

    def add_goal_round(self, goal_id: str, round_num: int,
                       cost: float, result: str) -> bool:
        """
        목표 라운드 실행 기록 추가

        Args:
            goal_id: 목표 ID
            round_num: 라운드 번호
            cost: 이번 라운드 비용 (USD)
            result: 라운드 실행 결과 요약
        """
        with self.get_exclusive_connection() as conn:
            cursor = conn.cursor()

            # 현재 rounds_data 읽기
            cursor.execute(
                'SELECT rounds_data FROM goals WHERE goal_id = ?', (goal_id,))
            row = cursor.fetchone()
            if not row:
                return False

            rounds = []
            if row[0]:
                try:
                    rounds = json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    rounds = []

            # 새 라운드 추가
            rounds.append({
                'round': round_num,
                'cost': cost,
                'result': result,
                'timestamp': datetime.now().isoformat()
            })

            # DB 업데이트 (라운드 데이터 + 라운드 카운터 + 비용 합산)
            cursor.execute("""
                UPDATE goals
                SET rounds_data = ?,
                    current_round = ?,
                    cumulative_cost = cumulative_cost + ?
                WHERE goal_id = ?
            """, (json.dumps(rounds, ensure_ascii=False),
                  round_num, cost, goal_id))

            return cursor.rowcount > 0

    def increment_goal_cost(self, goal_id: str, cost_delta: float) -> bool:
        """목표 누적 비용 증가 (판단 루프 비용 등 별도 합산용)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE goals
                SET cumulative_cost = cumulative_cost + ?
                WHERE goal_id = ?
            """, (cost_delta, goal_id))
            conn.commit()
            return cursor.rowcount > 0

    # ============ Attempt Log (Phase 26b: 전략 전환 + 라운드 메모리) ============

    def log_attempt(self, task_id: str, agent_id: str,
                    approach_category: str, description: str,
                    result: str = "failure", lesson: str = None) -> int:
        """
        시도 기록 추가

        Args:
            task_id: 태스크/대화 ID (같은 작업의 시도를 묶는 키)
            agent_id: 실행 에이전트
            approach_category: 접근 범주 (예: "cv2_import", "code_modification", "library_install")
            description: 구체적으로 무엇을 시도했는지
            result: "success" 또는 "failure"
            lesson: 이 시도에서 배운 점

        Returns:
            자동 부여된 round_num
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 해당 task의 현재 최대 round_num 조회
            cursor.execute("""
                SELECT COALESCE(MAX(round_num), 0) FROM attempt_log
                WHERE task_id = ?
            """, (task_id,))
            max_round = cursor.fetchone()[0]
            round_num = max_round + 1

            cursor.execute("""
                INSERT INTO attempt_log
                (task_id, agent_id, round_num, approach_category, description, result, lesson)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (task_id, agent_id, round_num, approach_category,
                  description, result, lesson))
            conn.commit()
            return round_num

    def get_attempt_history(self, task_id: str, limit: int = 20) -> List[Dict]:
        """
        시도 이력 조회 (최신순)

        Args:
            task_id: 태스크 ID
            limit: 최대 조회 수

        Returns:
            시도 기록 리스트
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT round_num, approach_category, description, result, lesson, created_at
                FROM attempt_log
                WHERE task_id = ?
                ORDER BY round_num DESC
                LIMIT ?
            """, (task_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_consecutive_failures(self, task_id: str, category: str) -> int:
        """
        특정 범주의 연속 실패 횟수 계산

        가장 최근의 성공 이후 해당 category의 연속 실패 수를 반환.
        한 번도 성공한 적 없으면 해당 category의 전체 실패 수.

        Args:
            task_id: 태스크 ID
            category: 접근 범주

        Returns:
            연속 실패 횟수
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 해당 카테고리의 마지막 성공 round_num
            cursor.execute("""
                SELECT MAX(round_num) FROM attempt_log
                WHERE task_id = ? AND approach_category = ? AND result = 'success'
            """, (task_id, category))
            row = cursor.fetchone()
            last_success = row[0] if row and row[0] else 0

            # 그 이후의 실패 수
            cursor.execute("""
                SELECT COUNT(*) FROM attempt_log
                WHERE task_id = ? AND approach_category = ?
                  AND result = 'failure' AND round_num > ?
            """, (task_id, category, last_success))
            return cursor.fetchone()[0]

    def get_failed_categories(self, task_id: str, threshold: int = 3) -> List[str]:
        """
        연속 실패 임계값을 넘은 접근 범주 목록

        Args:
            task_id: 태스크 ID
            threshold: 연속 실패 임계값 (기본 3)

        Returns:
            포기해야 할 접근 범주 리스트
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 모든 고유 카테고리 조회
            cursor.execute("""
                SELECT DISTINCT approach_category FROM attempt_log
                WHERE task_id = ?
            """, (task_id,))
            categories = [row[0] for row in cursor.fetchall()]

        failed = []
        for cat in categories:
            if self.get_consecutive_failures(task_id, cat) >= threshold:
                failed.append(cat)
        return failed

