"""IndieNet 릴레이 I/O·영구 캐시 계층 (2026-07-18 모듈화): _publish_event/_query_relays·글/DM 캐시."""
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


class IndieNetRelayMixin:
    """indienet.py 에서 verbatim 이동 — IndieNet 에 믹스인 합성(self 속성 공유)."""

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
                      relays: List[str] = None,
                      grace_after_first: float = None) -> List[dict]:
        """릴레이에 동일 REQ를 병렬 전송하고 이벤트를 수집·dedup한다.

        쓰기(_publish_event)가 전 릴레이에 fan-out 하는 것과 대칭으로, 읽기도
        전 릴레이를 조회한다. 단일 릴레이(relays[0])만 읽으면 그 릴레이가 prune한
        글은 다른 릴레이에 살아있어도 보이지 않는다.

        Args:
            req_filter: Nostr REQ 필터 (kinds/#t/#p/limit/since 등)
            accept: (event_dict) -> item_dict | None. None이면 제외.
            timeout: 릴레이별 EOSE 대기 최대 시간(초) — 조기 반환의 하드 상한
            relays: 조회할 relay 목록. 미지정 시 우리 일반 relay (NIP-17 수신은 DM relay 지정).
            grace_after_first: 첫 릴레이 응답 후 낙오 릴레이를 더 기다릴 유예(초, 기본 1.5).
                죽은 릴레이가 timeout 전체를 먹지 않도록 하는 조기 반환 창.
        Returns:
            event id 기준 dedup된 item 리스트
        """
        if not relays:
            relays = self.settings.relays if self.settings.relays else DEFAULT_RELAYS

        # 폰: Kotlin RelayClient.query 로 위임 (websocket 수집은 네이티브, accept 파싱은 여기서).
        if _ON_PHONE:
            try:
                import nostr_phone_bridge as bridge
                events = bridge.query_relays(req_filter, relays, timeout)
                collected_p: Dict[str, dict] = {}
                for event in events:
                    item = accept(event)
                    if item is not None:
                        eid = event.get('id')
                        if eid and eid not in collected_p:
                            collected_p[eid] = item
                return list(collected_p.values())
            except Exception as e:
                print(f"  폰 릴레이 조회 실패: {e}")
                return []

        collected: Dict[str, dict] = {}
        lock = threading.Lock()
        total = len(relays)
        all_done = threading.Event()          # 모든 릴레이가 EOSE/에러/종료
        first_eose_at = [None]                # 첫 응답(EOSE) 시각 — 낙오 릴레이 유예 기준
        finished = [0]                        # 완료(성공/실패 무관) 릴레이 수

        def _mark_finished():
            with lock:
                finished[0] += 1
                if finished[0] >= total:
                    all_done.set()

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
                        with lock:
                            if first_eose_at[0] is None:
                                first_eose_at[0] = time.monotonic()
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
            finally:
                _mark_finished()

        for relay_url in relays:
            t = threading.Thread(target=_query_one, args=(relay_url,), daemon=True)
            t.start()

        # 조기 반환: (1) 전 릴레이 완료, 또는 (2) 첫 응답 후 grace 만큼만 낙오 릴레이를
        # 더 기다리고 반환. 죽은 릴레이 하나가 timeout(=10초)을 통째로 먹지 않게 한다.
        # replaceable(kind:0/10002 등)은 아무 릴레이나 하나면 충분하고, 피드도 살아있는
        # 릴레이는 수백 ms 안에 응답하므로 grace 안에 다 잡힌다.
        grace = grace_after_first if grace_after_first is not None else 1.5
        start = time.monotonic()
        while not all_done.is_set():
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                break
            fe = first_eose_at[0]
            if fe is not None and (time.monotonic() - fe) >= grace:
                break
            all_done.wait(timeout=0.1)

        return list(collected.values())

    def fetch_posts(self, limit: int = 50, since: int = None) -> List[dict]:
        """
        IndieNet 활성 보드 피드 조회 (전 릴레이 조회 + 영구 캐시 합집합).

        활성 보드(settings.active_board, 기본 #indienet)에 위임 — 보드 '전환'이
        게시 기본값뿐 아니라 조회에도 반영된다. 같은 캐시 테이블에 보드 글이 섞여
        쌓이지만, 태그 필터로 해당 보드 글만 반환된다.
        """
        active = (getattr(self.settings, "active_board", None) or "indienet")
        return self.fetch_board_posts(hashtag=active, limit=limit, since=since)
