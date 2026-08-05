"""IndieNet 소셜 계층 (2026-07-18 모듈화): 팔로우·저자 피드/프로필·DM(NIP-04/17)."""
import json
import time
import uuid
import sqlite3
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

from indienet_common import (
    HAS_NOSTR, _ON_PHONE,
    INDIENET_DIR, IDENTITY_FILE, SETTINGS_FILE, CACHE_DIR, POSTS_DB, DMS_DB,
    DEFAULT_RELAYS, INDIENET_TAG,
    Event, EventKind, PrivateKey, PublicKey,
)
if HAS_NOSTR:
    import websocket


class IndieNetSocialMixin:
    """indienet.py 에서 verbatim 이동 — IndieNet 에 믹스인 합성(self 속성 공유)."""

    # ============ 팔로우 (로컬 저장) + 저자별/팔로잉 피드 ============

    def _pubkey_to_hex(self, pubkey: str) -> str:
        """npub/hex → hex (안전판). 실패 시 빈 문자열.

        _to_hex 와 달리 예외를 던지지 않는다(팔로우 목록에 잘못된 값이 섞여도
        전체 조회가 죽지 않게). 폰(HAS_NOSTR=False)에서 npub 디코드는 미지원 →
        폰은 hex 로 저장돼 있어야 한다."""
        pk = (pubkey or "").strip()
        if not pk:
            return ""
        if pk.startswith("npub"):
            if not HAS_NOSTR:
                return ""
            try:
                return PublicKey.from_npub(pk).hex()
            except Exception:
                return ""
        return pk  # hex 가정

    def _same_pubkey(self, a: str, b: str) -> bool:
        """두 pubkey(npub/hex 혼재 가능)가 같은 신원인지 비교."""
        if not a or not b:
            return False
        if a.strip() == b.strip():
            return True
        ha, hb = self._pubkey_to_hex(a), self._pubkey_to_hex(b)
        return bool(ha) and ha == hb

    def get_follows(self) -> List[Dict[str, Any]]:
        """팔로우 목록 조회."""
        return list(self.settings.follows)

    def add_follow(self, pubkey: str, name: str = None) -> Dict[str, Any]:
        """팔로우 추가 (로컬 저장). 이미 있으면 이름만 갱신하고 그 항목 반환."""
        pk = (pubkey or "").strip()
        if not pk:
            raise ValueError("팔로우할 pubkey(npub 또는 hex)가 필요합니다")
        for f in self.settings.follows:
            if self._same_pubkey(f.get("pubkey", ""), pk):
                if name and f.get("name") != name:
                    f["name"] = name
                    self.settings.save()
                return f
        entry = {
            "pubkey": pk,
            "name": name or "",
            "added_at": datetime.now().isoformat(),
        }
        self.settings.follows.append(entry)
        self.settings.save()
        print(f"✓ IndieNet: 팔로우 추가 - {pk[:16]}...")
        return entry

    def remove_follow(self, pubkey: str) -> bool:
        """언팔로우 (로컬 저장)."""
        pk = (pubkey or "").strip()
        for i, f in enumerate(self.settings.follows):
            if self._same_pubkey(f.get("pubkey", ""), pk):
                self.settings.follows.pop(i)
                self.settings.save()
                print(f"✓ IndieNet: 언팔로우 - {pk[:16]}...")
                return True
        return False

    def _author_accept(self, event: dict) -> Optional[dict]:
        """kind:1 이벤트 → 표준 글 dict. 저자 hex → npub 변환."""
        author_hex = event.get("pubkey", "")
        try:
            author_npub = PublicKey(bytes.fromhex(author_hex)).bech32()
        except Exception:
            author_npub = author_hex
        return {
            "id": event.get("id"),
            "author": author_npub,
            "content": event.get("content", ""),
            "created_at": event.get("created_at"),
            "tags": event.get("tags", []),
        }

    def fetch_author_posts(self, pubkey: str, limit: int = 50,
                           since: int = None) -> List[dict]:
        """특정 저자의 공개 글(kind:1)만 조회. authors 필터로 릴레이 질의.

        get_user_info(kind:0)·fetch_dm_relays(kind:10050)와 같은 authors 필터
        프리미티브를 kind:1 로 재사용 — 새 릴레이 로직 없음."""
        if not self._initialized:
            return []
        author_hex = self._pubkey_to_hex(pubkey)
        if not author_hex:
            print(f"⚠️  IndieNet: 저자 pubkey 변환 실패 - {pubkey}")
            return []
        try:
            req_filter = {"kinds": [1], "authors": [author_hex], "limit": limit}
            if since:
                req_filter["since"] = since
            posts = self._query_relays(req_filter, self._author_accept)
            try:
                self._cache_posts(posts)
            except Exception:
                pass
            posts.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return posts[:limit]
        except Exception as e:
            print(f"✗ IndieNet: 저자 글 조회 실패 - {e}")
            return []

    def fetch_following_feed(self, limit: int = 50,
                             since: int = None) -> List[dict]:
        """팔로우한 사람 전체의 최신 글(kind:1) 타임라인. authors 목록 필터 1회 질의."""
        if not self._initialized:
            return []
        hexes = [self._pubkey_to_hex(f.get("pubkey", "")) for f in self.settings.follows]
        hexes = [h for h in hexes if h]
        if not hexes:
            return []
        try:
            req_filter = {"kinds": [1], "authors": hexes, "limit": limit}
            if since:
                req_filter["since"] = since
            posts = self._query_relays(req_filter, self._author_accept)
            try:
                self._cache_posts(posts)
            except Exception:
                pass
            posts.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return posts[:limit]
        except Exception as e:
            print(f"✗ IndieNet: 팔로잉 피드 조회 실패 - {e}")
            return []

    def _article_accept(self, event: dict) -> Optional[dict]:
        """kind:30023(NIP-23) 이벤트 → 표준 글 dict. 태그에서 title/summary 추출."""
        author_hex = event.get("pubkey", "")
        try:
            author_npub = PublicKey(bytes.fromhex(author_hex)).bech32()
        except Exception:
            author_npub = author_hex
        title = summary = ""
        for t in (event.get("tags") or []):
            if isinstance(t, list) and len(t) >= 2:
                if t[0] == "title":
                    title = t[1]
                elif t[0] == "summary":
                    summary = t[1]
        return {
            "id": event.get("id"),
            "author": author_npub,
            "title": title,
            "summary": summary,
            "content": event.get("content", ""),
            "created_at": event.get("created_at"),
        }

    def fetch_author_articles(self, pubkey: str, limit: int = 20) -> List[dict]:
        """특정 저자의 공개 장문 글(NIP-23, kind:30023) 조회. fetch_author_posts 와 같은
        authors 필터 프리미티브 재사용 — kind 만 30023. 새 릴레이 로직 없음."""
        if not self._initialized:
            return []
        author_hex = self._pubkey_to_hex(pubkey)
        if not author_hex:
            return []
        try:
            arts = self._query_relays({"kinds": [30023], "authors": [author_hex], "limit": limit},
                                      self._article_accept)
            arts.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return arts[:limit]
        except Exception as e:
            print(f"✗ IndieNet: 저자 글(NIP-23) 조회 실패 - {e}")
            return []

    def _profile_accept(self, event: dict) -> Optional[dict]:
        """kind:0 이벤트 → 프로필 dict(name/about 등)."""
        if event.get("kind") != 0:
            return None
        try:
            c = json.loads(event.get("content") or "{}")
        except Exception:
            c = {}
        return {
            "pubkey": event.get("pubkey"),
            "name": c.get("name", ""),
            "display_name": c.get("display_name", ""),
            "about": c.get("about", ""),
            "picture": c.get("picture", ""),
            "created_at": event.get("created_at", 0),
        }

    def fetch_author_profile(self, pubkey: str) -> Optional[dict]:
        """저자 공개 프로필(kind:0) 조회. _query_relays 다중 릴레이 프리미티브 재사용
        (get_user_info 의 단일 릴레이보다 견고 — replaceable 최신본 1개)."""
        if not self._initialized:
            return None
        author_hex = self._pubkey_to_hex(pubkey)
        if not author_hex:
            return None
        try:
            got = self._query_relays({"kinds": [0], "authors": [author_hex], "limit": 1},
                                     self._profile_accept)
            got.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return got[0] if got else None
        except Exception as e:
            print(f"✗ IndieNet: 저자 프로필 조회 실패 - {e}")
            return None

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

        # 폰: NIP-04(kind:4, pynostr decrypt_message) 미지원 → NIP-17 + 영구 캐시만.
        if _ON_PHONE:
            try:
                nip17_dms = self.fetch_dms_nip17(limit=limit, since=since)
                try:
                    self._cache_dms(nip17_dms)
                    dms = self._get_cached_dms(limit=limit, since=since)
                except Exception:
                    dms = nip17_dms
                dms.sort(key=lambda x: x.get('created_at', 0), reverse=True)
                print(f"✓ IndieNet(phone): {len(dms)}개 DM (NIP-17 {len(nip17_dms)} + 캐시)")
                return dms[:limit]
            except Exception as e:
                print(f"✗ IndieNet(phone): DM 조회 실패 - {e}")
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

        # 폰: kind:1059 구독은 _query_relays(브리지), unwrap 은 Kotlin Nip17.unwrapDm.
        if _ON_PHONE:
            try:
                import nostr_phone_bridge as bridge
                my_hex = getattr(self.identity, 'public_key_hex', '')

                def accept_p(event):
                    out = bridge.unwrap_dm(event)
                    if not out:
                        return None
                    ca = out.get("created_at") or event.get("created_at") or 0
                    if since and ca < since:
                        return None
                    return {"id": event.get("id"), "from": out.get("sender"),
                            "content": out.get("content"), "created_at": ca, "tags": []}

                return self._query_relays(
                    {"kinds": [1059], "#p": [my_hex], "limit": limit},
                    accept_p, relays=self._self_dm_relays(),
                )
            except Exception as e:
                print(f"✗ NIP-17 DM 수신(phone) 실패 - {e}")
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

    def send_dm_nip17(self, to_pubkey: str, content: str,
                      extra_tags: Optional[list] = None) -> Optional[str]:
        """NIP-17 비공개 DM 발송. 수신자의 kind:10050 DM relay로 gift-wrap(kind1059) 발행.
        최신 클라이언트(Damus/Amethyst/0xchat)가 읽는 표준 방식.

        모든 발신 DM 은 rumor 에 indiebizOS peer 표식 태그를 얹는다(nip17.INDIEBIZ_TAG).
        extra_tags 로 추가 rumor 태그(예: 의뢰 타입)를 실을 수 있다."""
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None

        # 폰: nip17(pynostr) 대신 Kotlin Nip17.wrapDm + RelayClient.publish.
        if _ON_PHONE:
            try:
                import nostr_phone_bridge as bridge
                to_hex = to_pubkey  # 폰: hex 가정(npub 디코드는 후속)
                dm_relays = self.fetch_dm_relays(to_hex)  # _query_relays 경유(브리지)
                event_id = bridge.send_dm(to_hex, content, dm_relays)
                if event_id:
                    print(f"✓ NIP-17 DM(phone) 발송 - {event_id[:16]}...")
                return event_id
            except Exception as e:
                print(f"✗ NIP-17 DM(phone) 발송 실패 - {e}")
                return None

        try:
            import nip17
            to_hex = self._to_hex(to_pubkey)
            dm_relays = self.fetch_dm_relays(to_hex)
            print(f"✓ NIP-17 DM: to={to_hex[:16]}... relays={dm_relays}")

            peer_tags = [[nip17.INDIEBIZ_TAG, nip17.INDIEBIZ_PROTOCOL]]
            if extra_tags:
                peer_tags.extend(extra_tags)
            gift_wrap = nip17.wrap_dm(self.identity.private_key.hex(), to_hex, content,
                                      extra_tags=peer_tags)
            event_id = self._publish_event(gift_wrap, relays=dm_relays)

            if event_id:
                print(f"✓ NIP-17 DM 발송 완료 - gift_wrap_id={event_id[:16]}...")
            else:
                print("✗ NIP-17 DM 발송 실패 (relay OK 응답 없음)")
            return event_id
        except Exception as e:
            print(f"✗ NIP-17 DM 발송 실패 - {e}")
            return None

# (2026-06-13 은퇴) 구 send_dm(NIP-04 kind:4)은 최신 앱(0xchat/Damus)이 복호 못 해 DM이 깨졌다.
# 모든 발신을 send_dm_nip17(NIP-17 gift-wrap kind:1059) 단일 경로로 통일 — 호출처(channel_poller
# 자동응답·extension REST) 전부 이관 후 메서드 삭제. 수신은 NIP-17 우선(폰=NIP-17 전용).
