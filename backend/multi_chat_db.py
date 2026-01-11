"""
multi_chat_db.py - 다중채팅방 데이터베이스
IndieBiz OS

구조:
- rooms: 채팅방 정보
- room_participants: 채팅방 참여자 (에이전트들)
- room_messages: 채팅방 메시지 (모든 참여자 공유)
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, List, Dict
import uuid


class MultiChatDB:
    """다중채팅방 데이터베이스"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """DB 초기화 및 테이블 생성"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 채팅방 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    icon_position TEXT DEFAULT '[100, 100]',
                    in_trash INTEGER DEFAULT 0,
                    trashed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 기존 DB 마이그레이션
            cursor.execute("PRAGMA table_info(rooms)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'icon_position' not in columns:
                cursor.execute("ALTER TABLE rooms ADD COLUMN icon_position TEXT DEFAULT '[100, 100]'")
            if 'in_trash' not in columns:
                cursor.execute("ALTER TABLE rooms ADD COLUMN in_trash INTEGER DEFAULT 0")
            if 'trashed_at' not in columns:
                cursor.execute("ALTER TABLE rooms ADD COLUMN trashed_at TIMESTAMP")

            # 채팅방 참여자 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS room_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    agent_source TEXT,
                    system_prompt TEXT,
                    ai_provider TEXT,
                    ai_model TEXT,
                    ai_api_key TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (room_id) REFERENCES rooms(id),
                    UNIQUE(room_id, agent_name)
                )
            """)

            # ai_provider, ai_model, ai_api_key 컬럼이 없으면 추가 (기존 DB 마이그레이션)
            cursor.execute("PRAGMA table_info(room_participants)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'ai_provider' not in columns:
                cursor.execute("ALTER TABLE room_participants ADD COLUMN ai_provider TEXT")
            if 'ai_model' not in columns:
                cursor.execute("ALTER TABLE room_participants ADD COLUMN ai_model TEXT")
            if 'ai_api_key' not in columns:
                cursor.execute("ALTER TABLE room_participants ADD COLUMN ai_api_key TEXT")

            # 채팅방 메시지 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS room_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    content TEXT NOT NULL,
                    message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (room_id) REFERENCES rooms(id)
                )
            """)

            conn.commit()

    @contextmanager
    def get_connection(self):
        """컨텍스트 매니저로 연결 관리"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ============ Room 관리 ============

    def create_room(self, name: str, description: str = "") -> str:
        """채팅방 생성"""
        room_id = f"room_{uuid.uuid4().hex[:8]}"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO rooms (id, name, description)
                VALUES (?, ?, ?)
            """, (room_id, name, description))
            conn.commit()

        return room_id

    def get_room(self, room_id: str) -> Optional[Dict]:
        """채팅방 정보 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_rooms(self, include_trash: bool = False) -> List[Dict]:
        """모든 채팅방 목록 (휴지통 제외)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if include_trash:
                cursor.execute("SELECT * FROM rooms ORDER BY updated_at DESC")
            else:
                cursor.execute("SELECT * FROM rooms WHERE in_trash = 0 ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def delete_room(self, room_id: str) -> bool:
        """채팅방 삭제 (참여자, 메시지 포함)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM room_messages WHERE room_id = ?", (room_id,))
            cursor.execute("DELETE FROM room_participants WHERE room_id = ?", (room_id,))
            cursor.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_room_timestamp(self, room_id: str):
        """채팅방 업데이트 시간 갱신"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE rooms SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (room_id,))
            conn.commit()

    def update_room_position(self, room_id: str, x: int, y: int) -> bool:
        """채팅방 아이콘 위치 업데이트"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE rooms SET icon_position = ? WHERE id = ?
            """, (json.dumps([x, y]), room_id))
            conn.commit()
            return cursor.rowcount > 0

    # ============ 휴지통 관리 ============

    def move_to_trash(self, room_id: str) -> Optional[Dict]:
        """채팅방을 휴지통으로 이동"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE rooms SET in_trash = 1, trashed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (room_id,))
            conn.commit()
            if cursor.rowcount > 0:
                return self.get_room(room_id)
            return None

    def restore_from_trash(self, room_id: str) -> Optional[Dict]:
        """채팅방을 휴지통에서 복원"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE rooms SET in_trash = 0, trashed_at = NULL
                WHERE id = ?
            """, (room_id,))
            conn.commit()
            if cursor.rowcount > 0:
                return self.get_room(room_id)
            return None

    def list_trashed_rooms(self) -> List[Dict]:
        """휴지통에 있는 채팅방 목록"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM rooms WHERE in_trash = 1 ORDER BY trashed_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def empty_trash(self) -> int:
        """휴지통 비우기 (영구 삭제)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 휴지통에 있는 방들의 ID 조회
            cursor.execute("SELECT id FROM rooms WHERE in_trash = 1")
            trashed_ids = [row[0] for row in cursor.fetchall()]

            deleted_count = 0
            for room_id in trashed_ids:
                cursor.execute("DELETE FROM room_messages WHERE room_id = ?", (room_id,))
                cursor.execute("DELETE FROM room_participants WHERE room_id = ?", (room_id,))
                cursor.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
                deleted_count += 1

            conn.commit()
            return deleted_count

    # ============ Participant 관리 ============

    def add_participant(self, room_id: str, agent_name: str,
                       agent_source: str = "", system_prompt: str = "",
                       ai_provider: str = "", ai_model: str = "", ai_api_key: str = "") -> bool:
        """
        채팅방에 참여자 추가

        Args:
            room_id: 채팅방 ID
            agent_name: 에이전트 이름
            agent_source: 원본 위치 (예: "부동산/분석가")
            system_prompt: 에이전트 시스템 프롬프트
            ai_provider: AI 프로바이더 (anthropic, openai, google, ollama)
            ai_model: AI 모델
            ai_api_key: API 키
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO room_participants (room_id, agent_name, agent_source, system_prompt, ai_provider, ai_model, ai_api_key)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (room_id, agent_name, agent_source, system_prompt, ai_provider, ai_model, ai_api_key))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            # 이미 참여 중
            return False

    def update_participant_ai_config(self, room_id: str, agent_name: str,
                                     ai_provider: str, ai_model: str, ai_api_key: str) -> bool:
        """참여자의 AI 설정 업데이트"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE room_participants
                SET ai_provider = ?, ai_model = ?, ai_api_key = ?
                WHERE room_id = ? AND agent_name = ?
            """, (ai_provider, ai_model, ai_api_key, room_id, agent_name))
            conn.commit()
            return cursor.rowcount > 0

    def remove_participant(self, room_id: str, agent_name: str) -> bool:
        """채팅방에서 참여자 제거"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM room_participants
                WHERE room_id = ? AND agent_name = ?
            """, (room_id, agent_name))
            conn.commit()
            return cursor.rowcount > 0

    def get_participants(self, room_id: str) -> List[Dict]:
        """채팅방 참여자 목록"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM room_participants
                WHERE room_id = ?
                ORDER BY joined_at
            """, (room_id,))
            return [dict(row) for row in cursor.fetchall()]

    def update_participant_prompt(self, room_id: str, agent_name: str, system_prompt: str) -> bool:
        """참여자의 시스템 프롬프트 업데이트"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE room_participants
                SET system_prompt = ?
                WHERE room_id = ? AND agent_name = ?
            """, (system_prompt, room_id, agent_name))
            conn.commit()
            return cursor.rowcount > 0

    # ============ Message 관리 ============

    def add_message(self, room_id: str, speaker: str, content: str) -> int:
        """
        메시지 추가

        Args:
            room_id: 채팅방 ID
            speaker: 발화자 (사용자 또는 에이전트 이름)
            content: 메시지 내용

        Returns:
            생성된 메시지 ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO room_messages (room_id, speaker, content)
                VALUES (?, ?, ?)
            """, (room_id, speaker, content))
            conn.commit()

            # 채팅방 업데이트 시간 갱신
            self.update_room_timestamp(room_id)

            return cursor.lastrowid

    def get_messages(self, room_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        """채팅방 메시지 조회 (최신순)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM room_messages
                WHERE room_id = ?
                ORDER BY message_time DESC
                LIMIT ? OFFSET ?
            """, (room_id, limit, offset))

            messages = [dict(row) for row in cursor.fetchall()]
            return list(reversed(messages))  # 시간순으로 정렬

    def get_history_for_ai(self, room_id: str, limit: int = 20) -> List[Dict]:
        """
        AI용 대화 히스토리

        Returns:
            [{"role": "user/assistant", "name": "발화자", "content": "내용"}, ...]
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT speaker, content FROM room_messages
                WHERE room_id = ?
                ORDER BY message_time DESC
                LIMIT ?
            """, (room_id, limit))

            messages = []
            for row in cursor.fetchall():
                speaker = row[0]
                content = row[1]

                # 사용자는 "user", 에이전트는 "assistant"
                if speaker == "사용자":
                    role = "user"
                else:
                    role = "assistant"

                messages.append({
                    "role": role,
                    "name": speaker,
                    "content": f"[{speaker}] {content}" if role == "assistant" else content
                })

            return list(reversed(messages))

    def clear_messages(self, room_id: str) -> int:
        """채팅방 메시지 전체 삭제"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM room_messages WHERE room_id = ?", (room_id,))
            conn.commit()
            return cursor.rowcount
