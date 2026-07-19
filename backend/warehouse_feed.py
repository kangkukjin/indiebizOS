"""창고 피드 — 이웃 공유창고의 매니페스트를 주기 폴링해 변화를 타임라인으로 쌓는다.

설계(2026-07-18 대화, foaf-discovery-routing):
- 순수 기계층(AI·토큰 0): GET /manifest → 경로·mtime diff → 저장. 냄새의 수집=기계,
  냄새의 해석=AI(피드를 읽는 건 사람 또는 필요할 때의 AI).
- 스냅샷 전체 보존: 피드(변화)와 검색(현재 상태)이 같은 DB 의 두 읽기 — 스냅샷 테이블이
  곧 "내 동네 전체 파일명 색인"(전수 키워드 조사, 검색 사다리 1층).
- 창고이웃 등기부 = business.db contacts(contact_type='warehouse') — 창고주소도 이메일처럼
  연락방법의 하나(2026-07-18 2차 개정). 이 모듈의 키 = 창고 url(창고=주소가 정체).
- 비용 = asker-pays: 내가 읽고 싶어 내가 폴링. 이웃 쪽엔 정적 서빙 ~0 뿐.
- 첫 폴링은 kind='seed'(현재 파일 전체 — 팔로우 직후 지난 트윗 보이듯), 이후 new/changed.
"""
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _ROOT / "data" / "warehouse_feed.db"
POLL_INTERVAL = 30 * 60          # 초 — 배경 폴링 주기 (매니페스트=작은 JSON 이라 가벼움)
_REQUEST_TIMEOUT = 20
_UA = "indiebizOS-warehouse-feed/1.0"

_db_lock = threading.Lock()
_poller_thread: Optional[threading.Thread] = None


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, _conn() as c:
        # v1(neighbor_id 키) 캐시 폐기 — 창고=url 이 정체(연락처 개정). 캐시라 재폴링이 복구.
        try:
            cols = [r["name"] for r in c.execute("PRAGMA table_info(snapshots)").fetchall()]
            if cols and "wh_url" not in cols:
                c.executescript("DROP TABLE IF EXISTS snapshots; DROP TABLE IF EXISTS feed; "
                                "DROP TABLE IF EXISTS poll_status;")
        except Exception:
            pass
        c.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots(
                wh_url  TEXT NOT NULL,
                path    TEXT NOT NULL,
                mtime   TEXT,
                bytes   INTEGER,
                url     TEXT,
                seen_at TEXT,
                PRIMARY KEY(wh_url, path)
            );
            CREATE TABLE IF NOT EXISTS feed(
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                wh_url  TEXT NOT NULL,
                path    TEXT NOT NULL,
                mtime   TEXT,
                bytes   INTEGER,
                url     TEXT,
                kind    TEXT NOT NULL,      -- seed | new | changed
                seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS poll_status(
                wh_url         TEXT PRIMARY KEY,
                last_poll      TEXT,
                ok             INTEGER,
                error          TEXT,
                file_count     INTEGER,
                title          TEXT,
                has_restricted INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_feed_seen ON feed(seen_at DESC, mtime DESC);
            CREATE INDEX IF NOT EXISTS idx_feed_wh ON feed(wh_url);
        """)
        # 좋아요 컬럼 마이그레이션(2026-07-19) — 매니페스트 likes 를 스냅샷에 담아 피드에 하트.
        for tbl in ("snapshots", "feed"):
            try:
                c.execute(f"ALTER TABLE {tbl} ADD COLUMN likes INTEGER")
            except Exception:
                pass  # 이미 있음


def normalize_base(url: str) -> str:
    """사용자 입력 주소를 창고 베이스 URL 로 정규화 (…/manifest, 뒤 슬래시 허용)."""
    u = (url or "").strip()
    if not u:
        return ""
    if not (u.startswith("http://") or u.startswith("https://")):
        u = "https://" + u
    u = u.rstrip("/")
    if u.endswith("/manifest"):
        u = u[: -len("/manifest")]
    return u


_bm_instance = None


def _bm():
    global _bm_instance
    if _bm_instance is None:
        from business_manager import BusinessManager
        _bm_instance = BusinessManager()
    return _bm_instance


def fetch_manifest(url: str) -> Dict:
    """창고 매니페스트 한 번 가져오기 (등록 시 제목 유도 등에도 사용)."""
    base = normalize_base(url)
    r = requests.get(base + "/manifest", timeout=_REQUEST_TIMEOUT,
                     headers={"User-Agent": _UA})
    r.raise_for_status()
    return r.json()


def _migrate_warehouse(old: str, new: str) -> Dict:
    """이사 치유 — 등기부(contacts warehouse 행)의 옛 주소를 새 주소로, 캐시(wh_url 키)도 이관.

    매니페스트 moved_to 를 본 폴러가 부른다. 새 주소에 이미 스냅샷이 있으면(양쪽을 따로
    등록했던 경우) 옛 캐시는 버린다 — 캐시는 재폴링이 복구하는 파생물이라 안전.
    """
    old, new = normalize_base(old), normalize_base(new)
    healed = {"contacts": 0, "cache": "none"}
    try:
        bm = _bm()
        for ct in bm.get_warehouse_contacts():
            if normalize_base(ct.get("url") or "") == old:
                bm.update_contact(ct["contact_id"], contact_value=new)
                healed["contacts"] += 1
    except Exception as e:
        healed["contacts_error"] = str(e)
    with _db_lock, _conn() as c:
        has_new = c.execute("SELECT 1 FROM snapshots WHERE wh_url=? LIMIT 1", (new,)).fetchone()
        if has_new:
            c.execute("DELETE FROM snapshots WHERE wh_url=?", (old,))
            c.execute("DELETE FROM feed WHERE wh_url=?", (old,))
            c.execute("DELETE FROM poll_status WHERE wh_url=?", (old,))
            healed["cache"] = "dropped_old"
        else:
            c.execute("UPDATE snapshots SET wh_url=? WHERE wh_url=?", (new, old))
            c.execute("UPDATE feed SET wh_url=? WHERE wh_url=?", (new, old))
            c.execute("DELETE FROM poll_status WHERE wh_url=?", (old,))
            healed["cache"] = "rekeyed"
    return healed


def poll_warehouse(url: str, _hop: int = 0) -> Dict:
    """창고 하나를 폴링해 스냅샷 갱신 + 변화를 피드에 기록. AI 없음 — 순수 diff.

    매니페스트에 moved_to(이사 공지)가 있으면 등기부·캐시를 새 주소로 치유하고
    새 주소를 이어서 폴링한다(1홉만 — 공지 루프 방어)."""
    _init_db()
    base = normalize_base(url)
    now = datetime.now().isoformat(timespec="seconds")
    try:
        data = fetch_manifest(base)
        moved = normalize_base(data.get("moved_to") or "")
        if moved and moved != base and _hop == 0:
            healed = _migrate_warehouse(base, moved)
            print(f"[창고피드] 이사 공지 감지: {base} → {moved} (치유: {healed})")
            return poll_warehouse(moved, _hop=1)
        files = data.get("files") or []
        title = data.get("title") or ""
        has_restricted = 1 if data.get("has_restricted") else 0
        # 상대가 목록을 상한에서 잘랐다고 신고하면 "안 보이는 것"과 "사라진 것"을 가를 수 없다.
        truncated = bool(data.get("truncated"))
    except Exception as e:
        with _db_lock, _conn() as c:
            c.execute("""
                INSERT INTO poll_status(wh_url, last_poll, ok, error)
                VALUES(?, ?, 0, ?)
                ON CONFLICT(wh_url) DO UPDATE SET last_poll=?, ok=0, error=?
            """, (base, now, str(e), now, str(e)))
        return {"ok": False, "error": str(e), "url": base}

    new_events = 0
    with _db_lock, _conn() as c:
        rows = c.execute("SELECT path, mtime FROM snapshots WHERE wh_url=?", (base,)).fetchall()
        existing = {row["path"]: row["mtime"] for row in rows}
        first_poll = not existing
        seen_paths = set()
        for f in files:
            path = f.get("name")
            if not path:
                continue
            seen_paths.add(path)
            mtime = f.get("mtime") or ""
            fbytes = f.get("bytes")
            furl = f.get("url") or f"{base}/f?path={quote(path)}"
            flikes = f.get("likes") or 0
            if path not in existing:
                kind = "seed" if first_poll else "new"
            elif (existing[path] or "") != mtime:
                kind = "changed"
            else:
                kind = None
            c.execute("""
                INSERT INTO snapshots(wh_url, path, mtime, bytes, url, seen_at, likes)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(wh_url, path) DO UPDATE SET
                    mtime=excluded.mtime, bytes=excluded.bytes,
                    url=excluded.url, seen_at=excluded.seen_at, likes=excluded.likes
            """, (base, path, mtime, fbytes, furl, now, flikes))
            if kind:
                c.execute("""
                    INSERT INTO feed(wh_url, path, mtime, bytes, url, kind, seen_at, likes)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """, (base, path, mtime, fbytes, furl, kind, now, flikes))
                new_events += 1
        # 매니페스트에서 사라진 파일 = 스냅샷에서도 제거 (조용히 — 트윗 삭제처럼 피드 무이벤트)
        # ★단 절단 신고를 받았으면 삭제 판정을 보류한다. 상한에 밀려 목록에서 빠진 것뿐일 수
        #   있고, 그걸 지우면 다음 폴링에 같은 파일이 new 로 되살아나 피드가 요동친다.
        gone = [] if truncated else [p for p in existing if p not in seen_paths]
        for p in gone:
            c.execute("DELETE FROM snapshots WHERE wh_url=? AND path=?", (base, p))
        c.execute("""
            INSERT INTO poll_status(wh_url, last_poll, ok, error, file_count, title, has_restricted)
            VALUES(?, ?, 1, NULL, ?, ?, ?)
            ON CONFLICT(wh_url) DO UPDATE SET
                last_poll=?, ok=1, error=NULL, file_count=?, title=?, has_restricted=?
        """, (base, now, len(files), title, has_restricted,
              now, len(files), title, has_restricted))
    return {"ok": True, "url": base, "file_count": len(files),
            "new_events": new_events, "title": title}


def poll_all() -> List[Dict]:
    """등기부(창고 연락처)의 모든 창고를 폴링 — 같은 주소는 한 번만."""
    results = []
    try:
        contacts = _bm().get_warehouse_contacts()
    except Exception as e:
        return [{"ok": False, "error": f"등기부 조회 실패: {e}"}]
    seen = set()
    for ct in contacts:
        base = normalize_base(ct["url"])
        if not base or base in seen:
            continue
        seen.add(base)
        results.append(poll_warehouse(base))
    return results


GROUP_MIN = 3           # 한 폴링에서 같은 폴더에 이만큼 이상 = 한 줄로 접는다
GROUP_ITEMS_CAP = 20    # 접힌 줄이 품고 가는 내역 수(개수는 count 가 사실대로 말한다)
_SCAN_CAP = 5000        # 묶기 위해 훑는 원장 행 수 상한


def _group_feed(rows: List[Dict], limit: int) -> List[Dict]:
    """폴더 단위로 접기 — 폴더 하나 던져넣은 게 이웃 타임라인에 N 연속 트윗이 되는 걸 막는다.

    묶는 키 = (창고, 폴링 시각, 종류, 최상위 폴더). seen_at 이 한 폴링에서 같은 값이므로
    "이번에 이 폴더에 들어온 것들"이 자연히 한 덩어리가 된다. 원장(feed 테이블)은 파일
    단위 그대로 두고 여기서 표현만 접는다 — 스키마 변경 없음, 기준 바꾸기도 쉽다.

    루트 파일(경로에 / 없음)은 묶지 않는다 — 그건 낱개 트윗이 맞다.
    """
    buckets: Dict[tuple, Dict] = {}
    order: List[tuple] = []
    for r in rows:
        path = r.get("path") or ""
        folder = path.split("/")[0] if "/" in path else None
        if folder is None:
            key = ("__solo__", r.get("id"))
        else:
            key = (r.get("wh_url"), r.get("seen_at"), r.get("kind"), folder)
        if key not in buckets:
            buckets[key] = {"folder": folder, "rows": []}
            order.append(key)
        buckets[key]["rows"].append(r)

    out: List[Dict] = []
    for key in order:
        b = buckets[key]
        members = b["rows"]
        if b["folder"] is None or len(members) < GROUP_MIN:
            out.extend(members)          # 접을 만큼이 아니면 있는 그대로
        else:
            head = members[0]
            out.append({
                "group": True,
                "folder": b["folder"],
                "path": b["folder"],
                "count": len(members),
                "bytes": sum((m.get("bytes") or 0) for m in members),
                "mtime": max((m.get("mtime") or "") for m in members),
                "kind": head.get("kind"),
                "wh_url": head.get("wh_url"),
                "seen_at": head.get("seen_at"),
                "url": head.get("url"),
                "items": members[:GROUP_ITEMS_CAP],
            })
        if len(out) >= limit:
            break
    return out[:limit]


def get_feed(limit: int = 100, wh_url: Optional[str] = None,
             group: bool = True, wh_urls: Optional[List[str]] = None) -> List[Dict]:
    """피드 조회 — 내가 새로 본 순(seen_at) → 파일 자체 시간(mtime) 순.

    group=True 면 폴더 단위로 접어서 limit '줄'을 채운다. 접기 전 원장을 넉넉히 훑어야
    (한 폴더 폭주가 창을 다 먹지 않게) 이전 소식까지 같이 올라온다.
    wh_urls=허용 집합(레벨·즐겨찾기 필터) — 접기 *전에* 걸러야 필터가 limit 를 안 갉아먹는다.
    """
    _init_db()
    lim = max(1, min(500, limit))
    q = "SELECT * FROM feed"
    params: list = []
    if wh_url:
        q += " WHERE wh_url=?"
        params.append(normalize_base(wh_url))
    elif wh_urls is not None:
        if not wh_urls:
            return []
        q += f" WHERE wh_url IN ({','.join('?' * len(wh_urls))})"
        params.extend(wh_urls)
    q += " ORDER BY seen_at DESC, mtime DESC, id DESC LIMIT ?"
    params.append(_SCAN_CAP if group else lim)
    with _db_lock, _conn() as c:
        rows = [dict(r) for r in c.execute(q, params).fetchall()]
    return _group_feed(rows, lim) if group else rows


def _match_rank(path: str, q: str) -> int:
    """이름 일치의 질 — 낮을수록 좋다. 폴더 경로보다 파일 이름의 일치를 높게 본다.

    '축구' 로 찾을 때 `축구.md` 가 `2024_지역행사_축구부_명단_최종.xlsx` 보다 앞서야 한다.
    """
    name = path.rsplit("/", 1)[-1].lower()
    stem = name.rsplit(".", 1)[0] if "." in name else name
    ql = q.lower()
    if stem == ql:
        return 0                                  # 이름이 곧 검색어
    if stem.startswith(ql) or name.startswith(ql):
        return 1                                  # 이름이 검색어로 시작
    if ql in name:
        return 2                                  # 이름 안에 있음
    return 3                                      # 폴더 경로에서만 걸림


def search_snapshots(query: str, limit: int = 100, sort: str = "recent",
                     wh_urls: Optional[List[str]] = None) -> List[Dict]:
    """전수 키워드 조사(검색 사다리 1층) — 이웃 전부의 현재 파일명에서 부분일치.

    sort: recent=최신순(기본) / match=이름 일치순. 순위는 파이썬에서 매긴다 —
    자르기 전에 순위를 매겨야 해서(SQL LIMIT 뒤 정렬은 상위를 놓친다).
    wh_urls=허용 집합(레벨·즐겨찾기 필터, 피드와 같은 신뢰 축).
    """
    _init_db()
    q = (query or "").strip()
    if not q:
        return []
    cap = max(1, min(500, limit))
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = "path LIKE ? ESCAPE '\\'"
    params: list = [like]
    if wh_urls is not None:
        if not wh_urls:
            return []
        where += f" AND wh_url IN ({','.join('?' * len(wh_urls))})"
        params.extend(wh_urls)
    with _db_lock, _conn() as c:
        rows = [dict(r) for r in c.execute(f"""
            SELECT * FROM snapshots WHERE {where}
            ORDER BY mtime DESC LIMIT 1000
        """, params).fetchall()]
    if sort == "match":
        # SQL 이 이미 mtime DESC 로 주고 파이썬 정렬은 안정적 → 같은 순위 안에서는 최신순이 유지된다.
        rows.sort(key=lambda r: _match_rank(r["path"], q))
    return rows[:cap]


def get_status_map() -> Dict[str, Dict]:
    """창고(url)별 마지막 폴링 상태 (피드 UI 의 이웃 카드용)."""
    _init_db()
    with _db_lock, _conn() as c:
        return {r["wh_url"]: dict(r)
                for r in c.execute("SELECT * FROM poll_status").fetchall()}


def forget_warehouse(url: str) -> None:
    """창고 캐시(스냅샷·피드·상태) 삭제 — 등기부에서 창고 연락처를 뗄 때."""
    _init_db()
    base = normalize_base(url)
    with _db_lock, _conn() as c:
        c.execute("DELETE FROM snapshots WHERE wh_url=?", (base,))
        c.execute("DELETE FROM feed WHERE wh_url=?", (base,))
        c.execute("DELETE FROM poll_status WHERE wh_url=?", (base,))


def start_poller() -> None:
    """배경 폴링 스레드 시작 (멱등). 창고 연락처가 없으면 조용히 잔다."""
    global _poller_thread
    if _poller_thread is not None and _poller_thread.is_alive():
        return

    def _loop():
        time.sleep(90)  # 서버 워밍업 뒤 첫 폴링
        while True:
            try:
                poll_all()
            except Exception as e:
                print(f"[창고피드] 폴링 오류 (무시): {e}")
            time.sleep(POLL_INTERVAL)

    _poller_thread = threading.Thread(target=_loop, daemon=True, name="warehouse-feed-poller")
    _poller_thread.start()
