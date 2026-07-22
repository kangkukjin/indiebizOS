"""
channel_poller.py - 통신채널 메시지 수신 모듈
IndieBiz OS Core

각 통신채널에서 메시지를 수신하여 DB에 저장합니다.
- Gmail: 주기적 폴링
- Nostr: 실시간 WebSocket
"""

import os
import sys
import json
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional
import re

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_base_path as _get_base_path
GMAIL_PATH = _get_base_path() / "data" / "packages" / "installed" / "extensions" / "gmail"
NOSTR_KEYS_PATH = BACKEND_PATH / "data" / "nostr_keys"
sys.path.insert(0, str(GMAIL_PATH))

# Nostr 라이브러리 확인
try:
    from pynostr.key import PrivateKey, PublicKey
    from pynostr.event import EventKind
    import websocket
    HAS_NOSTR = True
except ImportError:
    HAS_NOSTR = False


def _hex_to_npub(hex_pubkey: str) -> str:
    """hex 공개키를 npub(bech32) 형식으로 변환. 실패 시 원본 반환."""
    if not hex_pubkey or hex_pubkey.startswith('npub'):
        return hex_pubkey
    try:
        return PublicKey(bytes.fromhex(hex_pubkey)).bech32()
    except Exception:
        return hex_pubkey


def _npub_to_hex(npub: str) -> str:
    """npub(bech32)를 hex로 변환. 실패 시 원본 반환."""
    if not npub or not npub.startswith('npub'):
        return npub
    try:
        return PublicKey.from_npub(npub).hex().lower()
    except Exception:
        return npub


def _load_owner_identities() -> Dict[str, set]:
    """환경변수에서 사용자 식별 정보 로드"""
    from dotenv import load_dotenv
    load_dotenv(_get_base_path() / ".env")

    identities = {
        'emails': set(),
        'nostr_pubkeys': set()
    }

    # 이메일 로드 (쉼표 구분)
    owner_emails = os.getenv('OWNER_EMAILS', '')
    if owner_emails:
        for email in owner_emails.split(','):
            email = email.strip().lower()
            if email:
                identities['emails'].add(email)

    # 시스템 AI 발신 주소는 owner로 등록하지 않음 — 자기 응답이 다시 명령으로 처리되는 루프 방지

    # Nostr 공개키 로드 (쉼표 구분, hex와 npub 양쪽 모두 저장)
    owner_nostr = os.getenv('OWNER_NOSTR_PUBKEYS', '')
    if owner_nostr:
        for pubkey in owner_nostr.split(','):
            pubkey = pubkey.strip()
            if not pubkey:
                continue
            if pubkey.startswith('npub'):
                hex_key = _npub_to_hex(pubkey)
                identities['nostr_pubkeys'].add(hex_key.lower())
                identities['nostr_pubkeys'].add(pubkey.lower())
            else:
                identities['nostr_pubkeys'].add(pubkey.lower())
                npub_key = _hex_to_npub(pubkey)
                identities['nostr_pubkeys'].add(npub_key.lower())

    return identities


class ChannelPoller:
    """통신채널 메시지 수신 관리자"""

    def __init__(self, log_callback: Callable[[str], None] = None):
        self.log_callback = log_callback or print
        self.running = False
        self.threads: Dict[str, threading.Thread] = {}
        self.stop_events: Dict[str, threading.Event] = {}

        # Gmail 클라이언트 캐시
        self._gmail_client = None

        # Nostr 관련
        self._nostr_private_key = None
        self._nostr_public_key = None
        self._nostr_wss = []  # 활성 WebSocket 목록(릴레이별 1개) — stop/토글오프 시 전체 close
        self._nostr_seen_ids = set()
        self._nostr_seen_lock = threading.Lock()  # 멀티릴레이 동시 수신 시 dedupe 체크-추가 원자화

        # 비즈니스 매니저 참조
        self._business_manager = None

        # 자동응답 서비스 참조
        self._auto_response = None

        # 사용자 식별 정보
        self._owner_identities = _load_owner_identities()

        # 처리된 소유자 메시지 external_id 캐시 (business DB 미저장으로 인한 재처리 방지)
        self._processed_owner_ids: set = set()

        # 발화한 채널 트리거 (trigger_id:msg) 캐시 — 같은 메시지 재발화 방지
        self._fired_channel_triggers: set = set()

    def _is_from_owner(self, contact_type: str, contact_value: str) -> bool:
        """메시지가 소유자(사용자)로부터 왔는지 확인"""
        contact_value = contact_value.lower().strip()

        if contact_type == 'email':
            # 이메일에서 주소만 추출
            email_match = re.search(r'<([^>]+)>', contact_value)
            if email_match:
                contact_value = email_match.group(1).lower()
            return contact_value in self._owner_identities['emails']

        elif contact_type == 'nostr':
            return contact_value in self._owner_identities['nostr_pubkeys']

        return False

    def _log(self, message: str):
        """로그 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_message = f"[채널폴러 {timestamp}] {message}"
        self.log_callback(full_message)

    def _get_business_manager(self):
        """비즈니스 매니저 가져오기 (지연 로딩)"""
        if self._business_manager is None:
            from business_manager import BusinessManager
            self._business_manager = BusinessManager()
        return self._business_manager

    def _get_auto_response(self):
        """자동응답 서비스 가져오기 (지연 로딩)"""
        if self._auto_response is None:
            from auto_response import get_auto_response_service
            self._auto_response = get_auto_response_service(self._log)
        return self._auto_response

    def start(self):
        """폴러 시작 - 활성화된 채널들의 수신 시작"""
        if self.running:
            return

        self.running = True
        self._log("채널 폴러 시작됨")

        # 활성화된 채널 확인 및 수신 시작
        self._refresh_channels()

        # pending 메시지 발송 스레드 시작
        self._start_pending_message_sender()

        # 자동응답 서비스 시작 — 단, 사용자가 영속적으로 꺼뒀으면(is_enabled=False) 부팅 시 자동 시작 안 함.
        try:
            auto_response = self._get_auto_response()
            if auto_response.is_enabled():
                auto_response.start()
            else:
                self._log("자동응답은 사용자 설정으로 꺼져 있음(부팅 자동 시작 생략)")
        except Exception as e:
            self._log(f"자동응답 서비스 시작 실패: {e}")

    def stop(self):
        """폴러 중지"""
        self.running = False

        # pending 메시지 발송 스레드 중지
        if 'pending_sender' in self.stop_events:
            self.stop_events['pending_sender'].set()

        # 자동응답 서비스 중지
        if self._auto_response:
            try:
                self._auto_response.stop()
            except Exception as e:
                self._log(f"자동응답 서비스 중지 실패: {e}")

        # Nostr WebSocket 종료 (릴레이별 전체)
        for ws in list(self._nostr_wss):
            try:
                ws.close()
            except Exception as e:
                self._log(f"Nostr WebSocket 종료 실패: {e}")

        # 모든 채널 폴링 중지
        for channel_type in list(self.stop_events.keys()):
            self._stop_channel(channel_type)

        self._log("채널 폴러 중지됨")

    def _refresh_channels(self):
        """채널 설정 새로고침 및 수신 상태 동기화"""
        try:
            bm = self._get_business_manager()
            channels = bm.get_all_channel_settings()

            for channel in channels:
                channel_type = channel['channel_type']
                enabled = channel['enabled'] == 1

                if enabled and channel_type not in self.threads:
                    # 활성화되었는데 수신 안 하고 있으면 시작
                    self._start_channel(channel_type, channel['polling_interval'])
                elif not enabled and channel_type in self.threads:
                    # 비활성화되었는데 수신 중이면 중지
                    self._stop_channel(channel_type)

        except Exception as e:
            self._log(f"채널 새로고침 실패: {e}")

    def _start_channel(self, channel_type: str, interval: int):
        """특정 채널의 수신 시작"""
        if channel_type in self.threads:
            return

        stop_event = threading.Event()
        self.stop_events[channel_type] = stop_event

        if channel_type == 'nostr':
            # Nostr은 실시간 WebSocket
            thread = threading.Thread(
                target=self._nostr_realtime_loop,
                args=(stop_event,),
                daemon=True
            )
            self._log("Nostr 실시간 리스닝 시작")
        else:
            # Gmail 등은 폴링
            thread = threading.Thread(
                target=self._polling_loop,
                args=(channel_type, interval, stop_event),
                daemon=True
            )
            self._log(f"{channel_type} 폴링 시작 (주기: {interval}초)")

        self.threads[channel_type] = thread
        thread.start()

    def _stop_channel(self, channel_type: str):
        """특정 채널의 수신 중지"""
        if channel_type in self.stop_events:
            self.stop_events[channel_type].set()
            del self.stop_events[channel_type]

        # Nostr WebSocket 종료 (릴레이별 전체)
        if channel_type == 'nostr':
            for ws in list(self._nostr_wss):
                try:
                    ws.close()
                except Exception as e:
                    self._log(f"Nostr WebSocket 종료 실패: {e}")
            self._nostr_wss = []

        if channel_type in self.threads:
            self.threads[channel_type].join(timeout=2)
            del self.threads[channel_type]

        self._log(f"{channel_type} 수신 중지됨")

    def _polling_loop(self, channel_type: str, interval: int, stop_event: threading.Event):
        """채널 폴링 루프 (Gmail 등)"""
        while not stop_event.is_set() and self.running:
            try:
                if channel_type == 'gmail':
                    self._poll_gmail()

                # 마지막 폴링 시간 업데이트
                self._update_last_poll_time(channel_type)

            except Exception as e:
                self._log(f"{channel_type} 폴링 오류: {e}")

            # 주기 대기 (1초 단위로 체크하여 빠른 종료 가능)
            for _ in range(interval):
                if stop_event.is_set() or not self.running:
                    break
                time.sleep(1)

    # ============ Nostr 실시간 리스닝 ============

    def _nostr_realtime_loop(self, stop_event: threading.Event):
        """Nostr 실시간 WebSocket 루프 — 설정된 모든 릴레이를 동시 구독.

        과거엔 relays[0] 한 곳만 실시간 구독해서, 우리 kind:10050 DM inbox 가 여러 릴레이면
        다른 릴레이로만 온 gift-wrap(NIP-17) 이 실시간 누락 → 자동응답 미트리거였다(주기 fetch 는
        dms.db 만 채움). 이제 릴레이마다 독립 리스너를 띄운다. 같은 이벤트가 여러 릴레이서 중복
        수신돼도 _nostr_seen_ids 락 + external_id DB dedup 으로 자동응답은 1회만 트리거된다.
        """
        if not HAS_NOSTR:
            self._log("Nostr 라이브러리 없음 (pip install pynostr websocket-client)")
            return

        # NIP-17 백필 가드 기준 시각(리스닝 시작 시점). 재연결돼도 리셋 안 함 —
        # 이 시각 이전(다운타임 포함) 메시지는 자동응답 대량 발송을 막기 위해 business.db 미저장.
        if not getattr(self, '_nostr_listen_started', None):
            self._nostr_listen_started = int(time.time())

        # 키·릴레이 목록 확보 (활성화·키 준비될 때까지 대기)
        relays = None
        while not stop_event.is_set() and self.running:
            try:
                if not self._init_nostr_keys():
                    self._log("Nostr 키 초기화 실패 - 60초 후 재시도")
                    time.sleep(60)
                    continue
                bm = self._get_business_manager()
                channel = bm.get_channel_setting('nostr')
                if not channel or channel['enabled'] != 1:
                    time.sleep(10)
                    continue
                config = json.loads(channel.get('config', '{}'))
                relays = config.get('relays') or ['wss://relay.damus.io']
                break
            except Exception as e:
                self._log(f"Nostr 오류: {e}")
                time.sleep(5)

        if not relays or stop_event.is_set() or not self.running:
            return

        # 릴레이별 독립 리스너 스레드 (각자 연결·재연결 관리)
        for relay_url in relays:
            threading.Thread(
                target=self._nostr_relay_listener,
                args=(relay_url, stop_event),
                daemon=True
            ).start()
        self._log(f"Nostr 실시간 구독: {len(relays)}개 릴레이")

        # stop_event 까지 대기 (리스너 스레드들이 각자 재연결 관리)
        while not stop_event.is_set() and self.running:
            time.sleep(1)

    def _nostr_relay_listener(self, relay_url: str, stop_event: threading.Event):
        """단일 릴레이 연결 + 재연결 루프 (릴레이마다 독립 스레드)."""
        while not stop_event.is_set() and self.running:
            try:
                self._connect_nostr_websocket(relay_url, stop_event)
            except Exception as e:
                self._log(f"Nostr 릴레이 오류({relay_url}): {e}")
            # 재연결 대기 (로그 없이 조용히)
            if not stop_event.is_set() and self.running:
                time.sleep(5)

    def _init_nostr_keys(self) -> bool:
        """Nostr 키 초기화 - IndieNet identity를 항상 우선 사용"""
        if self._nostr_private_key:
            return True

        try:
            bm = self._get_business_manager()
            channel = bm.get_channel_setting('nostr')
            if not channel:
                self._log("Nostr 채널 설정 없음")
                return False

            config = json.loads(channel.get('config', '{}'))

            # IndieNet identity 우선 사용 (시스템 전체 단일 Nostr 주소)
            indienet_identity = Path.home() / '.indiebiz' / 'indienet' / 'identity.json'
            if indienet_identity.exists():
                try:
                    with open(indienet_identity, 'r') as f:
                        identity_data = json.load(f)
                    indienet_nsec = identity_data.get('nsec', '')
                    if indienet_nsec and indienet_nsec.startswith('nsec'):
                        self._nostr_private_key = PrivateKey.from_nsec(indienet_nsec)
                        self._log(f"IndieNet 키 사용: {self._nostr_private_key.public_key.bech32()[:20]}...")
                    elif identity_data.get('private_key_hex'):
                        self._nostr_private_key = PrivateKey(bytes.fromhex(identity_data['private_key_hex']))
                        self._log(f"IndieNet 키 사용 (hex): {self._nostr_private_key.public_key.bech32()[:20]}...")
                except Exception as e:
                    self._log(f"IndieNet 키 로드 실패: {e}")

            # IndieNet 키가 없으면 DB config에서 fallback
            if self._nostr_private_key is None:
                nsec = config.get('nsec', '')
                private_key_hex = config.get('private_key_hex', '')

                if nsec:
                    if nsec.startswith('nsec'):
                        self._nostr_private_key = PrivateKey.from_nsec(nsec)
                    else:
                        self._nostr_private_key = PrivateKey(bytes.fromhex(nsec))
                    self._log(f"Nostr 키 로드 (DB): {self._nostr_private_key.public_key.bech32()[:20]}...")
                elif private_key_hex:
                    self._nostr_private_key = PrivateKey(bytes.fromhex(private_key_hex))
                    self._log(f"Nostr 키 로드 (hex): {self._nostr_private_key.public_key.bech32()[:20]}...")

            # 여전히 키가 없으면 새로 생성
            if self._nostr_private_key is None:
                self._nostr_private_key = PrivateKey()
                self._log(f"Nostr 새 키 생성: {self._nostr_private_key.public_key.bech32()}")

            self._nostr_public_key = self._nostr_private_key.public_key

            # config에 npub과 nsec 저장 (UI에서 표시용)
            config['npub'] = self._nostr_public_key.bech32()
            config['nsec'] = self._nostr_private_key.bech32()
            config['private_key_hex'] = self._nostr_private_key.hex()

            # 기본 릴레이 설정
            if 'relays' not in config or not config['relays']:
                config['relays'] = [
                    'wss://relay.damus.io',
                    'wss://nos.lol',
                    'wss://relay.primal.net'
                ]

            bm.update_channel_setting('nostr', config=json.dumps(config))
            return True

        except Exception as e:
            self._log(f"Nostr 키 초기화 실패: {e}")
            return False

    def _connect_nostr_websocket(self, relay_url: str, stop_event: threading.Event):
        """Nostr WebSocket 연결 (단일 릴레이). 멀티릴레이 동시 연결을 위해 ws·last_active 는 연결별 로컬."""
        import uuid

        connected = threading.Event()
        last_active = [time.time()]  # 연결별 하이버네이션 감지용 (closure-local)
        HIBERNATION_THRESHOLD = 30  # 30초 이상 점프하면 하이버네이션으로 판단
        PING_INTERVAL = 20  # 20초마다 ping

        def on_message(ws, message):
            try:
                data = json.loads(message)
                if data[0] == "EVENT":
                    event = data[2]
                    if event.get('kind') == 4:  # NIP-04 DM (레거시)
                        self._handle_nostr_dm(event)
                    elif event.get('kind') == 1059:  # NIP-17 gift-wrap DM (최신 클라이언트)
                        self._handle_nostr_giftwrap(event)
            except Exception as e:
                pass

        def on_error(ws, error):
            # 정상적인 연결 끊김은 로그 안 남김
            error_str = str(error)
            if "Connection to remote host was lost" not in error_str:
                self._log(f"Nostr WebSocket 에러({relay_url}): {error}")

        def on_close(ws, close_status_code, close_msg):
            pass  # 정상적인 닫힘은 로그 안 남김

        def on_open(ws):
            connected.set()
            # 나에게 온 NIP-04 DM 구독 (현재 시점부터)
            req = json.dumps([
                "REQ",
                f"dm_{uuid.uuid4().hex[:8]}",
                {
                    "kinds": [4],
                    "#p": [self._nostr_public_key.hex()],
                    "since": int(time.time())
                }
            ])
            ws.send(req)
            # 나에게 온 NIP-17 gift-wrap(kind:1059) 구독.
            # gift-wrap created_at 은 과거로 무작위화되므로 since 를 못 쓴다 →
            # limit 로 받고, 언랩 후 rumor 실제 시각으로 freshness 판단(_handle_nostr_giftwrap).
            req17 = json.dumps([
                "REQ",
                f"gw_{uuid.uuid4().hex[:8]}",
                {
                    "kinds": [1059],
                    "#p": [self._nostr_public_key.hex()],
                    "limit": 50
                }
            ])
            ws.send(req17)
            last_active[0] = time.time()
            # 최초 연결 시에만 로그
            if not hasattr(self, '_nostr_connected_once'):
                self._log(f"Nostr 연결됨: {relay_url}")
                self._nostr_connected_once = True
            self._update_last_poll_time('nostr')

        ws = websocket.WebSocketApp(
            relay_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        self._nostr_wss.append(ws)  # stop/토글오프 시 전체 close 대상

        # 별도 스레드에서 WebSocket 실행 (ping으로 좀비 연결 감지)
        ws_thread = threading.Thread(
            target=ws.run_forever,
            kwargs={"ping_interval": PING_INTERVAL, "ping_timeout": 10},
            daemon=True
        )
        ws_thread.start()

        # 연결 대기
        connected.wait(timeout=10)

        # stop_event가 설정될 때까지 대기 + 하이버네이션 감지
        try:
            while not stop_event.is_set() and self.running:
                if not ws_thread.is_alive():
                    break

                # 하이버네이션 감지: 시간 점프 체크
                now = time.time()
                elapsed = now - last_active[0]
                if elapsed > HIBERNATION_THRESHOLD:
                    self._log(f"하이버네이션 감지 ({int(elapsed)}초 경과) - Nostr 재연결({relay_url})")
                    break  # while 탈출 → ws.close() → 릴레이 리스너에서 재연결

                last_active[0] = now
                time.sleep(1)
        finally:
            # 종료 — 로컬 ws 닫고 활성 목록에서 제거
            try:
                ws.close()
            except Exception:
                pass
            try:
                self._nostr_wss.remove(ws)
            except ValueError:
                pass

    def _handle_nostr_dm(self, event: dict):
        """Nostr DM 처리 → DB 저장"""
        try:
            event_id = event.get('id')

            # 중복 체크 (멀티릴레이 동시 수신 — 체크-추가 원자화)
            with self._nostr_seen_lock:
                if event_id in self._nostr_seen_ids:
                    return
                self._nostr_seen_ids.add(event_id)

            # 나에게 온 DM인지 확인
            is_for_me = False
            for tag in event.get('tags', []):
                if len(tag) >= 2 and tag[0] == 'p' and tag[1] == self._nostr_public_key.hex():
                    is_for_me = True
                    break

            if not is_for_me:
                return

            # 복호화
            try:
                decrypted = self._nostr_private_key.decrypt_message(
                    event.get('content', ''),
                    event.get('pubkey', '')
                )
            except Exception as e:
                self._log(f"Nostr DM 복호화 실패: {e}")
                return

            # 시간 변환
            timestamp = event.get('created_at', 0)
            kst = timezone(timedelta(hours=9))
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(kst)

            sender_hex = event.get('pubkey', '')
            sender_npub = _hex_to_npub(sender_hex)
            sender_short = sender_npub[:20] + '...' if len(sender_npub) > 20 else sender_npub

            self._log(f"Nostr DM 수신: from={sender_short}")

            # DB에 저장 (npub 형식으로 통일)
            self._save_message_to_db(
                contact_type='nostr',
                contact_value=sender_npub,
                subject='Nostr DM',
                content=decrypted,
                external_id=event_id,
                message_time=dt.isoformat()
            )

            self._update_last_poll_time('nostr')

        except Exception as e:
            self._log(f"Nostr DM 처리 실패: {e}")

    def _handle_nostr_giftwrap(self, event: dict):
        """NIP-17 gift-wrap(kind:1059) DM 처리 → unwrap → business.db (자동응답 입력).

        kind:4(NIP-04)와 동일하게 _save_message_to_db 로 흘려보낸다(이웃 매칭·소유자 분기·미응답
        저장 모두 거기서 처리). 차이: ①gift-wrap unwrap(nip17) ②freshness 가드 — 리스닝 시작 이전
        rumor 는 스킵(릴레이가 과거 gift-wrap 을 한꺼번에 내려줄 때 옛 DM 에 대량 자동응답 방지).
        """
        try:
            event_id = event.get('id')
            # 중복 체크 (멀티릴레이 동시 수신 — 체크-추가 원자화)
            with self._nostr_seen_lock:
                if not event_id or event_id in self._nostr_seen_ids:
                    return
                self._nostr_seen_ids.add(event_id)

            try:
                import nip17
                out = nip17.unwrap_dm(self._nostr_private_key.hex(), event)
            except Exception:
                return  # 우리 대상 아님 / 복호·검증 실패 → 스킵

            content = (out or {}).get('content')
            if not content:
                return

            # 백필 가드: 리스닝 시작 이전(여유 120초) 메시지는 자동응답 트리거 안 함(이미 dms.db 에 있음).
            rumor_ca = out.get('created_at') or 0
            started = getattr(self, '_nostr_listen_started', 0)
            if rumor_ca and started and rumor_ca < started - 120:
                return

            sender_npub = _hex_to_npub(out.get('sender', ''))
            rumor_id = (out.get('rumor') or {}).get('id') or event_id  # dms.db 와 dedupe 정합
            ts = rumor_ca or int(time.time())
            kst = timezone(timedelta(hours=9))
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(kst)

            # indiebizOS peer 표식: rumor 태그에 indiebiz 마커가 있으면 발신 이웃을 peer 로 마킹.
            peer_version = None
            for _t in ((out.get('rumor') or {}).get('tags') or []):
                if isinstance(_t, list) and _t and _t[0] == nip17.INDIEBIZ_TAG:
                    peer_version = _t[1] if len(_t) > 1 else nip17.INDIEBIZ_PROTOCOL
                    break

            self._log(f"Nostr DM(NIP-17) 수신: from={sender_npub[:20]}...")
            self._save_message_to_db(
                contact_type='nostr',
                contact_value=sender_npub,
                subject='Nostr DM',
                content=content,
                external_id=rumor_id,
                message_time=dt.isoformat(),
                peer_version=peer_version,
            )
            self._update_last_poll_time('nostr')

        except Exception as e:
            self._log(f"Nostr NIP-17 DM 처리 실패: {e}")

    # ============ Gmail 폴링 ============

    def _poll_gmail(self):
        """Gmail 폴링"""
        try:
            bm = self._get_business_manager()
            channel = bm.get_channel_setting('gmail')

            if not channel or channel['enabled'] != 1:
                return

            # Gmail 클라이언트 초기화
            if self._gmail_client is None:
                self._init_gmail_client()

            if self._gmail_client is None:
                return

            # 읽지 않은 메시지 중 자신이 보낸 것 제외 (응답 루프 방지)
            query = 'is:unread -from:me'
            messages = self._gmail_client.get_messages(query=query, max_results=10)

            if not messages:
                return

            self._log(f"Gmail: {len(messages)}개 새 메시지 발견")

            for msg in messages:
                if msg is None:
                    continue

                # 처리 전 즉시 읽음 처리 — 처리가 수십 초 걸려도 다음 폴링 주기에서 재선택 방지
                if msg.get('id'):
                    try:
                        self._gmail_client.mark_as_read(msg['id'])
                    except Exception as e:
                        self._log(f"Gmail 읽음 처리 실패: {e}")

                # DB 저장 / 시스템 AI 처리
                self._save_message_to_db(
                    contact_type='email',
                    contact_value=self._extract_email(msg.get('from', '')),
                    subject=msg.get('subject', ''),
                    content=msg.get('body', msg.get('snippet', '')),
                    external_id=msg.get('id', ''),
                    message_time=msg.get('date')
                )

        except Exception as e:
            self._log(f"Gmail 폴링 실패: {e}")

    def _init_gmail_client(self):
        """Gmail 클라이언트 초기화"""
        try:
            from gmail import GmailClient

            # Gmail 확장의 config.yaml에서 설정 로드
            config_path = GMAIL_PATH / "config.yaml"

            if not config_path.exists():
                self._log("Gmail config.yaml 없음 - 폴링 건너뜀")
                return

            import yaml
            with open(config_path) as f:
                config = yaml.safe_load(f)

            gmail_config = config.get('gmail', {})
            if not gmail_config.get('client_id') or not gmail_config.get('client_secret'):
                self._log("Gmail OAuth 설정 없음 - 폴링 건너뜀")
                return

            # config.yaml의 email 사용 (유일한 출처)
            if not gmail_config.get('email'):
                self._log("Gmail 이메일 주소 없음 - 폴링 건너뜀")
                return

            self._gmail_client = GmailClient(gmail_config)
            self._gmail_client.authenticate()
            self._log("Gmail 클라이언트 초기화 완료")

        except Exception as e:
            self._log(f"Gmail 클라이언트 초기화 실패: {e}")
            self._gmail_client = None

    # ============ 공통 메서드 ============

    def _update_last_poll_time(self, channel_type: str):
        """마지막 수신 시간 업데이트"""
        try:
            bm = self._get_business_manager()
            bm.update_channel_last_poll(channel_type)
        except Exception as e:
            self._log(f"수신 시간 업데이트 실패: {e}")

    def _check_channel_triggers(self, contact_type: str, contact_value: str,
                                subject: str, content: str, external_id: str = None):
        """수신 메시지를 type:channel 트리거 규칙과 대조 → 일치 시 파이프라인 발화.

        event_triggers.json 의 enabled 채널 트리거를 읽어 config 로 필터:
          - channel: gmail | nostr (비우면 모든 채널)
          - from: 발신자 부분일치 필터 (옵션)
          - keyword: 제목+본문 부분일치 필터 (옵션)
        schedule 트리거가 calendar_manager 폴링으로 발화하듯, 채널 트리거는 이 수신 훅으로 발화.
        메시지 텍스트는 파이프라인 첫 step 의 _prev_result 로 주입(자동 데이터 전달)."""
        try:
            from trigger_engine import _load_triggers
        except Exception:
            return  # trigger_engine 미가용 — graceful (폰 등)
        try:
            triggers = [t for t in (_load_triggers().get("triggers") or [])
                        if t.get("type") == "channel" and t.get("enabled", True)]
        except Exception as e:
            self._log(f"채널 트리거 로드 실패: {e}")
            return
        if not triggers:
            return

        haystack = f"{subject or ''} {content or ''}".lower()
        cval = (contact_value or "").lower()
        for t in triggers:
            cfg = t.get("config") or {}
            want_ch = (cfg.get("channel") or "").strip().lower()
            if want_ch and want_ch != contact_type:
                continue
            want_from = (cfg.get("from") or "").strip().lower()
            if want_from and want_from not in cval:
                continue
            kw = (cfg.get("keyword") or "").strip().lower()
            if kw and kw not in haystack:
                continue
            # 같은 메시지로 같은 트리거 재발화 방지 (external_id 우선, 없으면 본문 일부)
            fire_key = f"{t.get('id')}:{external_id or haystack[:48]}"
            if fire_key in self._fired_channel_triggers:
                continue
            self._fired_channel_triggers.add(fire_key)
            self._fire_channel_pipeline(t, contact_type, contact_value, subject, content)

    def _fire_channel_pipeline(self, trigger: dict, contact_type: str,
                               contact_value: str, subject: str, content: str):
        """채널 트리거 파이프라인을 데몬 스레드에서 실행 (폴링 루프 블로킹 방지).
        calendar_actions._action_run_pipeline 의 '소유자 없는 레거시 직접실행' 경로와 동형."""
        pipeline = trigger.get("pipeline", "")
        if not pipeline:
            self._log(f"채널 트리거 '{trigger.get('name')}' pipeline 누락 — 발화 생략")
            return

        def _run():
            try:
                from ibl_parser import parse as ibl_parse, IBLSyntaxError
                from workflow_engine import execute_pipeline
                try:
                    steps = ibl_parse(pipeline)
                except IBLSyntaxError as e:
                    self._log(f"채널 트리거 IBL 문법 오류: {e}")
                    return
                msg_ctx = f"[{contact_type}] {contact_value}: {subject or ''} {content or ''}".strip()
                self._log(f"채널 트리거 발화: {trigger.get('name')} ← {contact_type} 메시지")
                result = execute_pipeline(steps, ".", context={"_prev_result": msg_ctx},
                                          agent_id="system_ai")
                try:
                    from trigger_engine import _add_history
                    _add_history(trigger.get("id"), trigger.get("name", ""), True, str(result)[:200])
                except Exception:
                    pass
            except Exception as e:
                self._log(f"채널 트리거 실행 실패: {e}")
                try:
                    from trigger_engine import _add_history
                    _add_history(trigger.get("id"), trigger.get("name", ""), False, str(e)[:200])
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True,
                         name=f"chtrig-{str(trigger.get('id'))[:8]}").start()

    def _save_message_to_db(self, contact_type: str, contact_value: str,
                           subject: str, content: str, external_id: str = None,
                           message_time: str = None, peer_version: str = None):
        """메시지를 DB에 저장 (Gmail/Nostr 공통).

        peer_version 이 있으면(발신 rumor 에 indiebiz 태그) 해당 이웃을 indiebizOS peer 로 마킹."""
        try:
            bm = self._get_business_manager()

            # 중복 체크 (external_id가 있으면)
            if external_id:
                existing = bm.get_message_by_external_id(external_id)
                if existing:
                    return  # 이미 저장됨

            # 채널 트리거 대조 (수신 메시지 전부 — 소유자/외부 무관). "Y 메시지 오면 X 실행"
            # = self:trigger{type:channel}. 저장/자동응답과 독립적인 push 발화 경로.
            self._check_channel_triggers(contact_type, contact_value, subject, content, external_id)

            # 사용자(소유자) 여부 확인
            is_owner = self._is_from_owner(contact_type, contact_value)

            if is_owner:
                # 소유자 메시지 중복 처리 방지 (business DB 미저장이므로 메모리 캐시 사용)
                if external_id:
                    if external_id in self._processed_owner_ids:
                        return
                    self._processed_owner_ids.add(external_id)

                # 사용자 명령 → 시스템 AI로 처리
                self._log(f"사용자 명령 감지: {subject[:30]}...")
                self._process_owner_command(contact_type, contact_value, subject, content)
                return  # business DB에는 저장하지 않음

            # 외부인 메시지 → 기존대로 DB 저장
            # 연락처로 이웃 찾기
            neighbor = bm.find_neighbor_by_contact(contact_type, contact_value)
            neighbor_id = neighbor['id'] if neighbor else None

            # 이웃이 없으면 자동 생성
            if neighbor_id is None:
                # 이름 추출
                if contact_type == 'email':
                    name = contact_value.split('@')[0] if '@' in contact_value else contact_value
                elif contact_type == 'nostr':
                    name = contact_value[:20] + '...' if len(contact_value) > 20 else contact_value
                else:
                    name = contact_value

                neighbor = bm.create_neighbor(name=name, info_level=0)
                neighbor_id = neighbor['id']

                # 연락처 추가
                bm.add_contact(neighbor_id, contact_type, contact_value)
                self._log(f"새 이웃 생성: {name}")

            # indiebizOS peer 표식 (발신 rumor 에 indiebiz 태그 감지 시) — 멱등
            if peer_version and neighbor_id:
                try:
                    bm.mark_neighbor_peer(neighbor_id, peer_version)
                except Exception as _e:
                    self._log(f"peer 마킹 실패: {_e}")

            # 메시지 저장
            bm.create_message(
                content=content,
                contact_type=contact_type,
                contact_value=contact_value,
                subject=subject,
                neighbor_id=neighbor_id,
                is_from_user=0,  # 수신 메시지
                external_id=external_id,
                message_time=message_time
            )

            self._log(f"메시지 저장: {subject[:30]}..." if len(subject) > 30 else f"메시지 저장: {subject}")

        except Exception as e:
            self._log(f"메시지 저장 실패: {e}")

    def _process_owner_command(self, contact_type: str, contact_value: str,
                               subject: str, content: str):
        """사용자 명령을 시스템 AI로 처리 (GUI와 동일하게)"""
        try:
            from system_ai_memory import save_conversation, get_history_for_ai

            # 메시지 내용 (본문이 비어있으면 제목 사용)
            message_content = content or subject
            if not message_content:
                self._log("빈 명령 무시")
                return

            # 사용자 메시지를 system_ai_memory.db에 저장 (GUI와 동일)
            source = f"user@{contact_type}"
            save_conversation("user", message_content, source=source)

            # 최근 대화 히스토리 로드 (조회 + 역할 매핑 + Observation Masking 통합)
            history = get_history_for_ai(limit=10)

            # 시스템 AI 설정 로드 (모델 기어 'system_ai' 역할로 해소 — 실행처와 일치)
            config = self._load_system_ai_config()
            no_key = {"claude_code", "claude-code", "claudecode", "ollama"}
            if not config.get('model') or (
                not config.get('apiKey') and config.get('provider', '').lower() not in no_key):
                self._log("시스템 AI 모델/키 없음")
                return

            # AI 처리
            response = self._execute_system_ai(message_content, history, config)

            if response:
                # AI 응답도 system_ai_memory.db에 저장 (GUI와 동일)
                save_conversation("assistant", response, source=f"system_ai@{contact_type}")

                # 오류 응답은 외부 채널로 전송하지 않음 (수신 루프 방지)
                if response.startswith("명령 처리 중 오류"):
                    self._log(f"오류 응답 - 외부 전송 생략 (루프 방지): {response[:60]}")
                else:
                    self._send_response(contact_type, contact_value, f"Re: {subject}", response)

            self._log(f"사용자 명령 처리 완료: {subject[:30]}...")

        except Exception as e:
            self._log(f"사용자 명령 처리 실패: {e}")
            import traceback
            traceback.print_exc()

    def _load_system_ai_config(self) -> dict:
        """시스템 AI 설정 — 모델 기어 'system_ai' 역할(실행 축)로 해소(get_system_ai_runner 와 일치).
        게이트 판정용. 리졸버 실패 시 옛 system_ai_config 직접 로드로 폴백."""
        try:
            from model_resolver import resolve
            d = resolve("system_ai")
            if d.get("model"):
                return {"enabled": True, "provider": d.get("provider", ""),
                        "model": d["model"], "apiKey": d.get("api_key", "")}
        except Exception:
            pass
        config_path = _get_base_path() / "data" / "system_ai_config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"enabled": False, "provider": "", "model": "", "apiKey": ""}

    def _execute_system_ai(self, command: str, history: list, config: dict) -> str:
        """시스템 AI로 명령 실행 - 실제 시스템 AI 호출 (모든 도구 포함)"""
        try:
            import uuid
            from api_system_ai import process_system_ai_message
            from thread_context import set_current_task_id, clear_current_task_id, clear_called_agent
            from system_ai_memory import create_task as create_system_ai_task, complete_task as complete_system_ai_task

            # 태스크 ID 생성 (GUI와 동일하게 - call_project_agent 등 위임 도구에 필요)
            task_id = f"task_sysai_{uuid.uuid4().hex[:8]}"
            create_system_ai_task(
                task_id=task_id,
                requester="user@channel",
                requester_channel="channel",
                original_request=command,
                delegated_to="system_ai"
            )
            set_current_task_id(task_id)
            clear_called_agent()

            # 히스토리 형식 변환
            formatted_history = []
            if history:
                for h in history:
                    role = h.get("role", "user")
                    if role not in ["user", "assistant"]:
                        role = "user"
                    formatted_history.append({
                        "role": role,
                        "content": h.get("content", "")
                    })

            # 실제 시스템 AI 호출 (모든 도구 포함)
            response_text, _tool_images = process_system_ai_message(
                message=command,
                history=formatted_history,
                images=None
            )

            # 태스크 완료 처리
            complete_system_ai_task(task_id, response_text[:500] if response_text else "")
            clear_current_task_id()
            clear_called_agent()

            return response_text

        except Exception as e:
            self._log(f"시스템 AI 실행 오류: {e}")
            import traceback
            traceback.print_exc()
            # 태스크 정리
            try:
                clear_current_task_id()
                clear_called_agent()
            except:
                pass
            return f"명령 처리 중 오류: {e}"

    def _send_response(self, contact_type: str, contact_value: str, subject: str, body: str):
        """외부 채널로 응답 전송"""
        try:
            if contact_type == 'email' and self._gmail_client:
                self._gmail_client.send_message(
                    to=contact_value,
                    subject=subject,
                    body=body
                )
                self._log(f"Gmail 응답 전송: {contact_value}")

            elif contact_type == 'nostr' and self._nostr_private_key:
                # Nostr DM 전송 로직 (기존 코드 재사용)
                self._send_nostr_dm(contact_value, body)
                self._log(f"Nostr 응답 전송: {contact_value[:16]}...")

        except Exception as e:
            self._log(f"응답 전송 실패: {e}")

    def _send_nostr_dm(self, recipient_pubkey: str, message: str):
        """Nostr DM 전송 - IndieNet의 다중 릴레이 발행 사용"""
        try:
            from indienet import get_indienet
            indienet = get_indienet()

            if indienet._initialized:
                event_id = indienet.send_dm_nip17(to_pubkey=recipient_pubkey, content=message)
                if event_id:
                    self._log(f"Nostr DM 발행 완료 (IndieNet): {event_id[:16]}...")
                else:
                    self._log("Nostr DM 발행 실패 (IndieNet)")
            else:
                self._log("IndieNet 미초기화 - Nostr DM 전송 불가")

        except Exception as e:
            self._log(f"Nostr DM 전송 실패: {e}")

    # ============ Pending 메시지 발송 ============

    def _start_pending_message_sender(self):
        """pending 메시지 발송 스레드 시작"""
        if 'pending_sender' in self.threads:
            return

        stop_event = threading.Event()
        self.stop_events['pending_sender'] = stop_event

        thread = threading.Thread(
            target=self._pending_message_loop,
            args=(stop_event,),
            daemon=True
        )
        self.threads['pending_sender'] = thread
        thread.start()
        self._log("pending 메시지 발송 스레드 시작 (주기: 10초)")

    def _pending_message_loop(self, stop_event: threading.Event):
        """pending 메시지 폴링 루프"""
        while not stop_event.is_set() and self.running:
            try:
                self._poll_pending_messages()
            except Exception as e:
                self._log(f"pending 메시지 폴링 오류: {e}")

            # 10초 대기 (1초 단위로 체크하여 빠른 종료 가능)
            for _ in range(10):
                if stop_event.is_set() or not self.running:
                    break
                time.sleep(1)

    def _poll_pending_messages(self):
        """pending 상태의 발신 메시지를 조회하여 발송"""
        try:
            bm = self._get_business_manager()

            # pending 상태이고 is_from_user=1인 메시지 조회
            pending_messages = bm.get_messages(status='pending')

            if not pending_messages:
                return

            # is_from_user=1 (발신 메시지)만 필터링
            outgoing_messages = [
                msg for msg in pending_messages
                if msg.get('is_from_user') == 1
            ]

            if not outgoing_messages:
                return

            self._log(f"발송 대기 메시지 {len(outgoing_messages)}개 발견")

            for msg in outgoing_messages:
                try:
                    self._process_pending_message(msg)
                except Exception as e:
                    self._log(f"pending 메시지 처리 실패 (ID: {msg.get('id')}): {e}")
                    # 실패한 메시지는 failed 상태로 업데이트
                    try:
                        bm.update_message_status(msg['id'], 'failed', str(e))
                    except:
                        pass

        except Exception as e:
            self._log(f"pending 메시지 조회 실패: {e}")

    def _process_pending_message(self, msg: dict):
        """개별 pending 메시지 발송 처리"""
        bm = self._get_business_manager()

        msg_id = msg.get('id')
        contact_type = msg.get('contact_type', 'email')
        contact_value = msg.get('contact_value', '')
        subject = msg.get('subject', '')
        content = msg.get('content', '')
        attachment_path = msg.get('attachment_path')

        if not contact_value:
            self._log(f"연락처 없음, 메시지 건너뜀 (ID: {msg_id})")
            bm.update_message_status(msg_id, 'failed', '연락처 없음')
            return

        self._log(f"메시지 발송 시작: {contact_type} → {contact_value[:30]}...")

        try:
            if contact_type == 'email':
                self._send_gmail_message(contact_value, subject, content, attachment_path)
            elif contact_type == 'nostr':
                self._send_nostr_dm(contact_value, content)
            else:
                raise Exception(f"지원하지 않는 연락처 타입: {contact_type}")

            # 발송 성공 → sent 상태로 업데이트
            bm.update_message_status(msg_id, 'sent')
            self._log(f"메시지 발송 완료: {contact_value[:30]}...")

        except Exception as e:
            # 발송 실패 → failed 상태로 업데이트
            bm.update_message_status(msg_id, 'failed', str(e))
            self._log(f"메시지 발송 실패: {e}")
            raise

    def _send_gmail_message(self, to: str, subject: str, body: str, attachment_path: str = None):
        """Gmail로 메시지 발송"""
        # Gmail 클라이언트 초기화
        if self._gmail_client is None:
            self._init_gmail_client()

        if self._gmail_client is None:
            raise Exception("Gmail 클라이언트 초기화 실패")

        # 이메일 발송 (send_message 메서드 사용)
        if attachment_path:
            self._gmail_client.send_message(
                to=to,
                subject=subject,
                body=body,
                attachment_path=attachment_path
            )
        else:
            self._gmail_client.send_message(
                to=to,
                subject=subject,
                body=body
            )

    def _extract_email(self, from_str: str) -> str:
        """From 헤더에서 이메일 주소 추출"""
        match = re.search(r'<([^>]+)>', from_str)
        if match:
            return match.group(1)
        if '@' in from_str:
            return from_str.strip()
        return from_str

    def refresh_channel(self, channel_type: str):
        """특정 채널의 설정 새로고침"""
        try:
            bm = self._get_business_manager()
            channel = bm.get_channel_setting(channel_type)

            if not channel:
                return

            enabled = channel['enabled'] == 1
            interval = channel['polling_interval']

            # Nostr의 경우 키가 변경되었을 수 있으니 리셋
            if channel_type == 'nostr':
                self._nostr_private_key = None
                self._nostr_public_key = None

            # 수신 상태 동기화
            if enabled and channel_type not in self.threads:
                self._start_channel(channel_type, interval)
            elif not enabled and channel_type in self.threads:
                self._stop_channel(channel_type)
            elif enabled and channel_type in self.threads:
                # 설정 변경되었을 수 있으니 재시작
                self._stop_channel(channel_type)
                self._start_channel(channel_type, interval)

        except Exception as e:
            self._log(f"채널 새로고침 실패: {e}")

    def poll_now(self, channel_type: str) -> dict:
        """즉시 폴링/수신 실행"""
        try:
            if channel_type == 'gmail':
                self._poll_gmail()
            elif channel_type == 'nostr':
                # Nostr은 실시간이므로 상태만 확인
                if 'nostr' in self.threads:
                    return {"status": "success", "channel": channel_type, "message": "실시간 리스닝 중"}
                else:
                    return {"status": "error", "message": "Nostr 리스닝이 활성화되지 않음"}

            self._update_last_poll_time(channel_type)
            return {"status": "success", "channel": channel_type}

        except Exception as e:
            return {"status": "error", "message": str(e)}


# 싱글톤 인스턴스
_poller_instance: Optional[ChannelPoller] = None


def get_channel_poller(log_callback: Callable[[str], None] = None) -> ChannelPoller:
    """채널 폴러 인스턴스 반환"""
    global _poller_instance
    if _poller_instance is None:
        _poller_instance = ChannelPoller(log_callback)
    return _poller_instance
