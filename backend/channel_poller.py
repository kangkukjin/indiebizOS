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
GMAIL_PATH = BACKEND_PATH.parent / "data" / "packages" / "installed" / "extensions" / "gmail"
NOSTR_KEYS_PATH = BACKEND_PATH / "data" / "nostr_keys"
sys.path.insert(0, str(GMAIL_PATH))

# Nostr 라이브러리 확인
try:
    from pynostr.key import PrivateKey
    from pynostr.event import EventKind
    import websocket
    HAS_NOSTR = True
except ImportError:
    HAS_NOSTR = False


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
        self._nostr_ws = None
        self._nostr_seen_ids = set()

        # 비즈니스 매니저 참조
        self._business_manager = None

        # 자동응답 서비스 참조
        self._auto_response = None

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

        # 자동응답 서비스 시작
        try:
            auto_response = self._get_auto_response()
            auto_response.start()
        except Exception as e:
            self._log(f"자동응답 서비스 시작 실패: {e}")

    def stop(self):
        """폴러 중지"""
        self.running = False

        # 자동응답 서비스 중지
        if self._auto_response:
            try:
                self._auto_response.stop()
            except:
                pass

        # Nostr WebSocket 종료
        if self._nostr_ws:
            try:
                self._nostr_ws.close()
            except:
                pass

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

        # Nostr WebSocket 종료
        if channel_type == 'nostr' and self._nostr_ws:
            try:
                self._nostr_ws.close()
            except:
                pass
            self._nostr_ws = None

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
        """Nostr 실시간 WebSocket 루프"""
        if not HAS_NOSTR:
            self._log("Nostr 라이브러리 없음 (pip install pynostr websocket-client)")
            return

        while not stop_event.is_set() and self.running:
            try:
                # 키 초기화
                if not self._init_nostr_keys():
                    self._log("Nostr 키 초기화 실패 - 60초 후 재시도")
                    time.sleep(60)
                    continue

                # 릴레이 설정 가져오기
                bm = self._get_business_manager()
                channel = bm.get_channel_setting('nostr')
                if not channel or channel['enabled'] != 1:
                    time.sleep(10)
                    continue

                config = json.loads(channel.get('config', '{}'))
                relays = config.get('relays', ['wss://relay.damus.io'])
                relay_url = relays[0] if relays else 'wss://relay.damus.io'

                # WebSocket 연결
                self._connect_nostr_websocket(relay_url, stop_event)

            except Exception as e:
                self._log(f"Nostr 오류: {e}")

            # 재연결 대기 (로그 없이 조용히)
            if not stop_event.is_set() and self.running:
                time.sleep(5)

    def _init_nostr_keys(self) -> bool:
        """Nostr 키 초기화 - DB config에서 nsec 로드 또는 IndieNet 연동 또는 새로 생성"""
        if self._nostr_private_key:
            return True

        try:
            bm = self._get_business_manager()
            channel = bm.get_channel_setting('nostr')
            if not channel:
                self._log("Nostr 채널 설정 없음")
                return False

            config = json.loads(channel.get('config', '{}'))
            nsec = config.get('nsec', '')
            private_key_hex = config.get('private_key_hex', '')

            if nsec:
                # nsec 형식으로 저장된 경우
                if nsec.startswith('nsec'):
                    self._nostr_private_key = PrivateKey.from_nsec(nsec)
                else:
                    # hex 형식으로 저장된 경우
                    self._nostr_private_key = PrivateKey(bytes.fromhex(nsec))
                self._log(f"Nostr 키 로드: {self._nostr_private_key.public_key.bech32()[:20]}...")
            elif private_key_hex:
                # 이전 버전 호환
                self._nostr_private_key = PrivateKey(bytes.fromhex(private_key_hex))
                self._log(f"Nostr 키 로드 (hex): {self._nostr_private_key.public_key.bech32()[:20]}...")
            else:
                # IndieNet identity.json에서 키 가져오기 시도
                indienet_identity = Path.home() / '.indiebiz' / 'indienet' / 'identity.json'
                if indienet_identity.exists():
                    try:
                        with open(indienet_identity, 'r') as f:
                            identity_data = json.load(f)
                        indienet_nsec = identity_data.get('nsec', '')
                        if indienet_nsec and indienet_nsec.startswith('nsec'):
                            self._nostr_private_key = PrivateKey.from_nsec(indienet_nsec)
                            self._log(f"IndieNet 키 연동: {self._nostr_private_key.public_key.bech32()[:20]}...")
                        elif identity_data.get('private_key_hex'):
                            self._nostr_private_key = PrivateKey(bytes.fromhex(identity_data['private_key_hex']))
                            self._log(f"IndieNet 키 연동 (hex): {self._nostr_private_key.public_key.bech32()[:20]}...")
                    except Exception as e:
                        self._log(f"IndieNet 키 로드 실패: {e}")

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
        """Nostr WebSocket 연결"""
        import uuid

        connected = threading.Event()

        def on_message(ws, message):
            try:
                data = json.loads(message)
                if data[0] == "EVENT":
                    event = data[2]
                    if event.get('kind') == 4:  # DM
                        self._handle_nostr_dm(event)
            except Exception as e:
                pass

        def on_error(ws, error):
            # 정상적인 연결 끊김은 로그 안 남김
            error_str = str(error)
            if "Connection to remote host was lost" not in error_str:
                self._log(f"Nostr WebSocket 에러: {error}")

        def on_close(ws, close_status_code, close_msg):
            pass  # 정상적인 닫힘은 로그 안 남김

        def on_open(ws):
            connected.set()
            # 나에게 온 DM 구독
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
            # 최초 연결 시에만 로그
            if not hasattr(self, '_nostr_connected_once'):
                self._log(f"Nostr 연결됨: {relay_url}")
                self._nostr_connected_once = True
            self._update_last_poll_time('nostr')

        self._nostr_ws = websocket.WebSocketApp(
            relay_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )

        # 별도 스레드에서 WebSocket 실행
        ws_thread = threading.Thread(target=self._nostr_ws.run_forever, daemon=True)
        ws_thread.start()

        # 연결 대기
        connected.wait(timeout=10)

        # stop_event가 설정될 때까지 대기
        while not stop_event.is_set() and self.running:
            if not ws_thread.is_alive():
                break
            time.sleep(1)

        # 종료
        if self._nostr_ws:
            self._nostr_ws.close()

    def _handle_nostr_dm(self, event: dict):
        """Nostr DM 처리 → DB 저장"""
        try:
            event_id = event.get('id')

            # 중복 체크
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

            sender_pubkey = event.get('pubkey', '')
            sender_short = sender_pubkey[:16] + '...' if len(sender_pubkey) > 16 else sender_pubkey

            self._log(f"Nostr DM 수신: from={sender_short}")

            # DB에 저장 (Gmail과 동일한 방식)
            self._save_message_to_db(
                contact_type='nostr',
                contact_value=sender_pubkey,
                subject='Nostr DM',
                content=decrypted,
                external_id=event_id,
                message_time=dt.isoformat()
            )

            self._update_last_poll_time('nostr')

        except Exception as e:
            self._log(f"Nostr DM 처리 실패: {e}")

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

            # 읽지 않은 모든 메시지 가져오기
            query = 'is:unread'
            messages = self._gmail_client.get_messages(query=query, max_results=10)

            if not messages:
                return

            self._log(f"Gmail: {len(messages)}개 새 메시지 발견")

            for msg in messages:
                if msg is None:
                    continue

                # DB에 저장
                self._save_message_to_db(
                    contact_type='gmail',
                    contact_value=self._extract_email(msg.get('from', '')),
                    subject=msg.get('subject', ''),
                    content=msg.get('body', msg.get('snippet', '')),
                    external_id=msg.get('id', ''),
                    message_time=msg.get('date')
                )

                # 읽음 처리
                if msg.get('id'):
                    try:
                        self._gmail_client.mark_as_read(msg['id'])
                    except Exception as e:
                        self._log(f"Gmail 읽음 처리 실패: {e}")

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

    def _save_message_to_db(self, contact_type: str, contact_value: str,
                           subject: str, content: str, external_id: str = None,
                           message_time: str = None):
        """메시지를 DB에 저장 (Gmail/Nostr 공통)"""
        try:
            bm = self._get_business_manager()

            # 중복 체크 (external_id가 있으면)
            if external_id:
                existing = bm.get_message_by_external_id(external_id)
                if existing:
                    return  # 이미 저장됨

            # 연락처로 이웃 찾기
            neighbor = bm.find_neighbor_by_contact(contact_type, contact_value)
            neighbor_id = neighbor['id'] if neighbor else None

            # 이웃이 없으면 자동 생성
            if neighbor_id is None:
                # 이름 추출
                if contact_type == 'gmail':
                    name = contact_value.split('@')[0] if '@' in contact_value else contact_value
                elif contact_type == 'nostr':
                    name = contact_value[:16] + '...' if len(contact_value) > 16 else contact_value
                else:
                    name = contact_value

                neighbor = bm.create_neighbor(name=name, info_level=0)
                neighbor_id = neighbor['id']

                # 연락처 추가
                bm.add_contact(neighbor_id, contact_type, contact_value)
                self._log(f"새 이웃 생성: {name}")

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
