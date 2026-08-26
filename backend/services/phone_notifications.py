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


DATA_DIR = Path(__file__).parent.parent.parent / "data"
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
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
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
                if not isinstance(d, dict):
                    continue  # 유효 JSON 이지만 객체가 아닌 줄
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


# ── PC 에서 폰 포획소 읽기 (USB) ──
# 폰의 NotificationCaptureService 가 적는 app-private JSONL 을 adb run-as 로 당겨 온다.
# ★같은 경로를 finance-record/finance_sync.py 도 읽는다 — 경로를 바꾸면 그쪽도 함께.
_CAPTURE_PKG = "com.indiebiz.phoneagent"
_CAPTURE_PATH = "files/signals/notifications.jsonl"


def _recent_via_adb(limit: int, pkg: Optional[str]) -> Optional[List[Dict]]:
    """USB 로 폰 포획소를 읽어 최근 알림 반환. None = 폰 미연결이거나 포획소 없음."""
    import subprocess
    # ★adb 경로 후보는 file_index 가 이미 쥔 OS 이음매다 — 여기 박으면 몸 독립 코어에
    # OS 경로가 흩어진다(빌드의 OS-가드가 실제로 잡아냈다). 이음매 하나만 쓴다.
    try:
        from file_index import _adb_bin
    except Exception:
        return None
    adb = _adb_bin()
    if not adb:
        return None
    try:
        st = subprocess.run([adb, "get-state"], capture_output=True, timeout=8)
        if b"device" not in st.stdout:
            return None
        r = subprocess.run([adb, "shell", "run-as", _CAPTURE_PKG, "cat", _CAPTURE_PATH],
                           capture_output=True, timeout=20)
    except Exception:
        return None
    out = r.stdout.decode("utf-8", "ignore")
    if r.returncode != 0 or "No such file" in out or not out.strip():
        return None
    items: List[Dict] = []
    for line in out.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("type", "notification") != "notification":
            continue
        if pkg and d.get("pkg") != pkg:
            continue
        ts = _to_ms(d.get("posted_at") or d.get("received_at") or 0)
        items.append({
            "event_id": f"{d.get('pkg','')}:{ts}:{(d.get('title') or '')[:24]}",
            "sender": "phone-capture",
            "pkg": d.get("pkg"),
            "title": d.get("title"),
            "body": d.get("text") or d.get("body"),
            "posted_at": ts,
            "received_at": _to_ms(d.get("received_at") or ts),
        })
    items.sort(key=lambda r: _to_ms(r.get("posted_at")), reverse=True)
    return items[:limit]


def recent(limit: int = 30, pkg: Optional[str] = None) -> List[Dict]:
    """최근 폰 알림(시간 내림차순). 시스템 AI 대화 참조용.

    우선순위: 폰 프로파일=로컬 JSONL 직접 / PC=USB 포획소 / 그것도 없으면 SQLite.
    ★SQLite 는 2026-06-22 에 폐기된 옛 Nostr 수신분이라 **얼어붙어 있다**(2026-08-17 실측:
    success=true 로 72일 전 데이터를 현재인 양 반환). 과거 기록으로만 남기고 마지막에 둔다."""
    if os.environ.get("INDIEBIZ_PROFILE") == "phone":
        return _recent_local(limit, pkg)
    via_usb = _recent_via_adb(limit, pkg)
    if via_usb is not None:
        return via_usb
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
