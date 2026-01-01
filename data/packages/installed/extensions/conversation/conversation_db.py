"""
대화 히스토리 데이터베이스 관리 모듈 (새 스키마)

구조:
- agents: 주체들 (kukjin + AI 에이전트들)
- neighbors: 각 agent의 이웃들 (my_agent_id 기준)
- messages: from_agent_id → to_agent_id (단방향)
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager


# ============ 히스토리 설정 (한 곳에서 관리) ============
HISTORY_LIMIT_USER = 5       # 사용자 ↔ 에이전트 대화 히스토리
HISTORY_LIMIT_AGENT = 4      # 에이전트 ↔ 에이전트 내부 메시지 히스토리
# ========================================================


class ConversationDB:
    """대화 히스토리 데이터베이스 관리 클래스"""
    
    def __init__(self, db_path: str = None):
        # db_path가 없으면 현재 작업 디렉토리의 conversations.db 사용
        if db_path is None:
            import os
            db_path = os.path.join(os.getcwd(), 'conversations.db')
        self.db_path = db_path
        
        # 테이블이 없으면 생성
        self._init_tables()
    
    def _init_tables(self):
        """테이블 초기화 (없으면 생성)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # agents 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL DEFAULT 'ai_agent',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # neighbors 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS neighbors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    my_agent_id INTEGER NOT NULL,
                    neighbor_name TEXT NOT NULL,
                    neighbor_type TEXT DEFAULT 'external',
                    info_level INTEGER DEFAULT 0,
                    rating INTEGER DEFAULT 0,
                    additional_info TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (my_agent_id) REFERENCES agents(id),
                    UNIQUE(my_agent_id, neighbor_name)
                )
            ''')
            
            # contacts 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    neighbor_id INTEGER NOT NULL,
                    contact_type TEXT NOT NULL,
                    contact_value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (neighbor_id) REFERENCES neighbors(id)
                )
            ''')
            
            # messages 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_agent_id INTEGER NOT NULL,
                    to_agent_id INTEGER NOT NULL,
                    content TEXT,
                    message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    contact_type TEXT DEFAULT 'gui',
                    tool_calls TEXT,
                    tool_results TEXT,
                    session_id TEXT,
                    attachment_path TEXT,
                    status TEXT DEFAULT 'sent',
                    FOREIGN KEY (from_agent_id) REFERENCES agents(id),
                    FOREIGN KEY (to_agent_id) REFERENCES agents(id)
                )
            ''')
            
            # tasks 테이블 (비동기 작업 추적)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE NOT NULL,
                    requester TEXT NOT NULL,
                    requester_channel TEXT DEFAULT 'gui',
                    ws_client_id TEXT,
                    original_request TEXT,
                    delegated_to TEXT,
                    delegation_context TEXT,
                    parent_task_id TEXT,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            ''')

            # 기본 사용자 생성 (kukjin)
            cursor.execute('''
                INSERT OR IGNORE INTO agents (name, type) VALUES ('kukjin', 'human')
            ''')

            # ✅ 기존 DB 마이그레이션: delegation_context, parent_task_id 열 추가
            try:
                cursor.execute('SELECT delegation_context FROM tasks LIMIT 1')
            except sqlite3.OperationalError:
                # 열이 없으면 추가
                cursor.execute('ALTER TABLE tasks ADD COLUMN delegation_context TEXT')
                print("[DB 마이그레이션] tasks.delegation_context 열 추가됨")

            try:
                cursor.execute('SELECT parent_task_id FROM tasks LIMIT 1')
            except sqlite3.OperationalError:
                # 열이 없으면 추가
                cursor.execute('ALTER TABLE tasks ADD COLUMN parent_task_id TEXT')
                print("[DB 마이그레이션] tasks.parent_task_id 열 추가됨")

            try:
                cursor.execute('SELECT ws_client_id FROM tasks LIMIT 1')
            except sqlite3.OperationalError:
                # 열이 없으면 추가
                cursor.execute('ALTER TABLE tasks ADD COLUMN ws_client_id TEXT')
                print("[DB 마이그레이션] tasks.ws_client_id 열 추가됨")

            # ✅ 병렬 위임 지원: pending_delegations 열 추가
            try:
                cursor.execute('SELECT pending_delegations FROM tasks LIMIT 1')
            except sqlite3.OperationalError:
                cursor.execute('ALTER TABLE tasks ADD COLUMN pending_delegations INTEGER DEFAULT 0')
                print("[DB 마이그레이션] tasks.pending_delegations 열 추가됨")

            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    # ==================== Agent 관리 ====================
    
    def get_agent_by_name(self, name: str) -> Optional[Dict]:
        """이름으로 agent 찾기"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM agents WHERE name = ?', (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_agent(self, agent_id: int) -> Optional[Dict]:
        """agent 정보 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM agents WHERE id = ?', (agent_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_agents(self) -> List[Dict]:
        """모든 agents 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM agents ORDER BY type, name')
            return [dict(row) for row in cursor.fetchall()]
    
    def add_agent(self, name: str, agent_type: str = 'ai_agent') -> int:
        """새 agent 추가"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO agents (name, type) VALUES (?, ?)
            ''', (name, agent_type))
            conn.commit()
            return cursor.lastrowid
    
    # ==================== Neighbor 관리 ====================
    
    def add_neighbor(self, my_agent_id: int, neighbor_name: str, 
                     neighbor_type: str = 'external',
                     info_level: int = 0, rating: int = 0,
                     additional_info: str = '') -> int:
        """특정 agent의 이웃 추가"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO neighbors (
                    my_agent_id, neighbor_name, neighbor_type,
                    info_level, rating, additional_info
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (my_agent_id, neighbor_name, neighbor_type, 
                  info_level, rating, additional_info))
            conn.commit()
            return cursor.lastrowid
    
    def find_neighbor(self, my_agent_id: int, neighbor_name: str) -> Optional[Dict]:
        """특정 agent의 이웃 찾기"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM neighbors 
                WHERE my_agent_id = ? AND neighbor_name = ?
            ''', (my_agent_id, neighbor_name))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_my_neighbors(self, my_agent_id: int) -> List[Dict]:
        """특정 agent의 모든 이웃 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM neighbors WHERE my_agent_id = ?
                ORDER BY updated_at DESC
            ''', (my_agent_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_neighbor(self, neighbor_id: int) -> Optional[Dict]:
        """neighbor 정보 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM neighbors WHERE id = ?', (neighbor_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== Contact 관리 ====================
    
    def add_contact(self, neighbor_id: int, contact_type: str, contact_value: str) -> int:
        """이웃에게 연락처 추가"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO contacts (neighbor_id, contact_type, contact_value)
                VALUES (?, ?, ?)
            ''', (neighbor_id, contact_type, contact_value))
            conn.commit()
            return cursor.lastrowid
    
    def get_contacts(self, neighbor_id: int) -> List[Dict]:
        """특정 이웃의 모든 연락처 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM contacts WHERE neighbor_id = ?
            ''', (neighbor_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== Message 저장 (단방향) ====================
    
    def save_message(self, from_agent_id: int, to_agent_id: int, content: str,
                     contact_type: str = 'gui',
                     tool_calls: Optional[List] = None, 
                     tool_results: Optional[List] = None,
                     session_id: Optional[str] = None, 
                     attachment_path: Optional[str] = None,
                     status: str = 'sent') -> int:
        """메시지 저장 (from → to 단방향)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (
                    from_agent_id, to_agent_id, content, message_time,
                    contact_type, tool_calls, tool_results, session_id,
                    attachment_path, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                from_agent_id, to_agent_id, content, datetime.now(),
                contact_type,
                json.dumps(tool_calls) if tool_calls else None,
                json.dumps(tool_results) if tool_results else None,
                session_id, attachment_path, status
            ))
            conn.commit()
            return cursor.lastrowid
    
    # ==================== Message 조회 ====================
    
    def get_conversation_history(self, agent1_id: int, agent2_id: int,
                                 limit: int = 30, 
                                 session_id: Optional[str] = None) -> List[Dict]:
        """
        두 agent 간의 대화 히스토리 조회
        
        Args:
            agent1_id: 첫 번째 agent
            agent2_id: 두 번째 agent  
            limit: 최대 메시지 수
            session_id: 특정 세션만 조회 (선택)
        
        Returns:
            메시지 목록 (시간순 정렬)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute('''
                    SELECT * FROM messages
                    WHERE (
                        (from_agent_id = ? AND to_agent_id = ?)
                        OR (from_agent_id = ? AND to_agent_id = ?)
                    ) AND session_id = ?
                    ORDER BY message_time DESC
                    LIMIT ?
                ''', (agent1_id, agent2_id, agent2_id, agent1_id, session_id, limit))
            else:
                cursor.execute('''
                    SELECT * FROM messages
                    WHERE (from_agent_id = ? AND to_agent_id = ?)
                       OR (from_agent_id = ? AND to_agent_id = ?)
                    ORDER BY message_time DESC
                    LIMIT ?
                ''', (agent1_id, agent2_id, agent2_id, agent1_id, limit))
            
            messages = [dict(row) for row in cursor.fetchall()]
            messages.reverse()  # 시간순 정렬

            # JSON 파싱
            for msg in messages:
                if msg['tool_calls']:
                    msg['tool_calls'] = json.loads(msg['tool_calls'])
                if msg['tool_results']:
                    msg['tool_results'] = json.loads(msg['tool_results'])

            return messages

    def get_conversations_with_message_count(self, my_agent_id: int) -> List[Dict]:
        """특정 agent가 대화한 모든 상대 목록 (메시지 수 포함)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT
                    CASE 
                        WHEN m.from_agent_id = ? THEN m.to_agent_id
                        ELSE m.from_agent_id
                    END as other_agent_id,
                    a.name as other_agent_name,
                    a.type as other_agent_type,
                    COUNT(m.id) as message_count,
                    MAX(m.message_time) as last_message_time
                FROM messages m
                JOIN agents a ON (
                    (m.from_agent_id = ? AND a.id = m.to_agent_id)
                    OR (m.to_agent_id = ? AND a.id = m.from_agent_id)
                )
                WHERE m.from_agent_id = ? OR m.to_agent_id = ?
                GROUP BY other_agent_id, other_agent_name, other_agent_type
                ORDER BY last_message_time DESC
            ''', (my_agent_id, my_agent_id, my_agent_id, my_agent_id, my_agent_id))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== 유틸리티 ====================
    
    def get_or_create_neighbor(self, my_agent_id: int, neighbor_name: str,
                               neighbor_type: str = 'external',
                               contact_type: Optional[str] = None,
                               contact_value: Optional[str] = None) -> int:
        """이웃 찾기 또는 생성"""
        # 먼저 찾기
        neighbor = self.find_neighbor(my_agent_id, neighbor_name)
        if neighbor:
            return neighbor['id']
        
        # 없으면 생성
        neighbor_id = self.add_neighbor(
            my_agent_id=my_agent_id,
            neighbor_name=neighbor_name,
            neighbor_type=neighbor_type,
            additional_info='자동 생성됨'
        )
        
        # 연락처 추가
        if contact_type and contact_value:
            self.add_contact(neighbor_id, contact_type, contact_value)
        
        return neighbor_id
    
    def format_history_for_ai(self, my_agent_id: int, other_agent_id: int,
                             limit: int = None) -> List[Dict]:
        """
        AI에게 전달할 형식으로 히스토리 포맷

        개선사항:
        1. 히스토리 수 줄이기 (HISTORY_LIMIT_USER 상수 사용)
        2. 연속 assistant 메시지 합치기
        3. 과거 user 메시지에 [과거 대화] 표시 (이미 처리된 요청임을 명확히)

        Args:
            my_agent_id: 나 (AI 관점)
            other_agent_id: 대화 상대
            limit: 최대 메시지 수 (None이면 HISTORY_LIMIT_USER 사용)

        Returns:
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        if limit is None:
            limit = HISTORY_LIMIT_USER
        messages = self.get_conversation_history(my_agent_id, other_agent_id, limit)

        formatted = []
        for msg in messages:
            # 내가 보낸 메시지 = assistant, 상대가 보낸 메시지 = user
            role = "assistant" if msg['from_agent_id'] == my_agent_id else "user"
            content = msg['content']

            # 연속 assistant 메시지 합치기
            if formatted and formatted[-1]['role'] == role == 'assistant':
                # 이전 assistant 메시지에 현재 내용 추가
                formatted[-1]['content'] += "\n\n" + content
            else:
                formatted.append({
                    "role": role,
                    "content": content
                })

            # tool_calls가 있으면 추가
            if msg['tool_calls']:
                formatted[-1]['tool_calls'] = msg['tool_calls']
            if msg['tool_results']:
                formatted[-1]['tool_results'] = msg['tool_results']

        # 모든 과거 user 메시지에 [과거 대화] 표시 추가
        # (이미 응답이 완료된 요청이므로 다시 처리하면 안됨)
        for i, msg in enumerate(formatted):
            if msg['role'] == 'user':
                formatted[i]['content'] = "[과거 대화 - 이미 처리 완료됨]\n" + msg['content']

        return formatted

    # ==================== Task 관리 (비동기 작업 추적) ====================

    def create_task(self, task_id: str, requester: str, requester_channel: str,
                    original_request: str, delegated_to: str,
                    delegation_context: str = None, parent_task_id: str = None,
                    ws_client_id: str = None) -> int:
        """
        새 작업 생성

        Args:
            task_id: 작업 ID (예: "task_abc123")
            requester: 원래 요청자 (예: "user@email.com")
            requester_channel: 요청 채널 (예: "gmail", "nostr", "gui")
            original_request: 원래 요청 내용
            delegated_to: 위임 대상 에이전트
            delegation_context: 위임 컨텍스트 - 왜 이 일을 시키는지에 대한 기억 (JSON 형식)
            parent_task_id: 부모 task ID (계층적 위임 추적용)
            ws_client_id: WebSocket 클라이언트 ID (GUI 채널일 때 응답 전송용)

        Returns:
            생성된 task의 DB ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tasks (task_id, requester, requester_channel,
                                   original_request, delegated_to,
                                   delegation_context, parent_task_id, ws_client_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (task_id, requester, requester_channel, original_request,
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
        """작업 완료 처리"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tasks
                SET status = 'completed', result = ?, completed_at = CURRENT_TIMESTAMP
                WHERE task_id = ?
            ''', (result, task_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_tasks(self, delegated_to: str = None) -> List[Dict]:
        """대기 중인 작업 목록 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if delegated_to:
                cursor.execute('''
                    SELECT * FROM tasks
                    WHERE status = 'pending' AND delegated_to = ?
                    ORDER BY created_at DESC
                ''', (delegated_to,))
            else:
                cursor.execute('''
                    SELECT * FROM tasks WHERE status = 'pending'
                    ORDER BY created_at DESC
                ''')
            return [dict(row) for row in cursor.fetchall()]

    def rename_agent(self, old_name: str, new_name: str) -> bool:
        """
        에이전트 이름 변경

        agents 테이블과 neighbors 테이블의 이름을 업데이트합니다.

        Args:
            old_name: 기존 에이전트 이름
            new_name: 새 에이전트 이름

        Returns:
            bool: 변경된 레코드가 있으면 True
        """
        updated = False

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. agents 테이블 업데이트
            cursor.execute(
                'UPDATE agents SET name = ? WHERE name = ?',
                (new_name, old_name)
            )
            if cursor.rowcount > 0:
                updated = True
                print(f"  - agents 테이블: {cursor.rowcount}개 업데이트")

            # 2. neighbors 테이블의 neighbor_name 업데이트
            cursor.execute(
                'UPDATE neighbors SET neighbor_name = ? WHERE neighbor_name = ?',
                (new_name, old_name)
            )
            if cursor.rowcount > 0:
                updated = True
                print(f"  - neighbors 테이블: {cursor.rowcount}개 업데이트")

            conn.commit()

        return updated


# ==================== 사용 예시 ====================

if __name__ == "__main__":
    db = ConversationDB()
    
    # 1. kukjin(1)과 집사(2)의 대화
    print("=== 예시 1: kukjin → 집사 ===")
    db.save_message(
        from_agent_id=1,  # kukjin
        to_agent_id=2,    # 집사
        content="오늘 할 일 알려줘",
        contact_type='gui'
    )
    
    db.save_message(
        from_agent_id=2,  # 집사
        to_agent_id=1,    # kukjin
        content="오늘 회의가 3개 있습니다",
        contact_type='gui'
    )
    
    # 2. 히스토리 조회
    print("\n=== kukjin과 집사의 대화 ===")
    history = db.get_conversation_history(agent1_id=1, agent2_id=2)
    for msg in history:
        if msg['from_agent_id'] == 1:
            print(f"[kukjin] {msg['content']}")
        else:
            print(f"[집사] {msg['content']}")
    
    # 3. AI 포맷으로 변환
    print("\n=== 집사가 AI 응답 생성용으로 로드 ===")
    ai_history = db.format_history_for_ai(my_agent_id=2, other_agent_id=1)
    for msg in ai_history:
        print(f"  {msg['role']}: {msg['content']}")
    
    print("\n✅ 완료!")
