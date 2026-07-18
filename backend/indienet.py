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

# 공통 기반(HAS_NOSTR·_ON_PHONE·경로·릴레이 상수·pynostr 타입)은 indienet_common,
# 게시/릴레이/소셜 계층은 indienet_publish/relay/social 믹스인으로 이동
# (2026-07-18 모듈화 — 1500줄 규칙). 재수출로 기존 import 경로 불변.
from indienet_common import (  # noqa: E402,F401
    HAS_NOSTR, _ON_PHONE,
    INDIENET_DIR, IDENTITY_FILE, SETTINGS_FILE, CACHE_DIR, POSTS_DB, DMS_DB,
    DEFAULT_RELAYS, INDIENET_TAG,
    Event, EventKind, PrivateKey, PublicKey,
)
from indienet_publish import IndieNetPublishMixin  # noqa: E402
from indienet_relay import IndieNetRelayMixin  # noqa: E402
from indienet_social import IndieNetSocialMixin  # noqa: E402
if HAS_NOSTR:
    import websocket  # noqa: F401,E402 (기존 모듈 네임스페이스 보존)


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
        # 팔로우 목록 (로컬 저장). [{"pubkey": npub_or_hex, "name": "표시이름", "added_at": "..."}]
        # 지금은 로컬 settings에만 둔다. 나중에 이 목록을 kind:3(NIP-02)으로 발행하면
        # 다른 Nostr 클라이언트와 공유되는 포터블 소셜 그래프로 승격 가능(마이그레이션 1회).
        self.follows: List[Dict[str, Any]] = []

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
                self.follows = data.get('follows', [])
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
                'active_board': self.active_board,
                'follows': self.follows
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
            'active_board': self.active_board,
            'follows': self.follows
        }


class IndieNet(IndieNetPublishMixin, IndieNetRelayMixin, IndieNetSocialMixin):
    """IndieNet 메인 클래스"""

    def __init__(self):
        self.identity = IndieNetIdentity()
        self.settings = IndieNetSettings()
        self._initialized = False

    def initialize(self) -> bool:
        """IndieNet 초기화"""
        if _ON_PHONE:
            return self._initialize_phone()
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

    def _initialize_phone(self) -> bool:
        """폰: pynostr 대신 Kotlin 브리지로 초기화.

        피드 읽기는 신원 불필요(공개 글). 신원(서명·DM용 priv/pub)은 best-effort 로
        폰 SharedPreferences 키에서 채우되, 실패해도 _initialized 는 세워 읽기는 살린다.
        """
        try:
            INDIENET_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            import nostr_phone_bridge as bridge
            self.identity.public_key_hex = bridge.pub_hex()
            self.identity.private_key_hex = bridge.priv_hex()
            self.identity.npub = self.identity.public_key_hex  # bech32 표시 변환은 후속
            print(f"✓ IndieNet(phone): 신원 로드 pub={self.identity.public_key_hex[:12]}...")
        except Exception as e:
            print(f"⚠️  IndieNet(phone): 신원 보류(읽기는 가능) - {e}")
        try:
            self.settings.load()
            self._init_post_cache()
            self._init_dm_cache()
        except Exception as e:
            print(f"⚠️  IndieNet(phone): 캐시/설정 - {e}")
        self._initialized = True
        print("✓ IndieNet(phone): Kotlin 브리지 초기화 완료")
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


# 싱글톤 인스턴스
_indienet_instance: Optional[IndieNet] = None


def get_indienet() -> IndieNet:
    """IndieNet 싱글톤 인스턴스 반환"""
    global _indienet_instance
    if _indienet_instance is None:
        _indienet_instance = IndieNet()
        _indienet_instance.initialize()
    return _indienet_instance
