"""boot_status.py — 부팅 서브시스템 성패 원장 (관측용, 아주 얇은 층).

왜: api.lifespan 은 서브시스템을 하나씩 켜면서 대부분을 `except Exception as e:
print(... 실패 (무시): {e})` 로 감싼다. 그 자체는 옳다 — 창고 폴러가 안 떠도 서버는
떠야 한다. 문제는 **그 실패가 stdout 한 줄로만 남는다**는 것이다. 앱을 띄운 지 사흘 뒤
"왜 스케줄이 안 도나"를 물으면 답이 터미널 스크롤 저편에 있다.

그래서 켜지는 순간의 성패를 여기 기록하고 `/world-pulse/health` 가 같이 내보낸다.
동작을 바꾸지 않는다 — 실패는 여전히 무시되고 부팅은 계속된다. 보이기만 한다.

★치명 서브시스템(스케줄러·채널폴러·system_ai_runner)은 lifespan 에서 try 밖 맨몸
호출이라 실패하면 부팅이 죽는다. 그건 의도된 설계이므로 여기 대상이 아니다 —
이 원장은 "죽지는 않지만 없이 도는" 것들의 명단이다.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_ENTRIES: Dict[str, Dict[str, Any]] = {}

# 프로세스 기동 기준점(monotonic) — 진입점(api.py 등)이 최상단에서 set_process_start 로
# 심는다. 이게 있으면 원장의 각 entry 에 elapsed(기동 후 경과초)가 붙어, 원장이 곧
# 부팅 프로파일이 된다("윈도우에서 백엔드가 느리게 뜬다"를 설치본이 스스로 신고).
_T0: Optional[float] = None


def set_process_start(t0: Optional[float] = None) -> None:
    """프로세스 기동 기준점을 심는다(멱등 — 먼저 심은 쪽이 이긴다)."""
    global _T0
    if _T0 is None:
        _T0 = t0 if t0 is not None else time.monotonic()


def _elapsed() -> Optional[float]:
    return None if _T0 is None else round(time.monotonic() - _T0, 2)


def record(name: str, ok: bool, error: Optional[BaseException | str] = None,
           detail: str = "") -> None:
    """서브시스템 하나의 기동 결과를 남긴다. 예외를 삼키지 않는다(호출자가 이미 처리)."""
    with _LOCK:
        _ENTRIES[name] = {
            "name": name,
            "ok": bool(ok),
            "error": (f"{error.__class__.__name__}: {error}"
                      if isinstance(error, BaseException) else (str(error) if error else None)),
            "detail": detail or None,
            "at": time.time(),
            "elapsed": _elapsed(),
        }


def snapshot() -> Dict[str, Any]:
    """{ok, failed:[…], entries:[…]} — 표면·API 가 그대로 쓰는 모양."""
    with _LOCK:
        entries: List[Dict[str, Any]] = [dict(v) for v in _ENTRIES.values()]
    entries.sort(key=lambda e: e["at"])
    failed = [e["name"] for e in entries if not e["ok"]]
    return {
        "ok": not failed,
        "failed": failed,
        "total": len(entries),
        "entries": entries,
    }


def failed_names() -> List[str]:
    return snapshot()["failed"]


def persist(path, platform_label: str = "") -> None:
    """부팅 완료 시점의 원장을 append-only jsonl 로 한 줄 남긴다.

    왜: _ENTRIES 는 메모리 전용이라 재시작마다 증발한다 — "이번 부팅 23.5초"는 있어도
    "평소보다 느려졌나 / 윈도우가 맥보다 느린가"를 물을 과거가 없었다(2026-08-31 윈도우
    실측). 부팅당 한 줄(~1KB)이라 로테이션 불요. 실패해도 부팅은 계속된다(관측층 교리).
    platform_label(몸 간 비교 라벨)은 이음매인 호출자가 공급한다 — 이 모듈은 몸 독립 코어라
    OS 를 직접 묻지 않는다(OS-가드).
    """
    import json
    from pathlib import Path as _P
    try:
        snap = snapshot()
        row = {
            "at": time.time(),
            "platform": platform_label or "unknown",
            "total_s": _elapsed(),
            "ok": snap["ok"],
            "failed": snap["failed"],
            "phases": [{"name": e["name"], "ok": e["ok"], "elapsed": e.get("elapsed")}
                       for e in snap["entries"]],
        }
        p = _P(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[boot] 부팅 프로파일 영속화 실패(무시): {e}")
