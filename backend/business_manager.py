"""
business_manager.py - 비즈니스 관리 매니저
SQLite DB를 사용하여 비즈니스, 아이템, 문서, 지침 관리
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# DB 경로
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH / "data"
DATA_PATH.mkdir(exist_ok=True)
DB_PATH = DATA_PATH / "business.db"


class BusinessManager:
    """비즈니스 관리 매니저"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """DB 연결 생성 (WAL 모드)"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """DB 스키마 초기화"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 비즈니스 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                level INTEGER DEFAULT 0,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 비즈니스 아이템 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS business_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                details TEXT,
                attachment_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
            )
        """)

        # 비즈니스 문서 테이블 (레벨별 문서)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS business_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level INTEGER UNIQUE NOT NULL,
                title TEXT DEFAULT '',
                content TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 근무 지침 테이블 (레벨별 지침)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_guidelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level INTEGER UNIQUE NOT NULL,
                title TEXT DEFAULT '',
                content TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 이웃 테이블 (비즈니스 파트너)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS neighbors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                info_level INTEGER DEFAULT 0,
                rating INTEGER DEFAULT 0,
                additional_info TEXT,
                business_doc TEXT,
                info_share INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 마이그레이션: neighbors 테이블에 info_share 컬럼 추가 (기존 DB 호환)
        try:
            cursor.execute("ALTER TABLE neighbors ADD COLUMN info_share INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 이미 존재하면 무시

        # 연락처 테이블 (이웃당 여러 연락처)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                neighbor_id INTEGER NOT NULL,
                contact_type TEXT NOT NULL,
                contact_value TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (neighbor_id) REFERENCES neighbors(id) ON DELETE CASCADE
            )
        """)

        # 메시지 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                neighbor_id INTEGER,
                subject TEXT,
                content TEXT,
                message_time TEXT,
                is_from_user INTEGER DEFAULT 0,
                contact_type TEXT,
                contact_value TEXT,
                attachment_path TEXT,
                status TEXT DEFAULT 'received',
                error_message TEXT,
                sent_at TEXT,
                processed INTEGER DEFAULT 0,
                replied INTEGER DEFAULT 0,
                external_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (neighbor_id) REFERENCES neighbors(id) ON DELETE SET NULL
            )
        """)

        # 통신채널 설정 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_type TEXT UNIQUE NOT NULL,
                enabled INTEGER DEFAULT 0,
                config TEXT,
                polling_interval INTEGER DEFAULT 60,
                last_poll_at TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 마이그레이션: messages 테이블에 external_id 컬럼 추가 (기존 DB 호환)
        # 인덱스 생성 전에 실행해야 함
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN external_id TEXT")
        except sqlite3.OperationalError:
            pass  # 이미 존재하면 무시

        # 인덱스 생성
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_neighbor_id ON contacts(neighbor_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_type_value ON contacts(contact_type, contact_value)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_neighbor_id ON messages(neighbor_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_processed ON messages(processed)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_replied ON messages(replied)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_external_id ON messages(external_id)")

        # 기본 문서/지침 레코드 생성 (레벨 0-4)
        for level in range(5):
            cursor.execute("""
                INSERT OR IGNORE INTO business_documents (level, title, content)
                VALUES (?, ?, ?)
            """, (level, f"레벨 {level} 비즈니스 문서", ""))

            cursor.execute("""
                INSERT OR IGNORE INTO work_guidelines (level, title, content)
                VALUES (?, ?, ?)
            """, (level, f"레벨 {level} 근무 지침", ""))

        # 기본 통신채널 설정
        default_channels = [
            ("gmail", 0, "{}", 60),
            ("nostr", 0, "{}", 30),
        ]
        for channel_type, enabled, config, interval in default_channels:
            cursor.execute("""
                INSERT OR IGNORE INTO channel_settings (channel_type, enabled, config, polling_interval)
                VALUES (?, ?, ?, ?)
            """, (channel_type, enabled, config, interval))

        # 기본 비즈니스 카테고리 생성 (첫 실행 시)
        cursor.execute("SELECT COUNT(*) FROM businesses")
        if cursor.fetchone()[0] == 0:
            default_businesses = [
                ("나눕니다", 0, "나눔/기부 관련 비즈니스"),
                ("구합니다", 0, "구인/구직 관련 비즈니스"),
                ("놉시다", 0, "함께 하기 관련 비즈니스"),
                ("빌려줍니다", 0, "대여/렌탈 관련 비즈니스"),
                ("소개합니다", 0, "소개/추천 관련 비즈니스"),
                ("팔아요", 0, "판매 관련 비즈니스"),
                ("할수있습니다", 0, "서비스 제공 관련 비즈니스"),
            ]
            cursor.executemany("""
                INSERT INTO businesses (name, level, description) VALUES (?, ?, ?)
            """, default_businesses)

        conn.commit()
        conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Row 객체를 딕셔너리로 변환"""
        return dict(row) if row else None

    # ============ 비즈니스 CRUD ============

    def get_businesses(self, level: Optional[int] = None, search: Optional[str] = None) -> List[Dict]:
        """비즈니스 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM businesses WHERE 1=1"
        params = []

        if level is not None:
            query += " AND level = ?"
            params.append(level)

        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")

        query += " ORDER BY name"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_business(self, business_id: int) -> Optional[Dict]:
        """비즈니스 상세 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM businesses WHERE id = ?", (business_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def create_business(self, name: str, level: int = 0, description: Optional[str] = None) -> Dict:
        """비즈니스 생성"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO businesses (name, level, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, level, description, now, now))

        business_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return self.get_business(business_id)

    def update_business(self, business_id: int, name: Optional[str] = None,
                        level: Optional[int] = None, description: Optional[str] = None) -> Dict:
        """비즈니스 수정"""
        conn = self._get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if level is not None:
            updates.append("level = ?")
            params.append(level)
        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(business_id)

            cursor.execute(f"""
                UPDATE businesses SET {', '.join(updates)} WHERE id = ?
            """, params)
            conn.commit()

        conn.close()
        return self.get_business(business_id)

    def delete_business(self, business_id: int):
        """비즈니스 삭제 (관련 아이템도 함께 삭제)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM businesses WHERE id = ?", (business_id,))
        conn.commit()
        conn.close()

    # ============ 비즈니스 아이템 CRUD ============

    def get_business_items(self, business_id: int) -> List[Dict]:
        """비즈니스 아이템 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM business_items WHERE business_id = ? ORDER BY created_at DESC
        """, (business_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def get_business_item(self, item_id: int) -> Optional[Dict]:
        """비즈니스 아이템 상세 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM business_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def create_business_item(self, business_id: int, title: str,
                             details: Optional[str] = None,
                             attachment_path: Optional[str] = None) -> Dict:
        """비즈니스 아이템 생성"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO business_items (business_id, title, details, attachment_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (business_id, title, details, attachment_path, now, now))

        item_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return self.get_business_item(item_id)

    def update_business_item(self, item_id: int, title: Optional[str] = None,
                             details: Optional[str] = None,
                             attachment_path: Optional[str] = None) -> Dict:
        """비즈니스 아이템 수정"""
        conn = self._get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if details is not None:
            updates.append("details = ?")
            params.append(details)
        if attachment_path is not None:
            updates.append("attachment_path = ?")
            params.append(attachment_path)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(item_id)

            cursor.execute(f"""
                UPDATE business_items SET {', '.join(updates)} WHERE id = ?
            """, params)
            conn.commit()

        conn.close()
        return self.get_business_item(item_id)

    def delete_business_item(self, item_id: int):
        """비즈니스 아이템 삭제"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM business_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()

    # ============ 비즈니스 문서 ============

    def get_all_business_documents(self) -> List[Dict]:
        """모든 비즈니스 문서 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM business_documents ORDER BY level")
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def get_business_document(self, level: int) -> Optional[Dict]:
        """특정 레벨의 비즈니스 문서 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM business_documents WHERE level = ?", (level,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def update_business_document(self, level: int, title: str, content: str) -> Dict:
        """비즈니스 문서 수정"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE business_documents SET title = ?, content = ?, updated_at = ?
            WHERE level = ?
        """, (title, content, now, level))

        conn.commit()
        conn.close()
        return self.get_business_document(level)

    # ============ 근무 지침 ============

    def get_all_work_guidelines(self) -> List[Dict]:
        """모든 근무 지침 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_guidelines ORDER BY level")
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def get_work_guideline(self, level: int) -> Optional[Dict]:
        """특정 레벨의 근무 지침 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_guidelines WHERE level = ?", (level,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def update_work_guideline(self, level: int, title: str, content: str) -> Dict:
        """근무 지침 수정"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE work_guidelines SET title = ?, content = ?, updated_at = ?
            WHERE level = ?
        """, (title, content, now, level))

        conn.commit()
        conn.close()
        return self.get_work_guideline(level)

    # ============ 문서 자동 생성 ============

    def regenerate_business_documents(self) -> Dict:
        """
        비즈니스 목록과 아이템을 기반으로 '나의 열린 비즈니스 문서'를 레벨별로 자동 생성
        - 레벨 0 문서: 레벨 0 비즈니스만 포함
        - 레벨 1 문서: 레벨 0~1 비즈니스 포함
        - 레벨 N 문서: 레벨 0~N 비즈니스 포함 (정보 공개 수준)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()

            for doc_level in range(5):  # 레벨 0~4
                # 해당 레벨 이하의 모든 비즈니스 조회
                cursor.execute("""
                    SELECT b.id, b.name, b.level, b.description
                    FROM businesses b
                    WHERE b.level >= 0 AND b.level <= ?
                    ORDER BY b.level ASC, b.name ASC
                """, (doc_level,))
                businesses = cursor.fetchall()

                # 문서 내용 생성
                content_lines = []
                for biz in businesses:
                    biz_id, biz_name, biz_level, biz_desc = biz

                    # 비즈니스 아이템 조회 (최대 5개)
                    cursor.execute("""
                        SELECT title FROM business_items
                        WHERE business_id = ?
                        ORDER BY created_at DESC
                        LIMIT 5
                    """, (biz_id,))
                    items = cursor.fetchall()
                    item_names = [item[0] for item in items] if items else []

                    # 라인 생성
                    line = f"[레벨 {biz_level}] {biz_name}"
                    if biz_desc:
                        line += f" : {biz_desc}"
                    content_lines.append(line)

                    if item_names:
                        content_lines.append(f"  └ 아이템: {', '.join(item_names)}")
                    else:
                        content_lines.append("  └ 아이템: (없음)")
                    content_lines.append("")  # 빈 줄

                content = "\n".join(content_lines) if content_lines else "(등록된 비즈니스가 없습니다)"

                # 문서 업데이트
                cursor.execute("""
                    UPDATE business_documents
                    SET title = ?, content = ?, updated_at = ?
                    WHERE level = ?
                """, (f"레벨 {doc_level} 열린 비즈니스 문서", content, now, doc_level))

            conn.commit()
            conn.close()
            return {"status": "success", "message": "모든 레벨의 비즈니스 문서가 재생성되었습니다."}

        except Exception as e:
            conn.close()
            return {"status": "error", "message": str(e)}

    # ============ 이웃 (Neighbors) CRUD ============

    def get_neighbors(self, search: Optional[str] = None, info_level: Optional[int] = None) -> List[Dict]:
        """이웃 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM neighbors WHERE 1=1"
        params = []

        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")

        if info_level is not None:
            query += " AND info_level = ?"
            params.append(info_level)

        query += " ORDER BY name"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_neighbor(self, neighbor_id: int) -> Optional[Dict]:
        """이웃 상세 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM neighbors WHERE id = ?", (neighbor_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def get_neighbor_by_contact(self, contact_type: str, contact_value: str) -> Optional[Dict]:
        """연락처로 이웃 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT n.* FROM neighbors n
            JOIN contacts c ON n.id = c.neighbor_id
            WHERE c.contact_type = ? AND c.contact_value = ?
        """, (contact_type, contact_value))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def find_neighbor_by_contact(self, contact_type: str, contact_value: str) -> Optional[Dict]:
        """연락처로 이웃 찾기 (get_neighbor_by_contact의 별칭)"""
        return self.get_neighbor_by_contact(contact_type, contact_value)

    def create_neighbor(self, name: str, info_level: int = 0, rating: int = 0,
                        additional_info: Optional[str] = None,
                        business_doc: Optional[str] = None,
                        info_share: int = 0) -> Dict:
        """이웃 생성"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO neighbors (name, info_level, rating, additional_info, business_doc, info_share, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, info_level, rating, additional_info, business_doc, info_share, now, now))

        neighbor_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return self.get_neighbor(neighbor_id)

    def update_neighbor(self, neighbor_id: int, name: Optional[str] = None,
                        info_level: Optional[int] = None,
                        rating: Optional[int] = None,
                        additional_info: Optional[str] = None,
                        business_doc: Optional[str] = None,
                        info_share: Optional[int] = None) -> Dict:
        """이웃 수정"""
        conn = self._get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if info_level is not None:
            updates.append("info_level = ?")
            params.append(info_level)
        if rating is not None:
            updates.append("rating = ?")
            params.append(rating)
        if additional_info is not None:
            updates.append("additional_info = ?")
            params.append(additional_info)
        if business_doc is not None:
            updates.append("business_doc = ?")
            params.append(business_doc)
        if info_share is not None:
            updates.append("info_share = ?")
            params.append(info_share)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(neighbor_id)

            cursor.execute(f"""
                UPDATE neighbors SET {', '.join(updates)} WHERE id = ?
            """, params)
            conn.commit()

        conn.close()
        return self.get_neighbor(neighbor_id)

    def delete_neighbor(self, neighbor_id: int):
        """이웃 삭제"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM neighbors WHERE id = ?", (neighbor_id,))
        conn.commit()
        conn.close()

    # ============ 연락처 (Contacts) CRUD ============

    def get_contacts(self, neighbor_id: int) -> List[Dict]:
        """이웃의 연락처 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM contacts WHERE neighbor_id = ? ORDER BY contact_type
        """, (neighbor_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def add_contact(self, neighbor_id: int, contact_type: str, contact_value: str) -> Dict:
        """연락처 추가"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO contacts (neighbor_id, contact_type, contact_value, created_at)
            VALUES (?, ?, ?, ?)
        """, (neighbor_id, contact_type, contact_value, now))

        contact_id = cursor.lastrowid
        conn.commit()

        cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def get_contact(self, contact_id: int) -> Optional[Dict]:
        """연락처 상세 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def update_contact(self, contact_id: int, contact_type: Optional[str] = None,
                       contact_value: Optional[str] = None) -> Dict:
        """연락처 수정"""
        conn = self._get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if contact_type is not None:
            updates.append("contact_type = ?")
            params.append(contact_type)
        if contact_value is not None:
            updates.append("contact_value = ?")
            params.append(contact_value)

        if updates:
            params.append(contact_id)
            cursor.execute(f"""
                UPDATE contacts SET {', '.join(updates)} WHERE id = ?
            """, params)
            conn.commit()

        conn.close()
        return self.get_contact(contact_id)

    def delete_contact(self, contact_id: int):
        """연락처 삭제"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        conn.close()

    # ============ 메시지 (Messages) CRUD ============

    def get_messages(self, neighbor_id: Optional[int] = None,
                     status: Optional[str] = None,
                     unprocessed_only: bool = False,
                     unreplied_only: bool = False,
                     limit: int = 50) -> List[Dict]:
        """메시지 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM messages WHERE 1=1"
        params = []

        if neighbor_id is not None:
            query += " AND neighbor_id = ?"
            params.append(neighbor_id)

        if status is not None:
            query += " AND status = ?"
            params.append(status)

        if unprocessed_only:
            query += " AND processed = 0"

        if unreplied_only:
            query += " AND replied = 0 AND is_from_user = 0"

        query += " ORDER BY message_time DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_message(self, message_id: int) -> Optional[Dict]:
        """메시지 상세 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def create_message(self, content: str, contact_type: str, contact_value: str,
                       subject: Optional[str] = None,
                       neighbor_id: Optional[int] = None,
                       is_from_user: int = 0,
                       attachment_path: Optional[str] = None,
                       status: str = "received",
                       external_id: Optional[str] = None,
                       message_time: Optional[str] = None) -> Dict:
        """메시지 생성 (수신 메시지 저장)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        msg_time = message_time or now

        # neighbor_id가 없으면 contact로 찾기
        if neighbor_id is None:
            neighbor = self.get_neighbor_by_contact(contact_type, contact_value)
            if neighbor:
                neighbor_id = neighbor["id"]

        cursor.execute("""
            INSERT INTO messages (
                neighbor_id, subject, content, message_time, is_from_user,
                contact_type, contact_value, attachment_path, status, external_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (neighbor_id, subject, content, msg_time, is_from_user,
              contact_type, contact_value, attachment_path, status, external_id, now))

        message_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return self.get_message(message_id)

    def get_message_by_external_id(self, external_id: str) -> Optional[Dict]:
        """외부 ID로 메시지 조회 (중복 체크용)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE external_id = ?", (external_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def update_message_status(self, message_id: int, status: str,
                              error_message: Optional[str] = None) -> Dict:
        """메시지 상태 업데이트"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        if status == "sent":
            cursor.execute("""
                UPDATE messages SET status = ?, sent_at = ? WHERE id = ?
            """, (status, now, message_id))
        elif error_message:
            cursor.execute("""
                UPDATE messages SET status = ?, error_message = ? WHERE id = ?
            """, (status, error_message, message_id))
        else:
            cursor.execute("""
                UPDATE messages SET status = ? WHERE id = ?
            """, (status, message_id))

        conn.commit()
        conn.close()
        return self.get_message(message_id)

    def mark_message_processed(self, message_id: int) -> Dict:
        """메시지 처리 완료 표시"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET processed = 1 WHERE id = ?", (message_id,))
        conn.commit()
        conn.close()
        return self.get_message(message_id)

    def mark_message_replied(self, message_id: int) -> Dict:
        """메시지 응답 완료 표시"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET replied = 1 WHERE id = ?", (message_id,))
        conn.commit()
        conn.close()
        return self.get_message(message_id)

    # ============ 통신채널 설정 ============

    def get_all_channel_settings(self) -> List[Dict]:
        """모든 통신채널 설정 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM channel_settings ORDER BY channel_type")
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def get_channel_setting(self, channel_type: str) -> Optional[Dict]:
        """특정 통신채널 설정 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM channel_settings WHERE channel_type = ?", (channel_type,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def update_channel_setting(self, channel_type: str, enabled: Optional[bool] = None,
                               config: Optional[str] = None,
                               polling_interval: Optional[int] = None) -> Dict:
        """통신채널 설정 업데이트"""
        conn = self._get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
        if config is not None:
            updates.append("config = ?")
            params.append(config)
        if polling_interval is not None:
            updates.append("polling_interval = ?")
            params.append(polling_interval)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(channel_type)

            cursor.execute(f"""
                UPDATE channel_settings SET {', '.join(updates)} WHERE channel_type = ?
            """, params)
            conn.commit()

        conn.close()
        return self.get_channel_setting(channel_type)

    def update_channel_last_poll(self, channel_type: str):
        """채널 마지막 폴링 시간 업데이트"""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE channel_settings SET last_poll_at = ? WHERE channel_type = ?
        """, (now, channel_type))
        conn.commit()
        conn.close()
