"""
business_manager.py - 비즈니스 관리 매니저
SQLite DB를 사용하여 비즈니스, 아이템, 문서, 지침 관리
"""

import sqlite3
import uuid as _uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any


def _new_uuid() -> str:
    """동기화용 전역 고유 식별자 (정수 rowid 는 기기마다 충돌 → uuid 로 레코드 동일성 판정)."""
    return _uuid.uuid4().hex


# 기본 비즈니스 카테고리는 기기마다 따로 시드됨 → 이름 기반 결정적 uuid 로 양 기기가
# 같은 식별자를 갖게 해 합집합 머지서 중복 방지. (사용자 생성 비즈니스는 _new_uuid 로 고유.)
_SYNC_NS = _uuid.UUID("6f1b2c3d-0000-4000-8000-000000000001")
_DEFAULT_BUSINESS_NAMES = {"나눕니다", "구합니다", "놉시다", "빌려줍니다", "소개합니다", "팔아요", "할수있습니다"}


def _default_business_uuid(name: str) -> str:
    return _uuid.uuid5(_SYNC_NS, "business:" + name).hex

# DB 경로
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_data_path as _get_data_path
DATA_PATH = _get_data_path()
DB_PATH = DATA_PATH / "business.db"

# 공개인사프로필 = 비즈니스 문서 하나(전용 어휘 없이 self:business_document 그대로 사용).
# 레벨 -1: 정보공개 레벨(0=최공개 ~ 4=최비공개) 밖의 예약 키라 seed(range 5)·regenerate(0-4)가
# 건드리지 않는다(= AI 재생성 대상 아님, 순수 사용자 작성). ORDER BY level 에서 맨 앞(공개문서 최상단).
GREETING_DOC_LEVEL = -1

# 자동생성(재생성) 비즈니스 문서 첫머리 인사말 — 창고를 사람이 열어 읽을 수 있으므로 친근한 소개 한 줄.
# 재생성 버튼이 만드는 문서 내용 자체에 박히므로 '공개문서' 탭 표시본 = 창고 발행본이 일치한다.
# ★1순위=사용자가 공개문서 탭에서 쓴 '공개인사프로필'(레벨 -1) 내용 → 그게 곧 Nostr 프로필이자
#   창고 문서 첫머리(한 곳에 쓰면 두 곳에 반영, 일관). 비어 있으면 아래 기본 문구로 폴백.
# 기본값은 코드에, 문구 교체·끄기는 warehouse.json 의 greeting 키로(미추적 파일, title/email 과 같은 자리).
_WAREHOUSE_CONFIG = DATA_PATH / "warehouse.json"
_DEFAULT_GREETING = "안녕하세요. 이건 저의 비즈니스 내용들입니다. 둘러보시고 관심 있으시면 연락 바랍니다."


def _fallback_greeting() -> str:
    """공개인사프로필(-1)이 비었을 때 쓰는 폴백 인사말. warehouse.json 에 greeting 키가 없으면
    기본 인사말, 빈 문자열이면 사용자가 명시적으로 끈 것(생략)."""
    import json
    try:
        g = json.loads(_WAREHOUSE_CONFIG.read_text(encoding="utf-8")).get("greeting")
    except Exception:
        g = None
    return _DEFAULT_GREETING if g is None else str(g).strip()


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

        # 마이그레이션: neighbors 테이블에 favorite 컬럼 추가 (빠른 연락처)
        try:
            cursor.execute("ALTER TABLE neighbors ADD COLUMN favorite INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 이미 존재하면 무시

        # 마이그레이션: indiebizOS peer 표식 (상대가 indiebizOS 노드인지 + 프로토콜 버전)
        for _col, _ddl in (("is_indiebiz_peer", "INTEGER DEFAULT 0"), ("peer_version", "TEXT")):
            try:
                cursor.execute(f"ALTER TABLE neighbors ADD COLUMN {_col} {_ddl}")
            except sqlite3.OperationalError:
                pass  # 이미 존재하면 무시

        # 마이그레이션: 개인 포털 인증 (이웃 = 포털 회원 통합). 포털 로그인한 사람이 이웃으로
        # 자동 등록되고, info_level(0~4) 하나가 메신저 이웃등급 겸 포털 앱 사용등급이 된다.
        # ★이 컬럼들은 맥(운영자) 전용 — 폰엔 포털이 없다. business_sync 가 머지에서 제외해
        #   폰 편집이 포털 인증을 지우지 않게 한다(business_sync.PORTAL_LOCAL_COLS).
        for _col, _ddl in (("portal_login_id", "TEXT"), ("portal_pw", "TEXT"),
                           ("portal_key", "TEXT"), ("portal_revoked", "INTEGER DEFAULT 0"),
                           ("portal_joined_at", "TEXT"), ("portal_last_used", "TEXT")):
            try:
                cursor.execute(f"ALTER TABLE neighbors ADD COLUMN {_col} {_ddl}")
            except sqlite3.OperationalError:
                pass  # 이미 존재하면 무시

        # 마이그레이션: 창고이웃 등기부 (2026-07-18) — 이웃 레코드에 창고 축.
        # warehouse_url=이웃 공유창고 공개 주소(그 노드의 얼굴), warehouse_memo=그 창고에 대한
        # 냄새 메모(additional_info 수기 메모와 분리 — AI 갱신이 사용자 메모를 덮지 않게),
        # warehouse_key=레벨1+ 열람 자격(/k/ 키, 추후). warehouse_feed.py 폴러가 url 을 순회한다.
        # ★맥 전용 — business_sync 머지 제외(business_sync.PORTAL_LOCAL_COLS 에 합류).
        for _col in ("warehouse_url", "warehouse_memo", "warehouse_key"):
            try:
                cursor.execute(f"ALTER TABLE neighbors ADD COLUMN {_col} TEXT")
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

        # 공개인사프로필 (사용자가 직접 작성하는 공개 인사 — 레벨 문서와 별개, AI 재생성 대상 아님).
        # 전용 어휘 없이 self:business_document 로 편집·조회. 발행 시 열린 비즈니스 문서 0 과 결합.
        cursor.execute("""
            INSERT OR IGNORE INTO business_documents (level, title, content)
            VALUES (?, ?, ?)
        """, (GREETING_DOC_LEVEL, "공개인사프로필", ""))

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

        # Nostr hex pubkey → npub 마이그레이션 (한 번만 실행)
        self._migrate_nostr_hex_to_npub()

        # 동기화용 컬럼(uuid/parent_uuid/updated_at/deleted) — 폰↔PC 합집합 머지 토대
        self._migrate_sync_columns()

        # 창고주소 컬럼→연락처 행 이관 — ★반드시 sync 컬럼 뒤(아래 메서드 주석 참조)
        self._migrate_warehouse_contacts()

        # 주소 종류 어휘 통일 — contact_type 'gmail' → 'email'
        self._migrate_contact_type_email()

    def _migrate_contact_type_email(self):
        """마이그레이션(2026-07-21): 주소 종류(contact_type) 어휘를 'email' 하나로 통일.

        contact_type = 상대 **주소의 종류**(email/nostr/warehouse)이고,
        channel_type = 내가 쓰는 **발신 수단**(gmail=내 Gmail 계정/nostr=릴레이)이다.
        서로 다른 축인데 주소 종류 칸에 수단 이름 'gmail' 이 쌓여 있었다(Gmail 수신 →
        이웃 자동 생성 경로). 한 단어=한 개념 원칙대로 주소 종류는 'email' 로 굳힌다.
        폰도 같은 코드를 부팅하므로 양쪽에서 돌고, phone_sync 머지 뒤에도 어휘가 일치한다.
        멱등 — 이미 통일됐으면 0행 UPDATE.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE contacts SET contact_type = 'email' WHERE contact_type = 'gmail'")
        n_c = cursor.rowcount
        cursor.execute("UPDATE messages SET contact_type = 'email' WHERE contact_type = 'gmail'")
        n_m = cursor.rowcount
        conn.commit()
        conn.close()
        if n_c or n_m:
            print(f"[business_manager] contact_type 'gmail'→'email' 이관: 연락처 {n_c}행, 메시지 {n_m}행")

    def _migrate_warehouse_contacts(self):
        """마이그레이션(2026-07-18 2차): 창고주소 = 연락방법 — neighbors.warehouse_url 컬럼(1차)을
        contacts(contact_type='warehouse') 행으로 이관. 창고주소도 이메일·nostr 처럼 그 사람에게
        닿는 접점(풀로 읽는 길)이므로 연락처 테이블이 곧 창고이웃 등기부가 된다 — 이웃당 여러
        창고 가능, "창고주소만 아는 상대"도 그 주소가 연락처라 정상 이웃. 컬럼은 이관 후 비움.

        ★호출 순서: 반드시 _migrate_sync_columns 뒤 — 이관 INSERT 가 uuid·neighbor_uuid·
        updated_at 을 쓰는데 신선 DB 는 그 컬럼들이 sync 마이그레이션에서야 생긴다.
        (2026-07-20 CI 윈도우 import 스모크가 신선 DB 부팅 죽음(no such column: uuid)으로
        검출 — 기존 DB 는 이전 실행이 컬럼을 이미 만들어 안 걸렸던 순서 버그.)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, uuid, warehouse_url FROM neighbors "
                       "WHERE warehouse_url IS NOT NULL AND warehouse_url != ''")
        for _nid, _nuuid, _wurl in cursor.fetchall():
            cursor.execute("SELECT 1 FROM contacts WHERE neighbor_id=? AND contact_type='warehouse' "
                           "AND contact_value=? AND (deleted IS NOT 1)", (_nid, _wurl))
            if not cursor.fetchone():
                _now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO contacts (neighbor_id, contact_type, contact_value,
                                          created_at, updated_at, uuid, neighbor_uuid)
                    VALUES (?, 'warehouse', ?, ?, ?, ?, ?)
                """, (_nid, _wurl, _now, _now, _new_uuid(), _nuuid))
            cursor.execute("UPDATE neighbors SET warehouse_url = NULL WHERE id = ?", (_nid,))
        conn.commit()
        conn.close()

    def _migrate_sync_columns(self):
        """동기화용 컬럼 추가 + 기존 행 backfill (멱등).

        폰↔PC business.db 를 합집합(union) 머지하기 위한 토대. 머지는 레코드별
        last-write-wins(updated_at 늦은 쪽이 이김) + tombstone(deleted=1, 삭제도 데이터로 전파해
        합집합서 부활 방지) + uuid(정수 rowid 는 기기마다 달라 레코드 동일성 판정 불가).
        대상=주소록 메타데이터(이웃·연락처·사업·아이템). 문서/지침은 level 로 식별(컬럼 불요).
        메시지/채널설정은 제외(내용=릴레이/Gmail 진실원, 설정=PC 전용)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        def _add(table, coldef):
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
            except sqlite3.OperationalError:
                pass  # 이미 존재

        # 엔티티: uuid + deleted
        _add("neighbors", "uuid TEXT")
        _add("neighbors", "deleted INTEGER DEFAULT 0")
        _add("businesses", "uuid TEXT")
        _add("businesses", "deleted INTEGER DEFAULT 0")
        # 자식: uuid + parent_uuid + deleted (+ contacts 는 updated_at 도 없어 추가)
        _add("contacts", "uuid TEXT")
        _add("contacts", "neighbor_uuid TEXT")
        _add("contacts", "updated_at TEXT")
        _add("contacts", "deleted INTEGER DEFAULT 0")
        _add("business_items", "uuid TEXT")
        _add("business_items", "business_uuid TEXT")
        _add("business_items", "deleted INTEGER DEFAULT 0")

        # uuid 조회 인덱스
        for t in ("neighbors", "businesses", "contacts", "business_items"):
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_uuid ON {t}(uuid)")

        # backfill: uuid 없는 기존 행에 부여 (부모 먼저 → 자식 parent_uuid remap 가능)
        for t in ("neighbors", "businesses", "contacts", "business_items"):
            if t == "businesses":
                # 기본 카테고리는 결정적 uuid(양 기기 일치), 사용자 생성분은 무작위
                cursor.execute("SELECT id, name FROM businesses WHERE uuid IS NULL OR uuid = ''")
                for rid, name in cursor.fetchall():
                    u = _default_business_uuid(name) if name in _DEFAULT_BUSINESS_NAMES else _new_uuid()
                    cursor.execute("UPDATE businesses SET uuid = ? WHERE id = ?", (u, rid))
            else:
                cursor.execute(f"SELECT id FROM {t} WHERE uuid IS NULL OR uuid = ''")
                for (rid,) in cursor.fetchall():
                    cursor.execute(f"UPDATE {t} SET uuid = ? WHERE id = ?", (_new_uuid(), rid))

        # contacts.updated_at backfill = created_at (없으면 now)
        cursor.execute(
            "UPDATE contacts SET updated_at = COALESCE(NULLIF(created_at, ''), ?) "
            "WHERE updated_at IS NULL OR updated_at = ''",
            (datetime.now().isoformat(),))

        # 자식 parent_uuid backfill (부모 uuid 연결)
        cursor.execute(
            "UPDATE contacts SET neighbor_uuid = "
            "(SELECT uuid FROM neighbors WHERE neighbors.id = contacts.neighbor_id) "
            "WHERE (neighbor_uuid IS NULL OR neighbor_uuid = '') AND neighbor_id IS NOT NULL")
        cursor.execute(
            "UPDATE business_items SET business_uuid = "
            "(SELECT uuid FROM businesses WHERE businesses.id = business_items.business_id) "
            "WHERE (business_uuid IS NULL OR business_uuid = '') AND business_id IS NOT NULL")

        # 기본 카테고리 reconcile: 이전 마이그레이션이 무작위 uuid 를 부여했을 수 있어,
        # 이름 기반 결정적 uuid 로 강제(양 기기 수렴). 자식 items 의 business_uuid 도 함께 동기.
        # 멱등: 이미 결정적이면 건너뜀.
        for name in _DEFAULT_BUSINESS_NAMES:
            du = _default_business_uuid(name)
            cursor.execute("SELECT id, uuid FROM businesses WHERE name = ?", (name,))
            for bid, old_uuid in cursor.fetchall():
                if old_uuid == du:
                    continue
                cursor.execute("UPDATE businesses SET uuid = ? WHERE id = ?", (du, bid))
                cursor.execute("UPDATE business_items SET business_uuid = ? WHERE business_id = ?", (du, bid))

        conn.commit()
        conn.close()

    def _migrate_nostr_hex_to_npub(self):
        """DB의 nostr contact_value가 hex면 npub로 변환"""
        try:
            from pynostr.key import PublicKey
        except ImportError:
            return

        conn = self._get_connection()
        cursor = conn.cursor()
        updated = 0

        # contacts 테이블
        cursor.execute("SELECT id, contact_value FROM contacts WHERE contact_type = 'nostr'")
        for row in cursor.fetchall():
            cid, val = row['id'], row['contact_value']
            if val and not val.startswith('npub') and len(val) == 64:
                try:
                    npub = PublicKey(bytes.fromhex(val)).bech32()
                    cursor.execute("UPDATE contacts SET contact_value = ? WHERE id = ?", (npub, cid))
                    updated += 1
                except Exception:
                    pass

        # messages 테이블
        cursor.execute("SELECT id, contact_value FROM messages WHERE contact_type = 'nostr'")
        for row in cursor.fetchall():
            mid, val = row['id'], row['contact_value']
            if val and not val.startswith('npub') and len(val) == 64:
                try:
                    npub = PublicKey(bytes.fromhex(val)).bech32()
                    cursor.execute("UPDATE messages SET contact_value = ? WHERE id = ?", (npub, mid))
                    updated += 1
                except Exception:
                    pass

        # neighbors 이름도 hex 기반이면 npub로 갱신
        cursor.execute("""
            SELECT n.id, n.name, c.contact_value FROM neighbors n
            JOIN contacts c ON c.neighbor_id = n.id
            WHERE c.contact_type = 'nostr' AND c.contact_value LIKE 'npub%'
        """)
        for row in cursor.fetchall():
            nid, name, npub_val = row['id'], row['name'], row['contact_value']
            # 이름이 hex 패턴(16자+...)이면 npub 기반으로 갱신
            if name and not name.startswith('npub') and '...' in name:
                prefix = name.replace('...', '')
                if len(prefix) == 16 and all(c in '0123456789abcdef' for c in prefix.lower()):
                    new_name = npub_val[:20] + '...' if len(npub_val) > 20 else npub_val
                    cursor.execute("UPDATE neighbors SET name = ? WHERE id = ?", (new_name, nid))
                    updated += 1

        if updated > 0:
            conn.commit()
            print(f"[BusinessManager] Nostr hex→npub 마이그레이션 완료: {updated}건")
        conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Row 객체를 딕셔너리로 변환"""
        return dict(row) if row else None

    # ============ 비즈니스 CRUD ============

    def get_businesses(self, level: Optional[int] = None, search: Optional[str] = None) -> List[Dict]:
        """비즈니스 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM businesses WHERE (deleted IS NOT 1)"
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
        cursor.execute("SELECT * FROM businesses WHERE id = ? AND (deleted IS NOT 1)", (business_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def create_business(self, name: str, level: int = 0, description: Optional[str] = None) -> Dict:
        """비즈니스 생성"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO businesses (name, level, description, created_at, updated_at, uuid)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, level, description, now, now, _new_uuid()))

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
        """비즈니스 삭제 (소프트 삭제 — tombstone 으로 합집합 머지서 부활 방지, 아이템도 함께)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("UPDATE businesses SET deleted = 1, updated_at = ? WHERE id = ?", (now, business_id))
        cursor.execute("UPDATE business_items SET deleted = 1, updated_at = ? WHERE business_id = ?", (now, business_id))
        conn.commit()
        conn.close()

    # ============ 비즈니스 아이템 CRUD ============

    def get_business_items(self, business_id: int) -> List[Dict]:
        """비즈니스 아이템 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM business_items WHERE business_id = ? AND (deleted IS NOT 1) ORDER BY created_at DESC
        """, (business_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def get_business_item(self, item_id: int) -> Optional[Dict]:
        """비즈니스 아이템 상세 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM business_items WHERE id = ? AND (deleted IS NOT 1)", (item_id,))
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
        cursor.execute("SELECT uuid FROM businesses WHERE id = ?", (business_id,))
        _r = cursor.fetchone()
        business_uuid = _r[0] if _r else None
        cursor.execute("""
            INSERT INTO business_items (business_id, title, details, attachment_path, created_at, updated_at, uuid, business_uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (business_id, title, details, attachment_path, now, now, _new_uuid(), business_uuid))

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
        """비즈니스 아이템 삭제 (소프트 삭제 — tombstone)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("UPDATE business_items SET deleted = 1, updated_at = ? WHERE id = ?", (now, item_id))
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

            # 첫머리 인사말 결정 — 사용자가 쓴 공개인사프로필(-1) 우선, 없으면 폴백 문구.
            cursor.execute(
                "SELECT content FROM business_documents WHERE level = ?", (GREETING_DOC_LEVEL,)
            )
            _gr = cursor.fetchone()
            _profile = ((_gr["content"] if _gr else None) or "").strip()
            greeting = _profile or _fallback_greeting()

            for doc_level in range(5):  # 레벨 0~4
                # 해당 레벨 이하의 모든 비즈니스 조회
                cursor.execute("""
                    SELECT b.id, b.name, b.level, b.description
                    FROM businesses b
                    WHERE b.level >= 0 AND b.level <= ? AND (b.deleted IS NOT 1)
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
                        WHERE business_id = ? AND (deleted IS NOT 1)
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

                body = "\n".join(content_lines) if content_lines else "(등록된 비즈니스가 없습니다)"
                # 첫머리 인사말(루프 전 결정) — 재생성 문서 내용 자체에 포함(공개문서 탭 = 창고 발행본 일치).
                content = f"{greeting}\n\n{body}" if greeting else body

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

        query = "SELECT * FROM neighbors WHERE (deleted IS NOT 1)"
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

    def get_inbox_summary(self, search: Optional[str] = None,
                          info_level: Optional[int] = None) -> List[Dict]:
        """메신저 inbox용 이웃 일괄 요약 — 이웃 N명을 연결 1개·쿼리 4개로.

        이웃당 개별 조회(마지막 메시지·미답신 수·연락처)를 반복하면 이웃 수에
        비례해 느려지고, /ibl/execute 가 이벤트 루프 동기 실행이라 그 시간만큼
        백엔드 전체가 멈춘다. 여기서 GROUP BY/윈도우로 한 번에 뽑는다.

        반환: get_neighbors 와 같은 이웃 dict + 밑줄 필드 셋
          _last: 마지막 메시지 dict(message_time DESC 첫 행) 또는 None
          _unread: 미답신 수신 수 (replied=0, is_from_user=0)
          _channel_contacts: [(contact_type, contact_value)] — gmail/nostr만, type 순
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM neighbors WHERE (deleted IS NOT 1)"
        params: list = []
        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")
        if info_level is not None:
            query += " AND info_level = ?"
            params.append(info_level)
        query += " ORDER BY name"
        cursor.execute(query, params)
        neighbors = [self._row_to_dict(r) for r in cursor.fetchall()]

        # 이웃별 마지막 메시지 (get_messages 와 동일하게 message_time DESC 기준)
        cursor.execute("""
            SELECT * FROM (
                SELECT m.*, ROW_NUMBER() OVER (
                    PARTITION BY neighbor_id ORDER BY message_time DESC
                ) AS _rn
                FROM messages m WHERE neighbor_id IS NOT NULL
            ) WHERE _rn = 1
        """)
        last_by_nid = {}
        for r in cursor.fetchall():
            d = dict(r)
            d.pop("_rn", None)
            last_by_nid[d["neighbor_id"]] = d

        cursor.execute("""
            SELECT neighbor_id, COUNT(*) AS cnt FROM messages
            WHERE replied = 0 AND is_from_user = 0 AND neighbor_id IS NOT NULL
            GROUP BY neighbor_id
        """)
        unread_by_nid = {r["neighbor_id"]: r["cnt"] for r in cursor.fetchall()}

        # 메시징 채널 연락처 — get_contacts 와 같은 contact_type 순 (email < nostr).
        # 발신 가능한 주소 종류만(warehouse 는 주소일 뿐 발신 수단이 없다).
        cursor.execute("""
            SELECT neighbor_id, contact_type, contact_value FROM contacts
            WHERE (deleted IS NOT 1) AND contact_type IN ('email', 'nostr')
            ORDER BY contact_type
        """)
        contacts_by_nid: Dict[int, list] = {}
        for r in cursor.fetchall():
            contacts_by_nid.setdefault(r["neighbor_id"], []).append(
                (r["contact_type"], r["contact_value"]))
        conn.close()

        for n in neighbors:
            nid = n["id"]
            n["_last"] = last_by_nid.get(nid)
            n["_unread"] = unread_by_nid.get(nid, 0)
            n["_channel_contacts"] = contacts_by_nid.get(nid, [])
        return neighbors

    def get_neighbor(self, neighbor_id: int) -> Optional[Dict]:
        """이웃 상세 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM neighbors WHERE id = ? AND (deleted IS NOT 1)", (neighbor_id,))
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
              AND (n.deleted IS NOT 1) AND (c.deleted IS NOT 1)
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
            INSERT INTO neighbors (name, info_level, rating, additional_info, business_doc, info_share, created_at, updated_at, uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, info_level, rating, additional_info, business_doc, info_share, now, now, _new_uuid()))

        neighbor_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return self.get_neighbor(neighbor_id)

    def update_neighbor(self, neighbor_id: int, name: Optional[str] = None,
                        info_level: Optional[int] = None,
                        rating: Optional[int] = None,
                        additional_info: Optional[str] = None,
                        business_doc: Optional[str] = None,
                        info_share: Optional[int] = None,
                        favorite: Optional[int] = None) -> Dict:
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
        if favorite is not None:
            updates.append("favorite = ?")
            params.append(favorite)

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

    def merge_neighbors(self, target_id: int, source_id: int) -> Optional[Dict]:
        """이웃 병합 — 같은 사람이 두 경로(창고 등록/창고 가입 등)로 두 번 등록됐을 때.

        source 의 연락처·메시지를 target 으로 옮기고, target 의 빈 자리(메모·문서·창고메모·
        포털 로그인 자격)를 source 로 보강한 뒤 source 는 은퇴(soft delete). 레벨·평점은
        큰 값(같은 사람이니 더 가까운 관계가 사실). 판별은 사람이, 병합은 여기가 한다."""
        if target_id == source_id:
            raise ValueError("같은 이웃입니다")
        t = self.get_neighbor(target_id)
        s = self.get_neighbor(source_id)
        if not t or not s:
            raise ValueError("이웃을 찾을 수 없습니다")
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        # 연락처 이관 — (type, value) 가 target 에 이미 있으면 source 쪽만 은퇴(중복 방지)
        cursor.execute(
            "SELECT contact_type, contact_value FROM contacts "
            "WHERE neighbor_id = ? AND (deleted IS NOT 1)", (target_id,))
        existing = {(r["contact_type"], r["contact_value"]) for r in cursor.fetchall()}
        cursor.execute(
            "SELECT id, contact_type, contact_value FROM contacts "
            "WHERE neighbor_id = ? AND (deleted IS NOT 1)", (source_id,))
        for r in cursor.fetchall():
            if (r["contact_type"], r["contact_value"]) in existing:
                cursor.execute("UPDATE contacts SET deleted = 1, updated_at = ? WHERE id = ?",
                               (now, r["id"]))
            else:
                cursor.execute("UPDATE contacts SET neighbor_id = ?, updated_at = ? WHERE id = ?",
                               (target_id, now, r["id"]))
        # 대화 이관 — 두 레코드의 메시지 역사가 한 사람의 스레드로 합류
        cursor.execute("UPDATE messages SET neighbor_id = ? WHERE neighbor_id = ?",
                       (target_id, source_id))
        # 필드 병합 — target 우선, 빈 자리만 보강. 숫자 축은 큰 값.
        sets, params = [], []
        def _fill(col, val):
            sets.append(f"{col} = ?")
            params.append(val)
        if (s.get("info_level") or 0) > (t.get("info_level") or 0):
            _fill("info_level", s["info_level"])
        if (s.get("rating") or 0) > (t.get("rating") or 0):
            _fill("rating", s["rating"])
        if (s.get("favorite") or 0) and not (t.get("favorite") or 0):
            _fill("favorite", 1)
        for col in ("additional_info", "business_doc", "warehouse_memo"):
            if not (t.get(col) or "").strip() and (s.get(col) or "").strip():
                _fill(col, s[col])
        # 포털 로그인 자격 — target 에 없고 source 에 있으면 이사(가입 계정 연속성).
        # 둘 다 있으면 target 것 유지(source 쪽은 아래 은퇴에서 로그인 아이디를 비워 무효화).
        if not (t.get("portal_login_id") or "") and (s.get("portal_login_id") or ""):
            for col in ("portal_login_id", "portal_pw", "portal_key",
                        "portal_revoked", "portal_joined_at", "portal_last_used"):
                _fill(col, s.get(col))
        if sets:
            params.extend([now, target_id])
            cursor.execute(f"UPDATE neighbors SET {', '.join(sets)}, updated_at = ? WHERE id = ?",
                           params)
        # source 은퇴 — 로그인 아이디도 비워 유령 로그인 차단(아이디 유니크 재사용 가능)
        cursor.execute(
            "UPDATE neighbors SET deleted = 1, portal_login_id = NULL, updated_at = ? WHERE id = ?",
            (now, source_id))
        cursor.execute("UPDATE contacts SET deleted = 1, updated_at = ? WHERE neighbor_id = ?",
                       (now, source_id))
        conn.commit()
        conn.close()
        return self.get_neighbor(target_id)

    def delete_neighbor(self, neighbor_id: int):
        """이웃 삭제 (소프트 삭제 — tombstone, 연락처도 함께)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("UPDATE neighbors SET deleted = 1, updated_at = ? WHERE id = ?", (now, neighbor_id))
        cursor.execute("UPDATE contacts SET deleted = 1, updated_at = ? WHERE neighbor_id = ?", (now, neighbor_id))
        conn.commit()
        conn.close()

    def get_favorite_neighbors(self) -> List[Dict]:
        """빠른 연락처(즐겨찾기) 이웃 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM neighbors WHERE favorite = 1 AND (deleted IS NOT 1) ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def toggle_neighbor_favorite(self, neighbor_id: int) -> Dict:
        """이웃의 즐겨찾기 토글"""
        neighbor = self.get_neighbor(neighbor_id)
        if not neighbor:
            return None
        new_favorite = 0 if neighbor.get('favorite', 0) == 1 else 1
        return self.update_neighbor(neighbor_id, favorite=new_favorite)

    def mark_neighbor_peer(self, neighbor_id: int, version: Optional[str] = None) -> None:
        """이웃을 indiebizOS peer 로 표시 (발신 DM 의 indiebiz 태그 감지 시). 멱등."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE neighbors SET is_indiebiz_peer = 1, peer_version = ?, updated_at = ? WHERE id = ?",
            (version, datetime.now().isoformat(), neighbor_id),
        )
        conn.commit()
        conn.close()

    # ============ 개인 포털 인증 (이웃 = 포털 회원 통합) ============
    # 포털 로그인·개인 링크 열쇠는 이웃 레코드에 붙는 맥 전용 속성. info_level(0~4)이 곧
    # 포털 앱 사용등급이라, 메신저에서 이웃을 승급하면 포털 접근도 함께 열린다.
    # ★portal_* 갱신은 updated_at 을 건드리지 않는다(동기화 LWW 는 실제 내용 편집만으로 결정 —
    #   맥 전용 인증은 동기화 대상이 아니므로 last_used 잦은 write 가 머지 충돌을 만들지 않게).

    _PORTAL_COLS = ("portal_login_id", "portal_pw", "portal_key",
                    "portal_revoked", "portal_joined_at", "portal_last_used")
    _WAREHOUSE_COLS = ("warehouse_url", "warehouse_memo", "warehouse_key")

    def update_neighbor_warehouse(self, neighbor_id: int, **fields) -> Optional[Dict]:
        """이웃의 창고 컬럼만 갱신(창고이웃 등기부). 허용 컬럼 외는 무시."""
        sets, params = [], []
        for k, v in fields.items():
            if k in self._WAREHOUSE_COLS:
                sets.append(f"{k} = ?")
                params.append(v)
        if not sets:
            return self.get_neighbor(neighbor_id)
        params.append(neighbor_id)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE neighbors SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        conn.close()
        return self.get_neighbor(neighbor_id)

    def get_warehouse_contacts(self) -> List[Dict]:
        """창고이웃 등기부 = contacts(contact_type='warehouse') — 창고주소도 연락방법(2026-07-18 2차).
        이웃당 여러 창고 가능. 반환: contact_id·neighbor_id·name·url·warehouse_memo·info_level."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id AS contact_id, c.neighbor_id, c.contact_value AS url,
                   n.name, n.warehouse_memo, n.info_level, n.favorite
            FROM contacts c JOIN neighbors n ON n.id = c.neighbor_id
            WHERE c.contact_type = 'warehouse' AND (c.deleted IS NOT 1) AND (n.deleted IS NOT 1)
            ORDER BY n.name
        """)
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def update_neighbor_portal(self, neighbor_id: int, **fields) -> Optional[Dict]:
        """이웃의 포털 인증 컬럼만 갱신(updated_at 불변). 허용 컬럼 외는 무시."""
        sets, params = [], []
        for k, v in fields.items():
            if k in self._PORTAL_COLS:
                sets.append(f"{k} = ?")
                params.append(v)
        if not sets:
            return self.get_neighbor(neighbor_id)
        params.append(neighbor_id)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE neighbors SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        conn.close()
        return self.get_neighbor(neighbor_id)

    def find_neighbor_by_portal_key(self, key: str, include_revoked: bool = False) -> Optional[Dict]:
        """개인 링크/세션 열쇠로 이웃 찾기(전역). 기본은 회수된 회원 제외."""
        if not key:
            return None
        conn = self._get_connection()
        cursor = conn.cursor()
        q = "SELECT * FROM neighbors WHERE portal_key = ? AND (deleted IS NOT 1)"
        if not include_revoked:
            q += " AND (portal_revoked IS NOT 1)"
        cursor.execute(q, (key,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def find_neighbor_by_portal_login(self, login_id: str) -> Optional[Dict]:
        """포털 로그인 아이디로 이웃 찾기(전역, 대소문자 무시). 회수 여부는 호출측이 확인."""
        lid = (login_id or "").strip().lower()
        if not lid:
            return None
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM neighbors WHERE LOWER(portal_login_id) = ? AND (deleted IS NOT 1)", (lid,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    # ============ 연락처 (Contacts) CRUD ============

    def get_contacts(self, neighbor_id: int) -> List[Dict]:
        """이웃의 연락처 목록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM contacts WHERE neighbor_id = ? AND (deleted IS NOT 1) ORDER BY contact_type
        """, (neighbor_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]

    def add_contact(self, neighbor_id: int, contact_type: str, contact_value: str) -> Dict:
        """연락처 추가"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute("SELECT uuid FROM neighbors WHERE id = ?", (neighbor_id,))
        _r = cursor.fetchone()
        neighbor_uuid = _r[0] if _r else None
        cursor.execute("""
            INSERT INTO contacts (neighbor_id, contact_type, contact_value, created_at, updated_at, uuid, neighbor_uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (neighbor_id, contact_type, contact_value, now, now, _new_uuid(), neighbor_uuid))

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
        cursor.execute("SELECT * FROM contacts WHERE id = ? AND (deleted IS NOT 1)", (contact_id,))
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
            updates.append("updated_at = ?")  # LWW 충돌 해소 기준
            params.append(datetime.now().isoformat())
            params.append(contact_id)
            cursor.execute(f"""
                UPDATE contacts SET {', '.join(updates)} WHERE id = ?
            """, params)
            conn.commit()

        conn.close()
        return self.get_contact(contact_id)

    def delete_contact(self, contact_id: int):
        """연락처 삭제 (소프트 삭제 — tombstone)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("UPDATE contacts SET deleted = 1, updated_at = ? WHERE id = ?", (now, contact_id))
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
