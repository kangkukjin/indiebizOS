"""가이드 신선도 원장 — 가이드는 '절차 기억'이고, 기억처럼 낡는다.

## 왜 있나

가이드(`data/guides/*.md`)는 "이 일을 제대로 하려면 이렇게 해야 한다"는 기억이다.
그런데 7종 기억 중 **정리 패스가 없는 유일한 기억**이었다 — 심층메모리·해마·포식기억은
주간 번들이 정리하고, 액션 desc 는 의미 드리프트 점검을 받는데, 그 desc 의 10~30배
길이로 같은 액션을 설명하는 가이드는 순찰이 0이었다(2026-08-17 정리에서 79→67개,
81KB 를 걷어내며 드러남).

## 무엇을 재나 — 날짜 셋

- **작성**(born): 최초로 들어온 날
- **최종수정**(updated): 마지막으로 고친 날 = "이 날 *틀린 게 발견됐다*"
- **무수정 사용**(clean use): 최종수정 *이후*에 주입된 횟수 = "그 뒤로 실전에서 안 고쳐졌다"

두 번째와 세 번째의 순서가 판단을 만든다:

| 상태 | 읽는 법 |
|---|---|
| 무수정 사용 > 0 | 고친 뒤로 N번 쓰였는데 안 고쳐졌다 → 상대적으로 신뢰 |
| 최종수정 후 사용 0 | 고쳤지만 아직 실전 검증 전 → 미검증 |
| 오래됐고 사용 0 | 방치 → 강하게 의심 |

나이만으로는 못 정한다: 67일 된 가이드가 그동안 12번 무수정으로 쓰였다면 오히려
검증된 것이고, 0번이면 방치다.

## ★"무수정 사용"은 "맞았다"가 아니라 "안 고쳐졌다"이다

틀렸는데 아무도 안 고쳤을 수 있다. `sense:search_local` 이 계수 19를 기록하고도
결과를 낸 적이 없었던 것과 같은 부류다(2026-08-15 실측). 그래서 이 원장이 내는 것은
**깃발이지 판결이 아니고**, 표식 문구도 "검증됨"이 아니라 "무수정 사용"이라고
사실만 적는다. 판단은 읽는 쪽(AI·사람)이 한다.

## 파생 우선

날짜는 저장하지 않고 **git 에서 파생**한다(수동 날짜 필드는 그 자체가 낡는 기억이라,
지금 고치는 문제를 한 층 위에 복제한다). git 이 없는 몸(설치본)에서는 파일 mtime 으로
degrade — 정확도는 떨어져도 "언제쯤"은 남는다.
"""

import json
import logging
import os
import sqlite3
import subprocess
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parents[2] / "data"
GUIDES_DIR = DATA_PATH / "guides"
DB_PATH = DATA_PATH / "guide_usage.db"
CACHE_PATH = DATA_PATH / "guide_dates_cache.json"

_lock = threading.Lock()
_date_cache: Optional[Dict[str, Dict]] = None

# 오래됐다고 볼 기준(일). 이 이상이면서 무수정 사용이 0이면 주의 문구를 붙인다.
STALE_DAYS = 60


# ---------------------------------------------------------------- 사용 기록

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS guide_use (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               guide TEXT NOT NULL,
               used_on TEXT NOT NULL,          -- YYYY-MM-DD
               origin TEXT NOT NULL DEFAULT 'agent',
               n INTEGER NOT NULL DEFAULT 1,
               UNIQUE(guide, used_on, origin)
           )"""
    )
    return conn


_injected = threading.local()


def mark_injected(guide: str) -> None:
    """이번 턴에 주입된 가이드를 기억해 둔다 (증류 4단계가 회수).

    ★threading.local 이라 스레드에 자동 전파되지 않는다 — thread_context 와 같은 기질이고
    같은 함정이다. 증류가 백그라운드 스레드로 내려가므로, **메인 컨텍스트에서**
    take_injected() 로 스냅샷해 값으로 넘겨야 한다(cognitive_distill 이 그렇게 한다).
    """
    try:
        cur = getattr(_injected, "names", None)
        if cur is None:
            cur = _injected.names = []
        if guide not in cur:
            cur.append(guide)
    except Exception:
        pass


def take_injected() -> List[str]:
    """이번 턴 주입 목록을 회수하고 비운다(다음 턴으로 새지 않게)."""
    try:
        cur = getattr(_injected, "names", None) or []
        _injected.names = []
        return list(cur)
    except Exception:
        return []


def record_use(guide: str, origin: str = "agent") -> None:
    """가이드가 프롬프트에 주입됐음을 기록 (일 단위 집계).

    ★origin 을 반드시 남긴다 — 액션 사용계수가 자가점검 순찰에 55% 오염돼
    은퇴 판단을 왜곡했던 전례(2026-08-15)가 있다. 순찰이 부풀린 숫자를
    '신선하다'로 오독하면 안 된다. 신선도 계산은 origin='agent' 만 센다.
    """
    if not guide:
        return
    try:
        today = date.today().isoformat()
        with _lock, _conn() as conn:
            conn.execute(
                "INSERT INTO guide_use(guide, used_on, origin, n) VALUES(?,?,?,1) "
                "ON CONFLICT(guide, used_on, origin) DO UPDATE SET n = n + 1",
                (guide, today, origin or "agent"),
            )
    except Exception as e:  # 기록 실패가 프롬프트 조립을 막으면 안 된다
        logger.debug(f"[guide_registry] 사용 기록 실패 (무시): {e}")


def record_review(guide: str) -> None:
    """검토했음을 기록 — 고칠 게 없었어도 남긴다.

    ★"검토했고 고칠 게 없었다"가 **"아무도 안 봤다"와 구별되는 정보**다.
    이 기록이 쿨다운의 근거이자, 신선도 표식의 '무수정 사용'을 진짜 신호로 만든다.
    """
    try:
        with _lock, _conn() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS guide_review (
                       guide TEXT PRIMARY KEY, reviewed_on TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 1)"""
            )
            conn.execute(
                "INSERT INTO guide_review(guide, reviewed_on, n) VALUES(?,?,1) "
                "ON CONFLICT(guide) DO UPDATE SET reviewed_on=excluded.reviewed_on, n = n + 1",
                (guide, date.today().isoformat()),
            )
    except Exception as e:
        logger.debug(f"[guide_registry] 검토 기록 실패 (무시): {e}")


def last_review(guide: str) -> Optional[str]:
    """마지막 검토일(YYYY-MM-DD). 없으면 None."""
    try:
        with _conn() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS guide_review (
                       guide TEXT PRIMARY KEY, reviewed_on TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 1)"""
            )
            row = conn.execute(
                "SELECT reviewed_on FROM guide_review WHERE guide=?", (guide,)
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _uses_since(guide: str, since: Optional[str]) -> Dict:
    """since(YYYY-MM-DD) *이후*의 origin='agent' 사용 집계."""
    try:
        with _conn() as conn:
            if since:
                rows = conn.execute(
                    "SELECT SUM(n), MAX(used_on) FROM guide_use "
                    "WHERE guide=? AND origin='agent' AND used_on > ?",
                    (guide, since),
                ).fetchone()
            else:
                rows = conn.execute(
                    "SELECT SUM(n), MAX(used_on) FROM guide_use "
                    "WHERE guide=? AND origin='agent'",
                    (guide,),
                ).fetchone()
        return {"count": int(rows[0] or 0), "last": rows[1]}
    except Exception:
        return {"count": 0, "last": None}


# ---------------------------------------------------------------- 날짜 파생

def _git_dates(rel_path: str) -> Optional[Dict[str, str]]:
    """git 에서 최초 추가일·최종 수정일. git 없는 몸이면 None."""
    try:
        born = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%ad", "--date=short", "-1", "--", rel_path],
            capture_output=True, text=True, timeout=5, cwd=str(DATA_PATH.parent),
        ).stdout.strip()
        upd = subprocess.run(
            ["git", "log", "--format=%ad", "--date=short", "-1", "--", rel_path],
            capture_output=True, text=True, timeout=5, cwd=str(DATA_PATH.parent),
        ).stdout.strip()
        if born or upd:
            return {"born": born or upd, "updated": upd or born, "src": "git"}
    except Exception:
        pass
    return None


def _load_cache() -> Dict[str, Dict]:
    global _date_cache
    if _date_cache is not None:
        return _date_cache
    try:
        _date_cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _date_cache = {}
    return _date_cache


def _save_cache() -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps(_date_cache or {}, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except Exception:
        pass


def dates_for(guide: str) -> Dict[str, str]:
    """가이드의 작성·최종수정일. mtime 을 캐시 무효화 키로 쓴다.

    git 이 진실 소스이고(파생 우선), 없으면 파일 mtime 으로 degrade 한다.
    """
    path = GUIDES_DIR / guide
    try:
        mtime = str(int(path.stat().st_mtime))
    except OSError:
        return {}
    cache = _load_cache()
    hit = cache.get(guide)
    if hit and hit.get("mtime") == mtime:
        return hit
    mdate = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    got = _git_dates(f"data/guides/{guide}")
    if not got:
        got = {"born": mdate, "updated": mdate, "src": "mtime"}
    elif mdate > (got.get("updated") or ""):
        # ★git 은 *커밋된* 것만 안다. 작업 트리에서 고쳐 놓고 아직 커밋 안 한 가이드는
        # git 날짜가 낡은 채로 남아, 방금 고친 것을 "몇 주 전 수정"으로 보고하게 된다
        # (실측: 오늘 고친 business.md 가 07-29 로 나왔다). 파일 mtime 이 더 최신이면
        # 그쪽이 진실 — 수정은 커밋이 아니라 편집 시점에 일어난다.
        got = {**got, "updated": mdate, "src": "git+worktree"}
    got["mtime"] = mtime
    with _lock:
        cache[guide] = got
        _save_cache()
    return got


# ---------------------------------------------------------------- 표식

def _days_ago(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return (date.today() - date(y, m, d)).days
    except Exception:
        return None


def freshness_note(guide: str) -> str:
    """주입 시 가이드 머리에 붙일 한 줄. 실패하면 빈 문자열(주입은 계속된다)."""
    try:
        d = dates_for(guide)
        if not d:
            return ""
        upd = d.get("updated")
        age = _days_ago(upd)
        use = _uses_since(guide, upd)
        approx = " 추정" if d.get("src") == "mtime" else ""

        when = f"최종수정 {upd}"
        if age is not None:
            when += "(오늘)" if age == 0 else f"({age}일 전)"

        if use["count"]:
            tail = f"이후 무수정 사용 {use['count']}회(최근 {use['last']})"
        elif age == 0:
            tail = "이후 사용 0회 — 고친 직후라 실전 검증 전"
        else:
            tail = "이후 무수정 사용 0회"

        # 검토 이력 — '아무도 안 봤다'와 '봤고 고칠 게 없었다'는 전혀 다른 정보다.
        rev = last_review(guide)
        if rev:
            rd = _days_ago(rev)
            tail += f" · 마지막 검토 {rev}" + (f"({rd}일 전)" if rd else "(오늘)")

        note = f"<!-- 가이드 신선도{approx}: 작성 {d.get('born')} · {when} · {tail}"
        if age is not None and age >= STALE_DAYS and not use["count"]:
            note += (
                " ★오래됐고 그 뒤 사용 이력이 없다 — 현재 어휘·경로와 어긋날 수 있으니"
                " 그대로 믿지 말고 실행 전 확인할 것"
            )
        # '무수정 사용'은 '맞았다'가 아니라 '안 고쳐졌다'이다. 읽는 쪽이 오독하지 않게 명시.
        note += " (무수정 사용=고쳐지지 않았다는 뜻이지 옳음의 증명이 아님) -->"
        return note
    except Exception as e:
        logger.debug(f"[guide_registry] 신선도 표식 실패 (무시): {e}")
        return ""


def all_freshness() -> List[Dict]:
    """전 가이드의 신선도 — 주간 순찰이 '어느 것부터 볼지' 정하는 데 쓴다."""
    out: List[Dict] = []
    try:
        names = sorted(f.name for f in GUIDES_DIR.glob("*.md"))
    except OSError:
        return out
    for g in names:
        d = dates_for(g)
        if not d:
            continue
        upd = d.get("updated")
        use = _uses_since(g, upd)
        out.append({
            "guide": g,
            "born": d.get("born"),
            "updated": upd,
            "age_days": _days_ago(upd),
            "clean_uses": use["count"],
            "last_use": use["last"],
            "src": d.get("src"),
            "bytes": (GUIDES_DIR / g).stat().st_size,
        })
    # 오래됐고 안 쓰인 것이 앞으로 — 순찰 우선순위
    out.sort(key=lambda r: (r["clean_uses"], -(r["age_days"] or 0)))
    return out
