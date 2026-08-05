"""IndieNet 게시 계층 (2026-07-18 모듈화 — 1500줄 규칙): 보드 CRUD·글/프로필/아티클/소개 게시."""
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


class IndieNetPublishMixin:
    """indienet.py 에서 verbatim 이동 — IndieNet 에 믹스인 합성(self 속성 공유)."""

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

        # 폰: pynostr Event 대신 Kotlin 브리지로 빌드+서명+발행.
        if _ON_PHONE:
            try:
                import nostr_phone_bridge as bridge
                full_content = f"{content}\n\n#{hashtag}"
                created_at = int(time.time())
                relays = self.settings.relays if self.settings.relays else DEFAULT_RELAYS
                event_id = bridge.publish_note(1, [['t', hashtag.lower()]], full_content, relays, created_at)
                if event_id:
                    print(f"✓ IndieNet(phone): 글 게시 #{hashtag} - {event_id[:16]}...")
                    try:
                        self._cache_posts([{
                            'id': event_id,
                            'author': getattr(self.identity, 'public_key_hex', ''),
                            'content': full_content,
                            'created_at': created_at,
                            'tags': [['t', hashtag.lower()]],
                        }])
                    except Exception as e:
                        print(f"⚠️  IndieNet(phone): 게시 글 캐시 실패 - {e}")
                return event_id
            except Exception as e:
                print(f"✗ IndieNet(phone): 글 게시 실패 - {e}")
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

    def publish_profile(self, about: str = "", name: str = "", extra: dict = None) -> Optional[str]:
        """공개 프로필(kind:0 메타데이터) 발행. content = 사용자가 작성/설정한 값만(name·about) +
        indiebiz peer 마커. replaceable(최신본이 이김)이라 재발행이 곧 갱신 → njump.me/npub 이
        이 프로필을 자기소개 페이지로 렌더한다. 여러 소스에서 정보를 긁어 조합하지 않는다."""
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None
        try:
            import nip17
            meta: dict = {}
            if name:
                meta["name"] = name
                meta["display_name"] = name
            if about:
                meta["about"] = about
            if extra:
                meta.update(extra)
            # indiebizOS peer 마커(kind:0 = 접촉 전 발견용 프로필 마커, DM rumor 태그와 동일 프로토콜)
            meta["indiebiz_agent"] = {"protocol": nip17.INDIEBIZ_PROTOCOL}
            content = json.dumps(meta, ensure_ascii=False)
            if _ON_PHONE:
                import nostr_phone_bridge as bridge
                relays = self.settings.relays if self.settings.relays else DEFAULT_RELAYS
                return bridge.publish_note(0, [], content, relays, int(time.time()))
            event = Event(pubkey=self.identity.public_key.hex(), content=content, kind=0)
            event.sign(self.identity.private_key.hex())
            event_id = self._publish_event(event)
            if event_id:
                print(f"✓ IndieNet: 공개 프로필(kind:0) 발행 - {event_id[:16]}...")
            return event_id
        except Exception as e:
            print(f"✗ IndieNet: 공개 프로필 발행 실패 - {e}")
            return None

    def publish_article(self, title: str, content: str, slug: str,
                        summary: str = "") -> Optional[str]:
        """공개 장문 글(NIP-23, kind:30023) 발행. slug=d 태그(같은 slug 재발행 = 같은 글 갱신).
        content = 사용자가 작성한 마크다운 그대로. njump 가 제목·본문 있는 글로 렌더."""
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None
        try:
            now = int(time.time())
            tags = [["d", slug], ["title", title or ""], ["published_at", str(now)]]
            if summary:
                tags.append(["summary", summary])
            if _ON_PHONE:
                import nostr_phone_bridge as bridge
                relays = self.settings.relays if self.settings.relays else DEFAULT_RELAYS
                return bridge.publish_note(30023, tags, content or "", relays, now)
            event = Event(pubkey=self.identity.public_key.hex(), content=content or "", kind=30023)
            for t in tags:
                event.tags.append(t)
            event.sign(self.identity.private_key.hex())
            event_id = self._publish_event(event)
            if event_id:
                print(f"✓ IndieNet: 공개 글(NIP-23) 발행 '{title}' - {event_id[:16]}...")
            return event_id
        except Exception as e:
            print(f"✗ IndieNet: 공개 글 발행 실패 - {e}")
            return None

    def publish_intro(self, text: str, website: str = "", hashtag: str = None) -> Optional[str]:
        """발견용 자기소개 노트(kind:1) 발행 — 기본 커뮤니티 태그 #IndieNet.
        #IndieNet 을 구독/검색하는 낯선 사람도 나를 찾게 하는 '망으로 보내는 소개 메시지'다.
        content = 사용자가 쓴 소개 + 공개 창고 주소(있으면). 서명(npub)이 신원을 실어 나른다.
        보드 write 경로와 동일 규약(kind:1 + `['t', tag.lower()]` + 본문 #태그)이라 같은
        #IndieNet 스트림에 얹혀 [others:feed]/[others:board] 로 서로 읽힌다."""
        if not self._initialized:
            print("✗ IndieNet이 초기화되지 않음")
            return None
        try:
            tag = hashtag or INDIENET_TAG            # 기본 #IndieNet (그 태그를 만든 이유=망 발견)
            now = int(time.time())
            tags = [["t", tag.lower()]]              # 보드와 동일하게 t-태그는 소문자
            body = (text or "").strip()
            if website:
                # 주소만 있으면 뭐하는 곳인지 모르니 "공유창고 Warehouse : <주소>" 라벨을 붙인다
                # (사람이 읽는 본문 + 기계가 파싱하는 계약 — 한/영 키워드 병기로 보편성 확보,
                #  이웃찾기 탭의 창고이웃 등록 버튼이 이 키워드를 보고 붙는다).
                labeled = "공유창고 Warehouse : " + website
                body = (body + "\n\n" + labeled).strip() if body else labeled
            body = (body + f"\n\n#{tag}").strip()    # 본문 표시용 #IndieNet
            if _ON_PHONE:
                import nostr_phone_bridge as bridge
                relays = self.settings.relays if self.settings.relays else DEFAULT_RELAYS
                return bridge.publish_note(1, tags, body, relays, now)
            event = Event(pubkey=self.identity.public_key.hex(), content=body, kind=1)
            for t in tags:
                event.tags.append(t)
            event.sign(self.identity.private_key.hex())
            event_id = self._publish_event(event)
            if event_id:
                print(f"✓ IndieNet: 발견 노트(kind:1 #{tag}) 발행 - {event_id[:16]}...")
            return event_id
        except Exception as e:
            print(f"✗ IndieNet: 발견 노트 발행 실패 - {e}")
            return None

    def article_url(self, slug: str) -> Optional[str]:
        """발행한 NIP-23 글의 공유 링크(njump). naddr(NIP-19 주소)라 같은 slug 재발행해도
        링크가 최신본을 가리킨다. 실패 시 npub 프로필 링크로 폴백."""
        try:
            from pynostr import bech32
            pubkey_hex = self.identity.public_key.hex()

            def _tlv(t: int, v: bytes) -> bytes:
                return bytes([t, len(v)]) + v

            # naddr TLV: 0=identifier(slug), 1=relay(옵션·복수), 2=author(32B), 3=kind(4B BE)
            data = _tlv(0, slug.encode("utf-8"))
            for r in (self.settings.relays or DEFAULT_RELAYS)[:2]:
                data += _tlv(1, r.encode("ascii"))
            data += _tlv(2, bytes.fromhex(pubkey_hex))
            data += _tlv(3, (30023).to_bytes(4, "big"))

            five = bech32.convertbits(list(data), 8, 5)
            naddr = bech32.bech32_encode("naddr", five, bech32.Encoding.BECH32)
            return f"https://njump.me/{naddr}"
        except Exception as e:
            print(f"✗ IndieNet: naddr 링크 생성 실패({e}) — npub 폴백")
            try:
                return f"https://njump.me/{self.identity.public_key.bech32()}"
            except Exception:
                return None
