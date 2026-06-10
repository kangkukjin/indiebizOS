"""폰 컴패니언 알림 영속 저장.

폰 에이전트(NotificationListenerService)가 NIP-17 DM 으로 보낸 알림을 받아 SQLite 에 저장한다.
한방향 센서 피드 — 대화용 channel_poller 와 분리. 시스템 AI 가 사용자와 대화할 때 참조한다.

인가된 폰 신원: data/phone_agent.json 의 pubkey(들). 그 외 발신자 DM 은 무시.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional


def _to_ms(ts) -> int:
    """타임스탬프를 밀리초로 정규화. 폰 payload(ms)와 Nostr created_at(초)가 섞여
    들어오므로 단위를 일원화한다 (10^12 미만이면 초로 보고 *1000)."""
    try:
        v = int(ts or 0)
    except (TypeError, ValueError):
        return 0
    if v and v < 1_000_000_000_000:  # 13자리 미만 = 초 단위
        v *= 1000
    return v


DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "phone_notifications.db"
CONFIG_PATH = DATA_DIR / "phone_agent.json"


def _phone_pubkeys() -> set:
    """인가된 폰 에이전트 pubkey(hex) 집합."""
    try:
        d = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        keys = d.get("pubkeys") or ([d["pubkey"]] if d.get("pubkey") else [])
        return {k.lower() for k in keys}
    except Exception:
        return set()


def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS notifications (
            event_id    TEXT PRIMARY KEY,
            sender      TEXT,
            pkg         TEXT,
            title       TEXT,
            body        TEXT,
            posted_at   INTEGER,
            received_at INTEGER,
            raw         TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS locations (
            event_id    TEXT PRIMARY KEY,
            sender      TEXT,
            lat         REAL,
            lng         REAL,
            accuracy    REAL,
            captured_at INTEGER,
            received_at INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS steps (
            date        TEXT PRIMARY KEY,
            sender      TEXT,
            steps       INTEGER,
            cumulative  INTEGER,
            captured_at INTEGER,
            received_at INTEGER
        )"""
    )
    return conn


def store(event_id: str, sender: str, payload: dict, posted_at, received_at) -> bool:
    """새 알림 저장. 이미 있으면(event_id 중복) False."""
    try:
        conn = _conn()
        cur = conn.execute(
            "INSERT OR IGNORE INTO notifications "
            "(event_id, sender, pkg, title, body, posted_at, received_at, raw) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (event_id, sender, payload.get("pkg", ""), payload.get("title", ""),
             payload.get("text", ""), _to_ms(payload.get("posted_at") or posted_at),
             _to_ms(received_at), json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        inserted = cur.rowcount > 0
        conn.close()
        return inserted
    except Exception as e:
        print(f"[phone_notifications] store 실패: {e}")
        return False


def store_location(event_id: str, sender: str, payload: dict, received_at) -> bool:
    try:
        conn = _conn()
        cur = conn.execute(
            "INSERT OR IGNORE INTO locations "
            "(event_id, sender, lat, lng, accuracy, captured_at, received_at) VALUES (?,?,?,?,?,?,?)",
            (event_id, sender, payload.get("lat"), payload.get("lng"),
             payload.get("accuracy"), int(payload.get("captured_at") or 0), int(received_at)),
        )
        conn.commit()
        inserted = cur.rowcount > 0
        conn.close()
        return inserted
    except Exception as e:
        print(f"[phone_notifications] store_location 실패: {e}")
        return False


def store_steps(sender: str, payload: dict, received_at) -> bool:
    """걸음수는 날짜당 1행 (최신값으로 갱신)."""
    try:
        conn = _conn()
        conn.execute(
            "INSERT OR REPLACE INTO steps "
            "(date, sender, steps, cumulative, captured_at, received_at) VALUES (?,?,?,?,?,?)",
            (payload.get("date"), sender, int(payload.get("steps") or 0),
             int(payload.get("cumulative") or 0), int(payload.get("captured_at") or 0), int(received_at)),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[phone_notifications] store_steps 실패: {e}")
        return False


def recent_locations(limit: int = 50) -> List[Dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT lat, lng, accuracy, captured_at, received_at FROM locations "
        "ORDER BY COALESCE(NULLIF(captured_at,0), received_at) DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    cols = ["lat", "lng", "accuracy", "captured_at", "received_at"]
    return [dict(zip(cols, r)) for r in rows]


def recent_steps(limit: int = 30) -> List[Dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT date, steps, cumulative, captured_at FROM steps ORDER BY date DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    cols = ["date", "steps", "cumulative", "captured_at"]
    return [dict(zip(cols, r)) for r in rows]


def recent(limit: int = 30, pkg: Optional[str] = None) -> List[Dict]:
    """최근 폰 알림(시간 내림차순). 시스템 AI 대화 참조용."""
    conn = _conn()
    q = "SELECT event_id, sender, pkg, title, body, posted_at, received_at FROM notifications"
    args: list = []
    if pkg:
        q += " WHERE pkg = ?"
        args.append(pkg)
    q += " ORDER BY COALESCE(NULLIF(posted_at,0), received_at) DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(q, args).fetchall()
    conn.close()
    cols = ["event_id", "sender", "pkg", "title", "body", "posted_at", "received_at"]
    return [dict(zip(cols, r)) for r in rows]


def ingest_once(log=print) -> int:
    """릴레이에서 폰 DM 을 가져와 새 알림을 저장. 저장 개수 반환."""
    try:
        from indienet import get_indienet
    except Exception:
        return 0
    indienet = get_indienet()
    if not getattr(indienet, "_initialized", False):
        return 0
    allowed = _phone_pubkeys()
    if not allowed:
        return 0
    try:
        dms = indienet.fetch_dms_nip17(limit=50)
    except Exception as e:
        log(f"[phone_notifications] fetch 실패: {e}")
        return 0
    now = int(time.time())
    n = 0
    for dm in dms:
        sender = (dm.get("from") or "").lower()
        if sender not in allowed:
            continue
        try:
            payload = json.loads(dm.get("content") or "")
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        t = payload.get("type")
        if t in ("notification", "test"):
            if store(dm.get("id"), sender, payload, dm.get("created_at"), now):
                n += 1
        elif t == "location":
            if store_location(dm.get("id"), sender, payload, now):
                n += 1
        elif t == "steps":
            if store_steps(sender, payload, now):
                n += 1
    if n:
        log(f"[phone_notifications] 폰 신호 {n}건 저장")
    return n


_poller_thread = None


def start_poller(interval: int = 60, log=print):
    """백그라운드 폴러 시작 (중복 기동 방지)."""
    global _poller_thread
    if _poller_thread and _poller_thread.is_alive():
        return

    def loop():
        time.sleep(8)  # 부팅 안정화
        while True:
            try:
                ingest_once(log)
            except Exception as e:
                log(f"[phone_notifications] poll 오류: {e}")
            time.sleep(interval)

    _poller_thread = threading.Thread(target=loop, daemon=True)
    _poller_thread.start()
    log("[phone_notifications] 폴러 시작")
