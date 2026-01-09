"""
Nostr 채널 - 웹소켓 기반 Nostr 프로토콜 구현
"""

import os
import time
import json
import threading
from .base import Channel

try:
    from pynostr.key import PrivateKey
    from pynostr.event import Event, EventKind
    from pynostr.relay_manager import RelayManager
    from pynostr.message_type import ClientMessageType
    from pynostr.filters import FiltersList, Filters
    import websocket
    HAS_NOSTR = True
except ImportError as e:
    HAS_NOSTR = False
    print(f"⚠️  pynostr가 설치되지 않음: pip install pynostr websocket-client")


class NostrChannel(Channel):
    """Nostr 프로토콜 채널"""
    
    def __init__(self, config):
        super().__init__(config)
        self.relay_manager = None
        self.private_key = None
        self.public_key = None
        
        # 설정
        self.key_name = config.get('key_name', 'default')
        self.relays = config.get('relays', [
            'wss://relay.damus.io',
            'wss://relay.nostr.band',
            'wss://nos.lol'
        ])
        
        # seen_event_ids 파일 경로
        self.seen_file = f"tokens/nostr_keys/{self.key_name}_seen.txt"
        self.timestamp_file = f"tokens/nostr_keys/{self.key_name}_timestamp.txt"
        
        # seen_event_ids 로드 (영구 저장)
        self.seen_event_ids = self._load_seen_events()
        
        # last_poll_timestamp 로드 (영구 저장)
        self.last_poll_timestamp = self._load_last_timestamp()
        
        # 실시간 리스닝 관련
        self.callback = None
        self.listening_thread = None
        self.listening = False
        
        # WebSocket 연결 유지
        self.ws = None
        self.ws_thread = None
        self.ws_connected = threading.Event()
    
    def _load_seen_events(self) -> set:
        """이미 처리한 이벤트 ID 목록 로드"""
        if os.path.exists(self.seen_file):
            try:
                with open(self.seen_file, 'r') as f:
                    lines = f.read().strip().split('\n')
                    # 최근 1000개만 유지 (메모리 절약)
                    return set(lines[-1000:]) if lines else set()
            except Exception as e:
                print(f"⚠️  seen 파일 로드 실패: {e}")
                return set()
        return set()
    
    def _load_last_timestamp(self) -> int:
        """마지막 폴링 타임스탬프 로드"""
        if os.path.exists(self.timestamp_file):
            try:
                with open(self.timestamp_file, 'r') as f:
                    timestamp = int(f.read().strip())
                    print(f"✓ Nostr: 마지막 폴링 시간 로드 = {timestamp}")
                    return timestamp
            except Exception as e:
                print(f"⚠️  timestamp 파일 로드 실패: {e}")
        
        # 파일이 없으면 현재 시간 (앞으로의 메시지만)
        return int(time.time())
    
    def _save_last_timestamp(self):
        """마지막 폴링 타임스탬프 저장"""
        try:
            os.makedirs(os.path.dirname(self.timestamp_file), exist_ok=True)
            with open(self.timestamp_file, 'w') as f:
                f.write(str(self.last_poll_timestamp))
        except Exception as e:
            print(f"⚠️  timestamp 저장 실패: {e}")
    
    def _save_seen_event(self, event_id: str):
        """새로 처리한 이벤트 ID 추가 저장"""
        try:
            os.makedirs(os.path.dirname(self.seen_file), exist_ok=True)
            
            # append 모드로 추가
            with open(self.seen_file, 'a') as f:
                f.write(event_id + '\n')
            
            # 메모리에도 추가
            self.seen_event_ids.add(event_id)
            
            # 파일이 너무 커지면 정리 (1000개 초과 시)
            if len(self.seen_event_ids) > 1000:
                with open(self.seen_file, 'w') as f:
                    # 최근 1000개만 저장
                    recent = list(self.seen_event_ids)[-1000:]
                    f.write('\n'.join(recent) + '\n')
                    self.seen_event_ids = set(recent)
                    
        except Exception as e:
            print(f"⚠️  seen 파일 저장 실패: {e}")
    
    def authenticate(self) -> bool:
        """Nostr 릴레이 연결 및 키 로드/생성"""
        if not HAS_NOSTR:
            print("⚠️  pynostr 라이브러리가 필요합니다")
            return False
        
        try:
            # Private key 로드/생성
            private_key_hex = self.config.get('private_key', '')
            
            if private_key_hex:
                # 설정에서 제공된 키 사용
                self.private_key = PrivateKey(bytes.fromhex(private_key_hex))
            else:
                # 키 파일에서 로드 또는 생성
                key_file = f"tokens/nostr_keys/{self.key_name}.key"
                
                if os.path.exists(key_file):
                    # 기존 키 로드
                    with open(key_file, 'r') as f:
                        private_key_hex = f.read().strip()
                    self.private_key = PrivateKey(bytes.fromhex(private_key_hex))
                    print(f"✓ Nostr: 기존 키 로드 ({key_file})")
                else:
                    # 새 키 생성
                    self.private_key = PrivateKey()
                    os.makedirs(os.path.dirname(key_file), exist_ok=True)
                    
                    with open(key_file, 'w') as f:
                        f.write(self.private_key.hex())
                    
                    os.chmod(key_file, 0o600)
                    
                    print(f"✓ Nostr: 새 키 생성 및 저장 ({key_file})")
                    print(f"   Public Key (npub): {self.private_key.public_key.bech32()}")
                    print(f"   Private Key (nsec): {self.private_key.bech32()}")
            
            self.public_key = self.private_key.public_key
            
            # RelayManager 초기화 (실제로는 poll_messages가 자체 WebSocket 사용)
            self.relay_manager = RelayManager(timeout=6)
            for relay in self.relays:
                self.relay_manager.add_relay(relay)
            
            print(f"✓ Nostr: {len(self.relays)}개 릴레이 설정 완료 (WebSocket 직접 사용)")
            print(f"  - npub: {self.public_key.bech32()}")
            print(f"  - hex:  {self.public_key.hex()}")
            return True
            
        except Exception as e:
            print(f"✗ Nostr 인증 실패: {e}")
            return False
    
    def poll_messages(self, max_count: int = 5) -> list:
        """
        새 메시지 폴링 (WebSocket 직접 구현)
        Args:
            max_count: 가져올 최대 메시지 수
        Returns:
            메시지 리스트
        """
        if not self.private_key:
            return []
        
        messages = []
        
        try:
            import websocket
            import json
            import uuid
            import threading
            from datetime import datetime
            
            # 결과 저장용
            received_events = []
            connected = threading.Event()
            
            def on_message(ws, message):
                """WebSocket 메시지 수신"""
                try:
                    data = json.loads(message)
                    if data[0] == "EVENT":
                        event = data[2]
                        if event.get('kind') == 4:  # DM
                            received_events.append(event)
                except:
                    pass
            
            def on_error(ws, error):
                pass
            
            def on_close(ws, close_status_code, close_msg):
                pass
            
            def on_open(ws):
                connected.set()
                # REQ 메시지 전송 - 나에게 온 DM만!
                req = json.dumps([
                    "REQ",
                    f"dm_{uuid.uuid4().hex[:8]}",
                    {
                        "kinds": [4],
                        "#p": [self.public_key.hex()],  # 나에게 온 DM만
                        "since": self.last_poll_timestamp,  # 이 시간 이후 메시지만!
                        "limit": 100
                    }
                ])
                ws.send(req)
            
            # 릴레이 선택 (첫 번째)
            relay_url = self.relays[0] if self.relays else "wss://relay.damus.io"
            
            # WebSocket 연결
            ws = websocket.WebSocketApp(
                relay_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # 별도 스레드에서 실행
            wst = threading.Thread(target=ws.run_forever, daemon=True)
            wst.start()
            
            # 연결 대기 (5초 타임아웃)
            if not connected.wait(timeout=5):
                ws.close()
                print(f"⚠️  Nostr 릴레이 연결 타임아웃: {relay_url}")
                return []
            
            # 3초 대기 (이벤트 수신)
            time.sleep(3)
            
            # 연결 종료
            ws.close()
            wst.join(timeout=1)
            
            if received_events:
                print(f"✓ Nostr: {len(received_events)}개 DM 이벤트 수신 (since={datetime.fromtimestamp(self.last_poll_timestamp).strftime('%H:%M:%S')})")
            
            # 이벤트 처리하면서 최신 시간 추적
            latest_timestamp = self.last_poll_timestamp
            processed_count = 0
            
            for event in received_events:
                # 중복 체크
                event_id = event.get('id')
                if event_id in self.seen_event_ids:
                    continue
                
                # 영구 저장
                self._save_seen_event(event_id)
                
                # #p 태그 확인 - 나에게 온 DM인가?
                is_for_me = False
                for tag in event.get('tags', []):
                    if len(tag) >= 2 and tag[0] == 'p' and tag[1] == self.public_key.hex():
                        is_for_me = True
                        break
                
                if not is_for_me:
                    continue
                
                # 복호화 시도
                try:
                    decrypted = self.private_key.decrypt_message(
                        event.get('content', ''),
                        event.get('pubkey', '')
                    )
                    
                    # 시간은 UTC 타임스탬프
                    timestamp = event.get('created_at', 0)
                    
                    messages.append({
                        'id': event.get('id'),
                        'from': event.get('pubkey'),
                        'subject': 'Nostr DM',
                        'body': decrypted,
                        'timestamp': timestamp  # Unix timestamp (UTC)
                    })
                    
                    # 한국 시간으로 변환 (+9시간)
                    from datetime import datetime, timezone, timedelta
                    kst = timezone(timedelta(hours=9))
                    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(kst)
                    
                    print(f"✓ DM 복호화: from={event.get('pubkey', '')[:16]}... time={dt.strftime('%Y-%m-%d %H:%M:%S KST')} msg={decrypted[:30]}...")
                    
                    if len(messages) >= max_count:
                        break
                    
                    # 처리한 이벤트의 시간 추적
                    event_time = event.get('created_at', 0)
                    if event_time > latest_timestamp:
                        latest_timestamp = event_time
                    processed_count += 1
                        
                except Exception as e:
                    print(f"⚠️  DM 복호화 실패: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 실제로 처리한 이벤트가 있으면 timestamp 업데이트
            if processed_count > 0:
                self.last_poll_timestamp = latest_timestamp + 1  # +1초 (같은 메시지 재수신 방지)
                self._save_last_timestamp()
                print(f"✓ Nostr: {processed_count}개 새 메시지 처리, timestamp 업데이트 → {latest_timestamp}")
            else:
                # 새 메시지 없으면 timestamp를 현재 시간으로 (이후 메시지 대비)
                self.last_poll_timestamp = int(time.time())
                self._save_last_timestamp()
                print(f"✓ Nostr: 새 메시지 없음, timestamp 현재 시간으로 업데이트")
            
        except Exception as e:
            print(f"⚠️  메시지 폴링 오류: {e}")
        
        return messages
    
    def send_message(self, to: str, subject: str, body: str) -> bool:
        """메시지 전송 (WebSocket 직접 구현)"""
        if not self.private_key:
            print(f"⚠️  Nostr 전송 실패: private_key={self.private_key is not None}")
            return False
        
        try:
            import websocket
            import json
            import threading
            
            # npub 형식이면 hex로 변환
            to_hex = to
            if to.startswith('npub'):
                from pynostr.key import PublicKey
                to_hex = PublicKey.from_npub(to).hex()
                print(f"✓ Nostr: npub 변환 {to[:16]}... → {to_hex[:16]}...")
            
            print(f"✓ Nostr DM 전송 시작: to={to_hex[:16]}... msg={body[:30]}...")
            
            # 암호화된 DM 생성
            encrypted_content = self.private_key.encrypt_message(body, to_hex)
            
            # 이벤트 생성
            event = Event(
                kind=EventKind.ENCRYPTED_DIRECT_MESSAGE,
                content=encrypted_content,
                pubkey=self.public_key.hex(),
                tags=[['p', to_hex]]
            )
            
            # 이벤트 서명
            event.sign(self.private_key.hex())
            
            # WebSocket으로 직접 전송
            published = threading.Event()
            error_msg = [None]
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    # OK 응답 확인
                    if data[0] == "OK" and data[1] == event.id:
                        if data[2]:  # success
                            published.set()
                        else:
                            error_msg[0] = data[3] if len(data) > 3 else "Unknown error"
                            print(f"  - 릴레이 거부: {error_msg[0]}")
                except:
                    pass
            
            def on_error(ws, error):
                error_msg[0] = str(error)
            
            def on_close(ws, close_status_code, close_msg):
                pass
            
            def on_open(ws):
                # EVENT 메시지 전송
                event_msg = json.dumps([
                    "EVENT",
                    {
                        "id": event.id,
                        "pubkey": event.pubkey,
                        "created_at": event.created_at,
                        "kind": event.kind,
                        "tags": event.tags,
                        "content": event.content,
                        "sig": event.sig  # signature → sig
                    }
                ])
                ws.send(event_msg)
            
            # 릴레이 선택
            relay_url = self.relays[0] if self.relays else "wss://relay.damus.io"
            
            # WebSocket 연결
            ws = websocket.WebSocketApp(
                relay_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # 별도 스레드에서 실행
            wst = threading.Thread(target=ws.run_forever, daemon=True)
            wst.start()
            
            # 응답 대기 (5초)
            if published.wait(timeout=5):
                ws.close()
                wst.join(timeout=1)
                print(f"✓ Nostr DM 전송 성공: {to_hex[:16]}...")
                return True
            else:
                ws.close()
                wst.join(timeout=1)
                if error_msg[0]:
                    print(f"✗ Nostr DM 전송 실패: {error_msg[0]}")
                else:
                    print(f"⚠️  Nostr DM 전송 타임아웃 (릴레이 응답 없음)")
                return False
            
        except Exception as e:
            print(f"✗ Nostr 메시지 전송 실패: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def mark_as_read(self, message_id: str) -> bool:
        """메시지를 읽음으로 표시 (로컬 seen 목록에 추가 및 영구 저장)"""
        self._save_seen_event(message_id)
        return True
    
    def get_channel_info(self) -> dict:
        """채널 정보 반환"""
        return {
            'type': 'nostr',
            'account': self.public_key.bech32()[:16] + '...' if self.public_key else 'not-authenticated'
        }
    
    def get_status(self) -> dict:
        """채널 상태 반환"""
        return {
            'type': 'nostr',
            'authenticated': self.relay_manager is not None,
            'public_key': self.public_key.bech32() if self.public_key else None,
            'public_key_hex': self.public_key.hex() if self.public_key else None,
            'private_key': self.private_key.bech32() if self.private_key else None,
            'relay_count': len(self.relays),
            'relays': self.relays,  # 실제 릴레이 URL 목록
            'seen_events': len(self.seen_event_ids),
            'listening': self.listening
        }
    
    def is_realtime(self) -> bool:
        """실시간 WebSocket 채널"""
        return True
    
    def register_callback(self, callback):
        """
        실시간 메시지 수신 시 호출할 콜백 등록
        Args:
            callback: 메시지 수신 시 호출할 함수 (msg dict를 인자로 받음)
        """
        self.callback = callback
    
    def start_listening(self):
        """실시간 리스닝 시작 - WebSocket 연결 유지"""
        if self.listening or not self.relay_manager:
            return
        
        self.listening = True
        
        # WebSocket 연결 시작
        self._start_websocket()
        
        print(f"✓ Nostr: 실시간 리스닝 시작 (WebSocket 연결 유지)")
    
    def stop_listening(self):
        """실시간 리스닝 중지"""
        self.listening = False
        if self.listening_thread:
            self.listening_thread.join(timeout=2)
        print(f"✓ Nostr: 실시간 리스닝 중지")
    
    def _listening_loop(self):
        """백그라운드에서 poll_messages 호출하여 메시지 확인"""
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self.listening:
            try:
                # poll_messages로 메시지 가져오기
                messages = self.poll_messages(max_count=5)
                
                # 성공적으로 메시지를 가져오면 에러 카운터 초기화
                consecutive_errors = 0
                
                # 콜백 호출
                for message in messages:
                    if self.callback:
                        self.callback(message)
                
            except Exception as e:
                consecutive_errors += 1
                print(f"⚠️  Nostr 리스닝 오류 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                
                # 연속된 에러가 많으면 재연결 시도
                if consecutive_errors >= max_consecutive_errors:
                    print(f"⚠️  Nostr 리스닝: 연속 에러 {consecutive_errors}번, 재인증 시도")
                    try:
                        self.authenticate()
                        consecutive_errors = 0
                        print(f"✓ Nostr 재인증 성공")
                    except Exception as re_err:
                        print(f"✗ Nostr 재인증 실패: {re_err}")
                        # 재인증 실패 시 60초 대기 후 재시도
                        time.sleep(60)
            
            # 10초 대기 (실시간성 개선)
            time.sleep(10)
    
    def _contains_korean(self, text: str) -> bool:
        """텍스트에 한국어가 포함되어 있는지 확인"""
        for char in text:
            # 한글 유니코드 범위: AC00-D7AF (완성형), 1100-11FF (자모)
            if '\uAC00' <= char <= '\uD7AF' or '\u1100' <= char <= '\u11FF':
                return True
        return False

    def search_public_notes(self, query: str = None, author: str = None, limit: int = 10, language: str = None) -> list:
        """
        퍼블릭 노트 검색 (WebSocket 직접 구현, 여러 릴레이 병렬 조회)
        Args:
            query: 검색 키워드 (content에서 검색, None이면 전체)
            author: 작성자 pubkey (hex 또는 npub)
            limit: 최대 결과 수
            language: 언어 필터 ('ko' = 한국어만, None = 전체)
        Returns:
            노트 리스트
        """
        try:
            # limit을 정수로 변환 (방어적 코딩)
            limit = int(limit) if limit else 10

            import websocket
            import json
            import uuid
            import threading
            from concurrent.futures import ThreadPoolExecutor, as_completed

            # author가 npub 형식이면 hex로 변환
            author_hex = None
            if author:
                if author.startswith('npub'):
                    from pynostr.key import PublicKey
                    author_hex = PublicKey.from_npub(author).hex()
                else:
                    author_hex = author

            # 여러 릴레이에서 병렬로 수집
            all_events = []
            events_lock = threading.Lock()

            def fetch_from_relay(relay_url: str) -> list:
                """단일 릴레이에서 노트 가져오기"""
                received = []
                connected = threading.Event()

                def on_message(ws, message):
                    try:
                        data = json.loads(message)
                        if data[0] == "EVENT":
                            event = data[2]

                            # kind 1 (TEXT_NOTE)만 허용
                            if event.get('kind') != 1:
                                return

                            content = event.get('content', '')

                            # Base64 암호화 데이터 필터링
                            if len(content) > 100 and content.replace('+', '').replace('/', '').replace('=', '').isalnum():
                                return

                            # 빈 콘텐츠 필터링
                            if not content.strip():
                                return

                            # 언어 필터링 (한국어)
                            if language == 'ko' and not self._contains_korean(content):
                                return

                            # query 필터링 (query가 있을 때만)
                            if query and query.lower() not in content.lower():
                                return

                            received.append(event)
                    except:
                        pass

                def on_error(ws, error):
                    pass

                def on_close(ws, close_status_code, close_msg):
                    pass

                def on_open(ws):
                    connected.set()

                    # REQ 메시지 생성 (언어 필터링을 위해 더 많이 요청)
                    fetch_limit = limit * 10 if language == 'ko' else limit * 3

                    req_filter = {
                        "kinds": [1],
                        "limit": fetch_limit
                    }
                    if author_hex:
                        req_filter["authors"] = [author_hex]

                    req_id = f"search_{uuid.uuid4().hex[:8]}"
                    req_message = json.dumps(["REQ", req_id, req_filter])
                    ws.send(req_message)

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

                    if not connected.wait(timeout=5):
                        ws.close()
                        return []

                    # 최대 4초 대기 (한국어 필터링 시 더 많이 필요)
                    wait_time = 40 if language == 'ko' else 30
                    for _ in range(wait_time):
                        if len(received) >= limit * 2:
                            break
                        time.sleep(0.1)

                    ws.close()
                    wst.join(timeout=1)

                    return received

                except Exception as e:
                    return []

            # 사용할 릴레이 목록 (더 많은 릴레이 추가)
            relays_to_use = self.relays.copy()
            extra_relays = [
                'wss://relay.nostr.band',
                'wss://nos.lol',
                'wss://relay.damus.io',
                'wss://nostr.wine',
                'wss://relay.snort.social'
            ]
            for r in extra_relays:
                if r not in relays_to_use:
                    relays_to_use.append(r)

            # 최대 5개 릴레이 병렬 조회
            relays_to_use = relays_to_use[:5]

            print(f"✓ Nostr: {len(relays_to_use)}개 릴레이에서 병렬 검색 시작 (language={language}, query={query})")

            # 병렬 실행
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(fetch_from_relay, relay): relay for relay in relays_to_use}

                for future in as_completed(futures, timeout=10):
                    relay = futures[future]
                    try:
                        events = future.result()
                        if events:
                            with events_lock:
                                all_events.extend(events)
                            print(f"  - {relay}: {len(events)}개 수신")
                    except Exception as e:
                        print(f"  - {relay}: 오류 ({e})")

            # 중복 제거 (event id 기준)
            seen_ids = set()
            unique_events = []
            for event in all_events:
                event_id = event.get('id')
                if event_id not in seen_ids:
                    seen_ids.add(event_id)
                    unique_events.append(event)

            # 시간순 정렬 (최신순)
            unique_events.sort(key=lambda x: x.get('created_at', 0), reverse=True)

            # 결과 가공
            results = []
            for event in unique_events[:limit]:
                results.append({
                    'id': event.get('id', 'N/A'),
                    'author': event.get('pubkey', 'N/A'),
                    'content': event.get('content', ''),
                    'timestamp': event.get('created_at', 0),
                    'tags': event.get('tags', [])
                })

            print(f"✓ Nostr 검색 완료: {len(results)}개 노트 발견 (전체 {len(unique_events)}개 중)")
            return results

        except Exception as e:
            print(f"⚠️  Nostr 검색 오류: {e}")
            import traceback
            traceback.print_exc()
            return []

    def search_nostr_band(self, query: str, limit: int = 10) -> list:
        """
        nostr.band API를 사용한 키워드 검색 (한국어 검색에 효과적)
        Args:
            query: 검색 키워드 (필수)
            limit: 최대 결과 수
        Returns:
            노트 리스트
        """
        import requests

        try:
            limit = int(limit) if limit else 10

            print(f"✓ nostr.band 검색 시작: query='{query}', limit={limit}")

            # nostr.band API 호출
            url = f"https://api.nostr.band/v0/search?q={requests.utils.quote(query)}&limit={limit}"

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            # 결과 가공
            results = []
            events = data.get('events', []) or data.get('notes', []) or []

            # API 응답 구조가 다를 수 있으므로 유연하게 처리
            if not events and isinstance(data, list):
                events = data

            for event in events[:limit]:
                # nostr.band API 응답 형식에 맞춰 처리
                if isinstance(event, dict):
                    results.append({
                        'id': event.get('id', 'N/A'),
                        'author': event.get('pubkey', event.get('author', 'N/A')),
                        'content': event.get('content', ''),
                        'timestamp': event.get('created_at', 0),
                        'tags': event.get('tags', [])
                    })

            print(f"✓ nostr.band 검색 완료: {len(results)}개 노트 발견")
            return results

        except requests.exceptions.RequestException as e:
            print(f"⚠️  nostr.band API 오류: {e}")
            return []
        except Exception as e:
            print(f"⚠️  nostr.band 검색 오류: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _start_websocket(self):
        """진짜 실시간 WebSocket 연결 시작"""
        import websocket
        import json
        import uuid
        
        relay_url = self.relays[0] if self.relays else "wss://relay.damus.io"
        
        def on_message(ws, message):
            """메시지 수신 시 즉시 처리"""
            try:
                data = json.loads(message)
                if data[0] == "EVENT":
                    event = data[2]
                    if event.get('kind') == 4:  # DM
                        self._process_dm_event(event)
            except Exception as e:
                print(f"⚠️  Nostr 메시지 처리 오류: {e}")
        
        def on_error(ws, error):
            print(f"⚠️  Nostr WebSocket 에러: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            print(f"⚠️  Nostr WebSocket 닫힘: {close_status_code} - {close_msg}")
            # 재연결 시도
            if self.listening:
                print("⚠️  5초 후 재연결 시도...")
                time.sleep(5)
                if self.listening:
                    self._start_websocket()
        
        def on_open(ws):
            self.ws_connected.set()
            # REQ 메시지 전송 - 나에게 온 DM만!
            req = json.dumps([
                "REQ",
                f"dm_{uuid.uuid4().hex[:8]}",
                {
                    "kinds": [4],
                    "#p": [self.public_key.hex()],
                    "since": int(time.time())  # 지금부터 오는 메시지만
                }
            ])
            ws.send(req)
            print(f"✓ Nostr WebSocket 연결 성공: {relay_url}")
        
        # WebSocket 연결
        self.ws = websocket.WebSocketApp(
            relay_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # 별도 스레드에서 실행
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()
        
        # 연결 대기
        self.ws_connected.wait(timeout=10)
    
    def _process_dm_event(self, event):
        """수신한 DM 이벤트 처리"""
        try:
            # 중복 체크
            event_id = event.get('id')
            if event_id in self.seen_event_ids:
                return
            
            # 영구 저장
            self._save_seen_event(event_id)
            
            # #p 태그 확인 - 나에게 온 DM인가?
            is_for_me = False
            for tag in event.get('tags', []):
                if len(tag) >= 2 and tag[0] == 'p' and tag[1] == self.public_key.hex():
                    is_for_me = True
                    break
            
            if not is_for_me:
                return
            
            # 복호화
            decrypted = self.private_key.decrypt_message(
                event.get('content', ''),
                event.get('pubkey', '')
            )
            
            # 한국 시간으로 변환
            from datetime import datetime, timezone, timedelta
            timestamp = event.get('created_at', 0)
            kst = timezone(timedelta(hours=9))
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(kst)
            
            print(f"✓ Nostr DM 수신: from={event.get('pubkey', '')[:16]}... time={dt.strftime('%H:%M:%S KST')} msg={decrypted[:30]}...")
            
            # 콜백 호출
            if self.callback:
                message = {
                    'id': event.get('id'),
                    'from': event.get('pubkey'),
                    'subject': 'Nostr DM',
                    'body': decrypted,
                    'timestamp': timestamp
                }
                self.callback(message)
        
        except Exception as e:
            print(f"⚠️  DM 처리 실패: {e}")
            import traceback
            traceback.print_exc()
