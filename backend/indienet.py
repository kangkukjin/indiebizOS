"""
IndieNet - Nostr 기반 P2P 커뮤니티
독립적인 사용자 ID로 #IndieNet 해시태그 게시판 운영
"""

import os
import json
import time
import uuid
import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    from pynostr.key import PrivateKey, PublicKey
    from pynostr.event import Event, EventKind
    import websocket
    HAS_NOSTR = True
except ImportError:
    HAS_NOSTR = False
    print("⚠️  IndieNet: pynostr 필요 - pip install pynostr websocket-client")
    # 타입 힌트를 위한 더미 클래스 정의
    class Event:
        pass
    class EventKind:
        TEXT_NOTE = 1
        ENCRYPTED_DIRECT_MESSAGE = 4
    class PrivateKey:
        pass
    class PublicKey:
        pass


# IndieNet 데이터 디렉토리
INDIENET_DIR = Path.home() / '.indiebiz' / 'indienet'
IDENTITY_FILE = INDIENET_DIR / 'identity.json'
SETTINGS_FILE = INDIENET_DIR / 'settings.json'
CACHE_DIR = INDIENET_DIR / 'cache'
POSTS_DB = INDIENET_DIR / 'posts.db'  # 공개 글 영구 캐시 (릴레이 prune 대비)
DMS_DB = INDIENET_DIR / 'dms.db'      # 수신 DM 영구 캐시 (릴레이 prune 대비)

# 기본 릴레이
DEFAULT_RELAYS = [
    # 2026-06-12: 도달성 실측 후 정리 — nostr.wine(403 유료 거부)·nostr.band(상시 타임아웃) 제거,
    # 확인된 무료 릴레이로 중복성 확보(글 prune 대비 fan-out 읽기/쓰기 대상).
    'wss://nos.lol',
    'wss://relay.damus.io',
    'wss://relay.primal.net',
    'wss://relay.snort.social',
    'wss://nostr.mom',
    'wss://purplepag.es',
]

# IndieNet 해시태그
INDIENET_TAG = "IndieNet"


class IndieNetIdentity:
    """IndieNet 사용자 ID 관리"""

    def __init__(self):
        self.private_key: Optional[PrivateKey] = None
        self.public_key: Optional[PublicKey] = None
        self.npub: Optional[str] = None
        self.nsec: Optional[str] = None
        self.created_at: Optional[str] = None
        self.display_name: Optional[str] = None

    def load_or_create(self) -> bool:
        """ID 로드 또는 신규 생성"""
        if not HAS_NOSTR:
            return False

        # 디렉토리 생성
        INDIENET_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if IDENTITY_FILE.exists():
            return self._load_identity()
        else:
            return self._create_identity()

    def _load_identity(self) -> bool:
        """기존 ID 로드"""
        try:
            with open(IDENTITY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            nsec = data.get('nsec')
            if nsec and nsec.startswith('nsec'):
                self.private_key = PrivateKey.from_nsec(nsec)
            else:
                # hex 형식으로 저장된 경우
                self.private_key = PrivateKey(bytes.fromhex(data.get('private_key_hex', '')))

            self.public_key = self.private_key.public_key
            self.npub = self.public_key.bech32()
            self.nsec = self.private_key.bech32()
            self.created_at = data.get('created_at')
            self.display_name = data.get('display_name', '')

            print(f"✓ IndieNet: ID 로드 완료 - {self.npub[:20]}...")
            return True

        except Exception as e:
            print(f"✗ IndieNet: ID 로드 실패 - {e}")
            return False

    def _create_identity(self) -> bool:
        """새 ID 생성"""
        try:
            self.private_key = PrivateKey()
            self.public_key = self.private_key.public_key
            self.npub = self.public_key.bech32()
            self.nsec = self.private_key.bech32()
            self.created_at = datetime.now().isoformat()
            self.display_name = ""

            # 저장
            data = {
                'npub': self.npub,
                'nsec': self.nsec,
                'private_key_hex': self.private_key.hex(),
                'public_key_hex': self.public_key.hex(),
                'created_at': self.created_at,
                'display_name': self.display_name
            }

            with open(IDENTITY_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # 보안: 파일 권한 제한
            os.chmod(IDENTITY_FILE, 0o600)

            print(f"✓ IndieNet: 새 ID 생성 완료")
            print(f"  npub: {self.npub}")
            return True

        except Exception as e:
            print(f"✗ IndieNet: ID 생성 실패 - {e}")
            return False

    def import_nsec(self, nsec: str) -> bool:
        """외부 nsec 키로 ID 변경"""
        if not HAS_NOSTR:
            return False

        try:
            # nsec 검증 및 변환
            if not nsec.startswith('nsec'):
                raise ValueError("nsec는 'nsec'로 시작해야 합니다")

            self.private_key = PrivateKey.from_nsec(nsec)
            self.public_key = self.private_key.public_key
            self.npub = self.public_key.bech32()
            self.nsec = self.private_key.bech32()
            # 가져온 ID는 현재 시간으로 설정
            self.created_at = datetime.now().isoformat()

            # 저장
            data = {
                'npub': self.npub,
                'nsec': self.nsec,
                'private_key_hex': self.private_key.hex(),
                'public_key_hex': self.public_key.hex(),
                'created_at': self.created_at,
                'display_name': self.display_name or '',
                'imported': True  # 가져온 ID임을 표시
            }

            with open(IDENTITY_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            os.chmod(IDENTITY_FILE, 0o600)

            print(f"✓ IndieNet: ID 가져오기 완료 - {self.npub[:20]}...")
            return True

        except Exception as e:
            print(f"✗ IndieNet: ID 가져오기 실패 - {e}")
            return False

    def reset_identity(self) -> bool:
        """ID를 새로 생성 (기존 ID 삭제)"""
        try:
            # 기존 파일 삭제
            if IDENTITY_FILE.exists():
                IDENTITY_FILE.unlink()

            # 새 ID 생성
            return self._create_identity()

        except Exception as e:
            print(f"✗ IndieNet: ID 초기화 실패 - {e}")
            return False

    def set_display_name(self, name: str) -> bool:
        """표시 이름 설정"""
        try:
            self.display_name = name

            # 파일 업데이트
            if IDENTITY_FILE.exists():
                with open(IDENTITY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['display_name'] = name
                with open(IDENTITY_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            print(f"✗ 이름 설정 실패: {e}")
            return False

    def to_dict(self) -> dict:
        """ID 정보를 딕셔너리로 반환 (비밀키 제외)"""
        return {
            'npub': self.npub,
            'display_name': self.display_name,
            'created_at': self.created_at
        }


class IndieNetSettings:
    """IndieNet 설정 관리"""

    def __init__(self):
        self.relays: List[str] = DEFAULT_RELAYS.copy()
        self.default_tags: List[str] = [INDIENET_TAG]
        self.auto_refresh: bool = True
        self.refresh_interval: int = 60  # 초
        # 커스텀 보드 (해시태그 기반 비공개 게시판)
        self.boards: List[Dict[str, Any]] = []  # [{"name": "내 보드", "hashtag": "indienetkukjin", "created_at": "..."}]
        self.active_board: Optional[str] = None  # 현재 활성 보드의 hashtag (None이면 기본 IndieNet)

    def load(self) -> bool:
        """설정 로드"""
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.relays = data.get('relays', DEFAULT_RELAYS)
                self.default_tags = data.get('default_tags', [INDIENET_TAG])
                self.auto_refresh = data.get('auto_refresh', True)
                self.refresh_interval = data.get('refresh_interval', 60)
                self.boards = data.get('boards', [])
                self.active_board = data.get('active_board', None)
            return True
        except Exception as e:
            print(f"⚠️  IndieNet: 설정 로드 실패 - {e}")
            return False

    def save(self) -> bool:
        """설정 저장"""
        try:
            INDIENET_DIR.mkdir(parents=True, exist_ok=True)

            data = {
                'relays': self.relays,
                'default_tags': self.default_tags,
                'auto_refresh': self.auto_refresh,
                'refresh_interval': self.refresh_interval,
                'boards': self.boards,
                'active_board': self.active_board
            }

            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            print(f"✗ IndieNet: 설정 저장 실패 - {e}")
            return False

    def to_dict(self) -> dict:
        """설정을 딕셔너리로 반환"""
        return {
            'relays': self.relays,
            'default_tags': self.default_tags,
            'auto_refresh': self.auto_refresh,
            'refresh_interval': self.refresh_interval,
            'boards': self.boards,
            'active_board': self.active_board
        }


class IndieNet:
    """IndieNet 메인 클래스"""

    def __init__(self):
        self.identity = IndieNetIdentity()
        self.settings = IndieNetSettings()
        self._initialized = False

    def initialize(self) -> bool:
        """IndieNet 초기화"""
        if not HAS_NOSTR:
            return False

        # ID 로드/생성
        if not self.identity.load_or_create():
            return False

        # 설정 로드
        self.settings.load()

        # 공개 글 / DM 영구 캐시 초기화
        self._init_post_cache()
        self._init_dm_cache()

        self._initialized = True

        # NIP-17 DM inbox relay 선언(kind:10050)을 백그라운드로 발행/갱신.
        # 이게 있어야 상대 앱이 "이 사람에게 DM 어디로?"를 알고 답장 가능.
        threading.Thread(target=self.publish_dm_relays, daemon=True).start()

        return True

    def is_initialized(self) -> bool:
        """초기화 여부"""
        return self._initialized

    def get_status(self) -> dict:
        """IndieNet 상태 조회"""
        return {
            'initialized': self._initialized,
            'has_nostr': HAS_NOSTR,
            'identity': self.identity.to_dict() if self._initialized else None,
            'settings': self.settings.to_dict() if self._initialized else None
        }

    # ============ 보드 (커스텀 해시태그 게시판) 관리 ============

    def create_board(self, name: str, hashtag: str) -> Dict[str, Any]:
        """
        새 보드 생성 (커스텀 해시태그 게시판)
        Args:
            name: 보드 이름 (표시용)
            hashtag: 해시태그 (필터링 키워드, 공백/특수문자 없이)
        Returns:
            생성된 보드 정보
        """
        # 해시태그 정리 (# 제거, 소문자, 공백 제거)
        hashtag = hashtag.lstrip('#').lower().replace(' ', '')

        # 중복 체크
        for board in self.settings.boards:
            if board['hashtag'] == hashtag:
                raise ValueError(f"이미 존재하는 해시태그입니다: #{hashtag}")

        board = {
            'name': name,
            'hashtag': hashtag,
            'created_at': datetime.now().isoformat()
        }

        self.settings.boards.append(board)
        self.settings.save()

        print(f"✓ IndieNet: 보드 생성 - {name} (#{hashtag})")
        return board

    def delete_board(self, hashtag: str) -> bool:
        """보드 삭제"""
        hashtag = hashtag.lstrip('#').lower()

        for i, board in enumerate(self.settings.boards):
            if board['hashtag'] == hashtag:
                self.settings.boards.pop(i)
                # 활성 보드였다면 해제
                if self.settings.active_board == hashtag:
                    self.settings.active_board = None
                self.settings.save()
                print(f"✓ IndieNet: 보드 삭제 - #{hashtag}")
                return True

        return False

    def get_boards(self) -> List[Dict[str, Any]]:
        """모든 보드 목록 조회"""
        return self.settings.boards

    def set_active_board(self, hashtag: Optional[str]) -> bool:
        """
        활성 보드 설정
        Args:
            hashtag: 보드 해시태그 (None이면 기본 IndieNet으로)
        """
        if hashtag is None:
            self.settings.active_board = None
            self.settings.save()
            print(f"✓ IndieNet: 기본 보드(#IndieNet)로 전환")
            return True

        hashtag = hashtag.lstrip('#').lower()

        # 보드 존재 확인
        for board in self.settings.boards:
            if board['hashtag'] == hashtag:
                self.settings.active_board = hashtag
                self.settings.save()
                print(f"✓ IndieNet: 활성 보드 변경 - #{hashtag}")
                return True

        return False

    def get_active_board(self) -> Optional[Dict[str, Any]]:
        """현재 활성 보드 정보 조회"""
        if self.settings.active_board is None:
            return None

        for board in self.settings.boards:
            if board['hashtag'] == self.settings.active_board:
                return board

        return None

    def post_to_board(self, content: str, hashtag: str = None) -> Optional[str]:
        """
        특정 보드에 글 게시
        Args:
            content: 게시할 내용
            hashtag: 보드 해시태그 (None이면 활성 보드 또는 기본 IndieNet)
        Returns:
            이벤트 ID (성공시) 또는 None
        """
        # 해시태그 결정
        if hashtag:
            target_tag = hashtag.lstrip('#').lower()
        elif self.settings.active_board:
            target_tag = self.settings.active_board
        else:
            target_tag = INDIENET_TAG.lower()

        # 해당 태그로 게시 (기존 post 메서드 활용, default_tags 대신 직접 지정)
        return self._post_with_tag(content, target_tag)

    def _post_with_tag(self, content: str, hashtag: str) -> Optional[str]:
        """특정 해시태그로 글 게시 (내부 메서드)"""
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None

        try:
            # 태그를 해시태그 형식으로 content에 추가
            full_content = f"{content}\n\n#{hashtag}"

            # Nostr 이벤트 생성
            event = Event(
                pubkey=self.identity.public_key.hex(),
                content=full_content,
                kind=EventKind.TEXT_NOTE
            )

            # 't' 태그 추가
            event.tags.append(['t', hashtag.lower()])

            # 서명
            event.sign(self.identity.private_key.hex())

            # 릴레이에 발행
            event_id = self._publish_event(event)

            if event_id:
                print(f"✓ IndieNet: 글 게시 완료 (#{hashtag}) - {event_id[:16]}...")
                # 내 보드 글을 즉시 영구 캐시에 저장 (모든 릴레이가 prune해도 보존)
                try:
                    author_hex = self.identity.public_key.hex()
                    try:
                        author_npub = PublicKey(bytes.fromhex(author_hex)).bech32()
                    except Exception:
                        author_npub = author_hex
                    created_at = int(getattr(event, 'created_at', None) or time.time())
                    self._cache_posts([{
                        'id': event_id,
                        'author': author_npub,
                        'content': full_content,
                        'created_at': created_at,
                        'tags': event.tags,
                    }])
                except Exception as e:
                    print(f"⚠️  IndieNet: 보드 게시 글 캐시 실패 - {e}")

            return event_id

        except Exception as e:
            print(f"✗ IndieNet: 글 게시 실패 - {e}")
            return None

    def fetch_board_posts(self, hashtag: str = None, limit: int = 50, since: int = None) -> List[dict]:
        """
        특정 보드의 게시글 가져오기
        Args:
            hashtag: 보드 해시태그 (None이면 활성 보드 또는 기본 IndieNet)
            limit: 최대 개수
            since: 이 시간 이후 글만 (Unix timestamp)
        Returns:
            게시글 리스트
        """
        if not self._initialized:
            return []

        # 해시태그 결정
        if hashtag:
            target_tag = hashtag.lstrip('#').lower()
        elif self.settings.active_board:
            target_tag = self.settings.active_board
        else:
            target_tag = 'indienet'

        try:
            req_filter = {
                "kinds": [1],
                "#t": [target_tag],
                "limit": limit
            }
            if since:
                req_filter["since"] = since

            def accept(event):
                content = event.get('content', '')
                tags = event.get('tags', [])
                has_tag = any(
                    (len(t) >= 2 and t[0] == 't' and t[1].lower() == target_tag)
                    for t in tags if t
                ) or f'#{target_tag}' in content.lower()
                if not has_tag:
                    return None
                # hex pubkey → npub 변환
                author_hex = event.get('pubkey', '')
                try:
                    author_npub = PublicKey(bytes.fromhex(author_hex)).bech32()
                except Exception:
                    author_npub = author_hex
                return {
                    'id': event.get('id'),
                    'author': author_npub,
                    'content': content,
                    'created_at': event.get('created_at'),
                    'tags': tags
                }

            relay_posts = self._query_relays(req_filter, accept)

            # 릴레이에서 새로 본 글을 영구 캐시에 적재 → prune돼도 보존
            try:
                self._cache_posts(relay_posts)
                # 캐시에서 이 보드 태그 글만 합집합으로 반환
                posts = self._get_cached_posts(limit=limit, since=since, tag=target_tag)
            except Exception as e:
                print(f"⚠️  IndieNet: 보드 글 캐시 접근 실패, 릴레이 결과만 사용 - {e}")
                posts = relay_posts

            # 시간순 정렬 (최신순)
            posts.sort(key=lambda x: x.get('created_at', 0), reverse=True)
            return posts[:limit]

        except Exception as e:
            print(f"✗ IndieNet: 보드 글 조회 실패 - {e}")
            return []

    def post(self, content: str, extra_tags: List[str] = None) -> Optional[str]:
        """
        IndieNet에 글 게시
        Args:
            content: 게시할 내용
            extra_tags: 추가 해시태그 (선택)
        Returns:
            이벤트 ID (성공시) 또는 None
        """
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None

        try:
            # 태그 구성 (#IndieNet 필수 + 추가 태그)
            all_tags = self.settings.default_tags.copy()
            if extra_tags:
                all_tags.extend(extra_tags)

            # 태그를 해시태그 형식으로 content에 추가
            hashtags = ' '.join([f'#{tag}' for tag in all_tags if not tag.startswith('#')])
            full_content = f"{content}\n\n{hashtags}"

            # Nostr 이벤트 생성
            event = Event(
                pubkey=self.identity.public_key.hex(),
                content=full_content,
                kind=EventKind.TEXT_NOTE  # kind 1
            )

            # 't' 태그 추가 (해시태그 표준)
            for tag in all_tags:
                tag_name = tag.lstrip('#')
                event.tags.append(['t', tag_name.lower()])

            # 서명 (pynostr에서는 Event.sign() 사용)
            event.sign(self.identity.private_key.hex())

            # 릴레이에 발행
            event_id = self._publish_event(event)

            if event_id:
                print(f"✓ IndieNet: 글 게시 완료 - {event_id[:16]}...")
                # 내 글을 즉시 영구 캐시에 저장 (모든 릴레이가 prune해도 보존)
                try:
                    author_hex = self.identity.public_key.hex()
                    try:
                        author_npub = PublicKey(bytes.fromhex(author_hex)).bech32()
                    except Exception:
                        author_npub = author_hex
                    created_at = int(getattr(event, 'created_at', None) or time.time())
                    self._cache_posts([{
                        'id': event_id,
                        'author': author_npub,
                        'content': full_content,
                        'created_at': created_at,
                        'tags': event.tags,
                    }])
                except Exception as e:
                    print(f"⚠️  IndieNet: 게시 글 캐시 실패 - {e}")

            return event_id

        except Exception as e:
            print(f"✗ IndieNet: 글 게시 실패 - {e}")
            return None

    def _publish_event(self, event, relays: List[str] = None) -> Optional[str]:
        """이벤트를 릴레이에 발행. event는 Event 객체 또는 이벤트 dict.
        relays 미지정 시 우리 일반 relay 목록, 지정 시 그 목록으로만 발행
        (NIP-17은 수신자의 kind:10050 DM relay로 발행해야 함)."""
        if not relays:
            relays = self.settings.relays if self.settings.relays else DEFAULT_RELAYS
        event_dict = event if isinstance(event, dict) else event.to_dict()
        event_message = json.dumps(["EVENT", event_dict])

        first_event_id = None
        success = threading.Event()
        ok_count = [0]

        def _send_to_relay(relay_url: str):
            nonlocal first_event_id

            relay_success = threading.Event()

            def on_message(ws, message):
                nonlocal first_event_id
                try:
                    data = json.loads(message)
                    if data[0] == "OK":
                        if first_event_id is None:
                            first_event_id = data[1]
                        ok_count[0] += 1
                        relay_success.set()
                        success.set()
                except:
                    pass

            def on_open(ws):
                ws.send(event_message)

            def on_error(ws, error):
                relay_success.set()

            def on_close(ws, close_status_code, close_msg):
                relay_success.set()

            try:
                ws = websocket.WebSocketApp(
                    relay_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                wst = threading.Thread(target=ws.run_forever, daemon=True)
                wst.start()
                relay_success.wait(timeout=5)
                ws.close()
            except Exception as e:
                print(f"  릴레이 전송 실패 ({relay_url}): {e}")

        # 모든 릴레이에 병렬 전송
        threads = []
        for relay_url in relays:
            t = threading.Thread(target=_send_to_relay, args=(relay_url,), daemon=True)
            t.start()
            threads.append(t)

        # 첫 번째 OK 응답 대기 (최대 5초)
        success.wait(timeout=5)

        # 나머지 릴레이도 잠시 대기 (최대 2초 추가)
        for t in threads:
            t.join(timeout=2)

        if ok_count[0] > 0:
            print(f"  릴레이 {ok_count[0]}/{len(relays)}개 발행 성공")

        return first_event_id

    # ============ 공개 글 영구 캐시 (릴레이 prune 대비) ============

    def _init_post_cache(self):
        """공개 글 캐시 DB/테이블 생성. 실패해도 IndieNet은 계속 동작(릴레이 직조회로 폴백)."""
        try:
            POSTS_DB.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(POSTS_DB), timeout=5)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS posts (
                        id         TEXT PRIMARY KEY,
                        author     TEXT,
                        content    TEXT,
                        created_at INTEGER,
                        tags       TEXT,
                        cached_at  INTEGER
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)"
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            print(f"⚠️  IndieNet: 글 캐시 초기화 실패 - {e}")

    def _cache_posts(self, posts: List[dict]):
        """글 리스트를 캐시에 upsert(event id 기준 dedup). 이미 있으면 무시."""
        if not posts:
            return
        try:
            now = int(time.time())
            conn = sqlite3.connect(str(POSTS_DB), timeout=5)
            try:
                conn.executemany(
                    "INSERT OR IGNORE INTO posts (id, author, content, created_at, tags, cached_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            p.get('id'),
                            p.get('author'),
                            p.get('content'),
                            int(p.get('created_at') or 0),
                            json.dumps(p.get('tags', []), ensure_ascii=False),
                            now,
                        )
                        for p in posts if p.get('id')
                    ],
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            print(f"⚠️  IndieNet: 글 캐시 저장 실패 - {e}")

    def _get_cached_posts(self, limit: int = 50, since: int = None, tag: str = None) -> List[dict]:
        """캐시에서 글 조회(최신순). since가 있으면 그 이후만, tag가 있으면 그 해시태그만.

        보드(커스텀 해시태그)와 기본 #indienet 글이 같은 테이블에 섞여 쌓이므로,
        각 피드는 자기 tag로 걸러 읽는다(필터 없으면 전 보드가 한 피드로 새어듦)."""
        clauses, params = [], []
        if since:
            clauses.append("created_at >= ?")
            params.append(int(since))
        if tag:
            t = tag.lstrip('#').lower()
            # t-태그(JSON에 "<tag>") 또는 본문 해시태그(#<tag>) 매칭. SQLite LIKE는 ASCII 대소문자 무시.
            clauses.append("(tags LIKE ? OR content LIKE ?)")
            params.append(f'%"{t}"%')
            params.append(f'%#{t}%')
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        conn = sqlite3.connect(str(POSTS_DB), timeout=5)
        try:
            rows = conn.execute(
                f"SELECT id, author, content, created_at, tags FROM posts "
                f"{where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        finally:
            conn.close()

        result = []
        for r in rows:
            try:
                tags = json.loads(r[4]) if r[4] else []
            except Exception:
                tags = []
            result.append({
                'id': r[0],
                'author': r[1],
                'content': r[2],
                'created_at': r[3],
                'tags': tags,
            })
        return result

    # ============ 수신 DM 영구 캐시 (릴레이 prune 대비) ============

    def _init_dm_cache(self):
        """DM 캐시 DB/테이블 생성. 실패해도 IndieNet은 계속 동작(릴레이 직조회로 폴백)."""
        try:
            DMS_DB.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(DMS_DB), timeout=5)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS dms (
                        id          TEXT PRIMARY KEY,
                        sender      TEXT,
                        content     TEXT,
                        created_at  INTEGER,
                        tags        TEXT,
                        cached_at   INTEGER
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_dms_created ON dms(created_at DESC)"
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            print(f"⚠️  IndieNet: DM 캐시 초기화 실패 - {e}")

    def _cache_dms(self, dms: List[dict]):
        """DM 리스트를 캐시에 upsert(event id 기준 dedup). 복호화된 평문 저장
        (폴러의 기존 _save_message_to_db도 평문 저장이라 노출 수준 동일)."""
        if not dms:
            return
        try:
            now = int(time.time())
            conn = sqlite3.connect(str(DMS_DB), timeout=5)
            try:
                conn.executemany(
                    "INSERT OR IGNORE INTO dms (id, sender, content, created_at, tags, cached_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            m.get('id'),
                            m.get('from'),
                            m.get('content'),
                            int(m.get('created_at') or 0),
                            json.dumps(m.get('tags', []), ensure_ascii=False),
                            now,
                        )
                        for m in dms if m.get('id')
                    ],
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            print(f"⚠️  IndieNet: DM 캐시 저장 실패 - {e}")

    def _get_cached_dms(self, limit: int = 50, since: int = None) -> List[dict]:
        """캐시에서 DM 조회(최신순). since가 있으면 그 이후만. fetch_dms와 동일한 키 형태로 반환."""
        conn = sqlite3.connect(str(DMS_DB), timeout=5)
        try:
            if since:
                rows = conn.execute(
                    "SELECT id, sender, content, created_at, tags FROM dms "
                    "WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
                    (int(since), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, sender, content, created_at, tags FROM dms "
                    "ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        finally:
            conn.close()

        result = []
        for r in rows:
            try:
                tags = json.loads(r[4]) if r[4] else []
            except Exception:
                tags = []
            result.append({
                'id': r[0],
                'from': r[1],
                'content': r[2],
                'created_at': r[3],
                'tags': tags,
            })
        return result

    def _query_relays(self, req_filter: dict, accept, timeout: int = 10,
                      relays: List[str] = None) -> List[dict]:
        """릴레이에 동일 REQ를 병렬 전송하고 이벤트를 수집·dedup한다.

        쓰기(_publish_event)가 전 릴레이에 fan-out 하는 것과 대칭으로, 읽기도
        전 릴레이를 조회한다. 단일 릴레이(relays[0])만 읽으면 그 릴레이가 prune한
        글은 다른 릴레이에 살아있어도 보이지 않는다.

        Args:
            req_filter: Nostr REQ 필터 (kinds/#t/#p/limit/since 등)
            accept: (event_dict) -> item_dict | None. None이면 제외.
            timeout: 릴레이별 EOSE 대기 최대 시간(초)
            relays: 조회할 relay 목록. 미지정 시 우리 일반 relay (NIP-17 수신은 DM relay 지정).
        Returns:
            event id 기준 dedup된 item 리스트
        """
        if not relays:
            relays = self.settings.relays if self.settings.relays else DEFAULT_RELAYS
        collected: Dict[str, dict] = {}
        lock = threading.Lock()

        def _query_one(relay_url: str):
            done = threading.Event()

            def on_open(ws):
                req_id = f"q_{uuid.uuid4().hex[:8]}"
                ws.send(json.dumps(["REQ", req_id, req_filter]))

            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    if data[0] == "EVENT":
                        event = data[2]
                        item = accept(event)
                        if item is not None:
                            eid = event.get('id')
                            with lock:
                                if eid not in collected:
                                    collected[eid] = item
                    elif data[0] == "EOSE":
                        done.set()
                except:
                    pass

            def on_error(ws, error):
                done.set()

            def on_close(ws, close_status_code, close_msg):
                done.set()

            try:
                ws = websocket.WebSocketApp(
                    relay_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                wst = threading.Thread(target=ws.run_forever, daemon=True)
                wst.start()
                done.wait(timeout=timeout)
                ws.close()
            except Exception as e:
                print(f"  릴레이 조회 실패 ({relay_url}): {e}")

        threads = []
        for relay_url in relays:
            t = threading.Thread(target=_query_one, args=(relay_url,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=timeout + 2)

        return list(collected.values())

    def fetch_posts(self, limit: int = 50, since: int = None) -> List[dict]:
        """
        IndieNet 기본 #indienet 피드 조회 (전 릴레이 조회 + 영구 캐시 합집합).

        #indienet은 사실상 '기본 보드'이므로 fetch_board_posts('indienet')에 위임한다.
        같은 캐시 테이블에 보드 글이 섞여 쌓이지만, 태그 필터로 #indienet 글만 반환된다.
        """
        return self.fetch_board_posts(hashtag='indienet', limit=limit, since=since)

    def get_user_info(self, pubkey: str) -> Optional[dict]:
        """
        사용자 프로필 정보 조회
        Args:
            pubkey: 공개키 (hex 또는 npub)
        Returns:
            사용자 정보 딕셔너리
        """
        if not self._initialized:
            return None

        try:
            # npub를 hex로 변환
            if pubkey.startswith('npub'):
                pubkey_hex = PublicKey.from_npub(pubkey).hex()
            else:
                pubkey_hex = pubkey

            user_info = None
            connected = threading.Event()
            done = threading.Event()

            def on_message(ws, message):
                nonlocal user_info
                try:
                    data = json.loads(message)
                    if data[0] == "EVENT":
                        event = data[2]
                        if event.get('kind') == 0:  # Metadata
                            content = json.loads(event.get('content', '{}'))
                            user_info = {
                                'pubkey': event.get('pubkey'),
                                'name': content.get('name', ''),
                                'display_name': content.get('display_name', ''),
                                'about': content.get('about', ''),
                                'picture': content.get('picture', ''),
                                'nip05': content.get('nip05', '')
                            }
                    elif data[0] == "EOSE":
                        done.set()
                except:
                    pass

            def on_open(ws):
                connected.set()
                req_filter = {
                    "kinds": [0],  # Metadata
                    "authors": [pubkey_hex],
                    "limit": 1
                }
                req_id = f"profile_{uuid.uuid4().hex[:8]}"
                ws.send(json.dumps(["REQ", req_id, req_filter]))

            def on_error(ws, error):
                done.set()

            def on_close(ws, close_status_code, close_msg):
                done.set()

            relay_url = self.settings.relays[0] if self.settings.relays else DEFAULT_RELAYS[0]

            ws = websocket.WebSocketApp(
                relay_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            wst = threading.Thread(target=ws.run_forever, daemon=True)
            wst.start()

            connected.wait(timeout=5)
            done.wait(timeout=5)
            ws.close()

            return user_info

        except Exception as e:
            print(f"✗ IndieNet: 사용자 조회 실패 - {e}")
            return None

    def fetch_dms(self, limit: int = 50, since: int = None) -> List[dict]:
        """
        받은 DM 가져오기 (channels/nostr.py 참조)
        Args:
            limit: 최대 개수
            since: 이 시간 이후 메시지만 (Unix timestamp)
        Returns:
            DM 리스트
        """
        if not self._initialized:
            return []

        try:
            my_hex = self.identity.public_key.hex()
            req_filter = {
                "kinds": [4],  # DM
                "#p": [my_hex],  # 나에게 온 것만
                "limit": limit
            }
            if since:
                req_filter["since"] = since

            def accept(event):
                if event.get('kind') != 4:
                    return None
                # #p 태그 확인 - 나에게 온 DM인가?
                is_for_me = any(
                    len(tag) >= 2 and tag[0] == 'p' and tag[1] == my_hex
                    for tag in event.get('tags', [])
                )
                if not is_for_me:
                    return None
                # 복호화
                try:
                    decrypted = self.identity.private_key.decrypt_message(
                        event.get('content', ''),
                        event.get('pubkey', '')
                    )
                except Exception as e:
                    print(f"⚠️  DM 복호화 실패: {e}")
                    return None
                return {
                    'id': event.get('id'),
                    'from': event.get('pubkey'),
                    'content': decrypted,
                    'created_at': event.get('created_at'),
                    'tags': event.get('tags', [])
                }

            relay_dms = self._query_relays(req_filter, accept)  # NIP-04 (kind:4)
            nip17_dms = self.fetch_dms_nip17(limit=limit, since=since)  # NIP-17 (kind:1059)
            all_relay_dms = relay_dms + nip17_dms

            # 릴레이에서 새로 본 DM을 영구 캐시에 적재 → 이후 prune돼도 보존
            try:
                self._cache_dms(all_relay_dms)
                # 캐시(릴레이 ∪ 과거 보존분)에서 합집합으로 반환
                dms = self._get_cached_dms(limit=limit, since=since)
            except Exception as e:
                print(f"⚠️  IndieNet: DM 캐시 접근 실패, 릴레이 결과만 사용 - {e}")
                dms = all_relay_dms

            # 시간순 정렬 (최신순)
            dms.sort(key=lambda x: x.get('created_at', 0), reverse=True)

            print(f"✓ IndieNet: {len(dms)}개 DM 수신 (NIP-04 {len(relay_dms)} + NIP-17 {len(nip17_dms)} + 캐시)")
            return dms[:limit]

        except Exception as e:
            print(f"✗ IndieNet: DM 조회 실패 - {e}")
            return []

    def _to_hex(self, pubkey: str) -> str:
        """npub/hex → hex."""
        return PublicKey.from_npub(pubkey).hex() if pubkey.startswith("npub") else pubkey

    def fetch_dm_relays(self, pubkey: str) -> List[str]:
        """수신자의 NIP-17 DM inbox relay 목록(kind:10050) 조회.
        없으면 일반 relay 목록(kind:10002)도 시도, 그래도 없으면 우리 relay로 폴백."""
        to_hex = self._to_hex(pubkey)

        def _extract_relays(event):
            urls = []
            for t in event.get("tags", []):
                if t and t[0] == "relay" and len(t) >= 2:
                    urls.append(t[1].rstrip("/"))
            return urls if urls else None

        # kind:10050 (DM 전용 relay)
        got = self._query_relays({"kinds": [10050], "authors": [to_hex], "limit": 1}, _extract_relays)
        for item in got:
            if item:
                return item
        # 폴백: kind:10002 (NIP-65 일반 relay)
        def _extract_nip65(event):
            urls = [t[1].rstrip("/") for t in event.get("tags", []) if t and t[0] == "r" and len(t) >= 2]
            return urls if urls else None
        got = self._query_relays({"kinds": [10002], "authors": [to_hex], "limit": 1}, _extract_nip65)
        for item in got:
            if item:
                return item
        # 최종 폴백: 우리 일반 relay
        return list(self.settings.relays)

    def _self_dm_relays(self) -> List[str]:
        """우리가 NIP-17 DM을 수신할 relay (kind:10050으로 선언한 것과 일치)."""
        return ["wss://nos.lol", "wss://relay.damus.io"]

    def fetch_dms_nip17(self, limit: int = 50, since: int = None) -> List[dict]:
        """NIP-17 수신 DM 조회. 우리 DM relay에서 kind:1059(#p=우리) 구독 → unwrap.

        주의: gift-wrap의 created_at은 과거로 무작위화되므로 relay 필터에 since를 쓰지 않고,
        언랩 후 내부 rumor의 실제 시각으로 거른다.
        """
        if not self._initialized:
            return []
        try:
            import nip17
            my_hex = self.identity.public_key.hex()
            my_priv = self.identity.private_key.hex()

            def accept(event):
                try:
                    out = nip17.unwrap_dm(my_priv, event)
                except Exception:
                    return None  # 우리 대상 아님/복호 실패 → 스킵
                ca = out.get("created_at") or event.get("created_at") or 0
                if since and ca < since:
                    return None
                return {
                    "id": (out.get("rumor") or {}).get("id") or event.get("id"),
                    "from": out["sender"],
                    "content": out["content"],
                    "created_at": ca,
                    "tags": [],
                }

            return self._query_relays(
                {"kinds": [1059], "#p": [my_hex], "limit": limit},
                accept, relays=self._self_dm_relays(),
            )
        except Exception as e:
            print(f"✗ NIP-17 DM 수신 실패 - {e}")
            return []

    def publish_dm_relays(self, dm_relays: List[str] = None) -> Optional[str]:
        """우리(IndieNet 신원)의 NIP-17 DM inbox relay 선언(kind:10050) 발행.
        이게 없으면 상대 앱이 '이 사람에게 DM 어디로 보내지?'를 몰라 'DM inbox relays not found' 표시.
        여기 적힌 relay로 남들이 우리에게 gift-wrap을 보내고, 우리는 그걸 구독해 받는다."""
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None
        if not dm_relays:
            # 무인증 쓰기 가능한 신뢰 relay (우리가 수신 구독할 곳)
            dm_relays = ["wss://nos.lol", "wss://relay.damus.io"]
        try:
            event = Event(
                content="",
                pubkey=self.identity.public_key.hex(),
                kind=10050,
                tags=[["relay", url] for url in dm_relays],
            )
            event.sign(self.identity.private_key.hex())
            event_id = self._publish_event(event)
            if event_id:
                print(f"✓ DM inbox relay(kind:10050) 발행: {dm_relays}")
            return event_id
        except Exception as e:
            print(f"✗ DM inbox relay 발행 실패 - {e}")
            return None

    def send_dm_nip17(self, to_pubkey: str, content: str) -> Optional[str]:
        """NIP-17 비공개 DM 발송. 수신자의 kind:10050 DM relay로 gift-wrap(kind1059) 발행.
        최신 클라이언트(Damus/Amethyst/0xchat)가 읽는 표준 방식."""
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None
        try:
            import nip17
            to_hex = self._to_hex(to_pubkey)
            dm_relays = self.fetch_dm_relays(to_hex)
            print(f"✓ NIP-17 DM: to={to_hex[:16]}... relays={dm_relays}")

            gift_wrap = nip17.wrap_dm(self.identity.private_key.hex(), to_hex, content)
            event_id = self._publish_event(gift_wrap, relays=dm_relays)

            if event_id:
                print(f"✓ NIP-17 DM 발송 완료 - gift_wrap_id={event_id[:16]}...")
            else:
                print("✗ NIP-17 DM 발송 실패 (relay OK 응답 없음)")
            return event_id
        except Exception as e:
            print(f"✗ NIP-17 DM 발송 실패 - {e}")
            return None

    def send_dm(self, to_pubkey: str, content: str) -> Optional[str]:
        """
        DM 전송 (channels/nostr.py 참조)
        Args:
            to_pubkey: 수신자 공개키 (hex 또는 npub)
            content: 메시지 내용
        Returns:
            이벤트 ID (성공시) 또는 None
        """
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None

        try:
            # npub를 hex로 변환
            if to_pubkey.startswith('npub'):
                to_hex = PublicKey.from_npub(to_pubkey).hex()
            else:
                to_hex = to_pubkey

            print(f"✓ IndieNet DM 전송: to={to_hex[:16]}...")

            # 암호화
            encrypted_content = self.identity.private_key.encrypt_message(content, to_hex)

            # DM 이벤트 생성 (kind 4)
            event = Event(
                pubkey=self.identity.public_key.hex(),
                content=encrypted_content,
                kind=EventKind.ENCRYPTED_DIRECT_MESSAGE  # kind 4
            )
            event.tags.append(['p', to_hex])

            # 서명
            event.sign(self.identity.private_key.hex())

            # 발행
            event_id = self._publish_event(event)

            if event_id:
                print(f"✓ IndieNet: DM 전송 완료 - {event_id[:16]}...")

            return event_id

        except Exception as e:
            print(f"✗ IndieNet: DM 전송 실패 - {e}")
            return None


# 싱글톤 인스턴스
_indienet_instance: Optional[IndieNet] = None


def get_indienet() -> IndieNet:
    """IndieNet 싱글톤 인스턴스 반환"""
    global _indienet_instance
    if _indienet_instance is None:
        _indienet_instance = IndieNet()
        _indienet_instance.initialize()
    return _indienet_instance
