"""폰 컴패니언 알림 영속 저장.

폰 에이전트(NotificationListenerService)가 NIP-17 DM 으로 보낸 알림을 받아 SQLite 에 저장한다.
한방향 센서 피드 — 대화용 channel_poller 와 분리. 시스템 AI 가 사용자와 대화할 때 참조한다.

인가된 폰 신원: data/phone_agent.json 의 pubkey(들). 그 외 발신자 DM 은 무시.
"""
import json
import os
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
    # (2026-06-12 location/steps 상시 수집 폐기 — 위치는 [sense:here] 온디맨드 1회 조회로 분리.)
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


# === M3 하드웨어 다리: 폰 로컬 캡처 (Nostr 왕복 없이) ===
# 폰 프로파일에선 NotificationCaptureService(LocalSignals)가 적은 app-private JSONL 을
# 직접 읽는다. filesDir/signals/notifications.jsonl = dirname(INDIEBIZ_BASE_PATH)/signals/.
def _local_signals_path() -> Optional[str]:
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    if not base:
        return None
    return os.path.join(os.path.dirname(base), "signals", "notifications.jsonl")


def _recent_local(limit: int, pkg: Optional[str]) -> List[Dict]:
    path = _local_signals_path()
    items: List[Dict] = []
    if not path or not os.path.exists(path):
        return items
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") and d.get("type") != "notification":
                    continue
                if pkg and d.get("pkg") != pkg:
                    continue
                ts = d.get("posted_at") or d.get("received_at") or 0
                items.append({
                    "event_id": f"{d.get('pkg','')}:{ts}:{(d.get('title') or '')[:24]}",
                    "sender": "phone-local",
                    "pkg": d.get("pkg"),
                    "title": d.get("title"),
                    "body": d.get("text") or d.get("body"),
                    "posted_at": ts,
                    "received_at": ts,
                })
    except Exception as e:
        print(f"[phone_notifications] 로컬 읽기 실패: {e}")
        return []
    items.sort(key=lambda r: _to_ms(r.get("posted_at")), reverse=True)
    return items[:limit]


def recent(limit: int = 30, pkg: Optional[str] = None) -> List[Dict]:
    """최근 폰 알림(시간 내림차순). 시스템 AI 대화 참조용.

    폰 프로파일(INDIEBIZ_PROFILE=phone)=로컬 JSONL 직접 읽기(M3). PC=SQLite(Nostr 수신분)."""
    if os.environ.get("INDIEBIZ_PROFILE") == "phone":
        return _recent_local(limit, pkg)
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
        # (location/steps 타입은 2026-06-12 폐기 — 폰이 더 이상 상시 push 하지 않음.)
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
