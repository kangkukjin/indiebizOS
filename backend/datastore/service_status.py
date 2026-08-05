"""service_status.py — 서비스 생존/상태 프로브 레지스트리 (2026-08-05 감사 ⑦ 후반부).

왜 분리: trigger_engine(IBL층)의 상태 보고와 world_pulse_collectors(인지층)의
자기수용감각이 "폴러 살아있나"를 물으려고 서비스 모듈(channel_poller·auto_response)을
직접 import 했다 — 아래층→서비스층 역방향이자 매듭의 교차층 간선. 상태를 *묻는 쪽*은
이름만 알고, *답하는 쪽*(각 서비스)이 기동 시 프로브를 등록한다(의존 역전).

서비스가 아예 로드 안 된 몸(폰 등)에선 프로브가 없고 probe() 가 default 를 반환 —
옛 lazy-import 의 except 경로와 같은 의미(없는 서비스 = 안 돎).
"""
from typing import Any, Callable, Dict, Optional

_PROBES: Dict[str, Callable[[], Any]] = {}


def register_probe(name: str, fn: Callable[[], Any]) -> None:
    """서비스 상태 프로브 등록 — 각 서비스 모듈이 로드/기동 시 1회."""
    _PROBES[name] = fn


def probe(name: str, default: Any = None) -> Any:
    """등록된 프로브 실행. 미등록·실패 = default (상태 조회가 본체를 깨면 안 됨)."""
    fn = _PROBES.get(name)
    if fn is None:
        return default
    try:
        return fn()
    except Exception:
        return default
