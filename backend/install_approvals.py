"""
install_approvals.py - [self:install_lib] 승인-전-차단 게이트의 상태 저장소

자기개조 안전장치 Floor #1(RED 직접 쓰기 차단)과 같은 패턴의 공급망 방어 게이트.
에이전트가 런타임 pip 설치를 스스로 실행하지 못하게 하드 차단하고, 승인은
IBL 이 닿지 못하는 HTTP 채널(사람 전용 — 에이전트 도구는 execute_ibl 하나뿐)로만 받는다.

위협 모델: 악의적 에이전트가 아니라 '성실하지만 부주의한' 에이전트.
작업 중 의존성 누락을 만나 오타·typosquat 패키지(2026-06 Mastra easy-day-js 사태 부류)를
확인 없이 설치하는 경로를 기본값에서 제거한다. python-exec 등 임의 코드 실행 도구로
우회 가능한 것은 Floor #1 과 동일한 한계 — 이 게이트의 몫은 '기본 경로의 무단 설치 차단'이다.

승인은 1회용: 설치 성공 시 소비된다(재설치·업그레이드엔 재승인).
상태 파일(data/system_ai_state/install_approvals.json)은 system_essentials
쓰기 초크포인트가 보호 파일로 차단해, 에이전트가 파일 쓰기로 자가승인하지 못한다.
"""
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "system_ai_state" / "install_approvals.json"
_LOCK = threading.Lock()


def canonical_name(spec: str) -> str:
    """패키지 스펙에서 정규화된 이름을 뽑는다 (PEP 503).
    'DDGS[full]>=1.0' → 'ddgs'. 승인 대조는 항상 이 이름으로 한다."""
    name = re.split(r"[\[<>=!~;@ ]", (spec or "").strip(), 1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


def _load() -> dict:
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("pending", {})
            data.setdefault("approved", {})
            return data
    except FileNotFoundError:
        pass
    except Exception:
        pass  # 손상 시 빈 상태로 시작 (승인이 사라지는 쪽 = 안전한 방향)
    return {"pending": {}, "approved": {}}


def _save(data: dict):
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STATE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(_STATE_PATH)


def request_approval(spec: str, reason: str = "", source: str = "") -> dict:
    """설치 요청을 대기열에 등록(중복이면 갱신). 등록된 엔트리를 반환."""
    name = canonical_name(spec)
    with _LOCK:
        data = _load()
        entry = data["pending"].get(name) or {}
        entry.update({
            "package": name,
            "spec": (spec or "").strip(),
            "reason": (reason or "").strip()[:500],
            "source": source or entry.get("source", ""),
            "requested_at": datetime.now().isoformat(timespec="seconds"),
        })
        data["pending"][name] = entry
        _save(data)
        return entry


def is_approved(spec: str) -> bool:
    with _LOCK:
        return canonical_name(spec) in _load()["approved"]


def consume(spec: str) -> bool:
    """설치 성공 후 승인을 1회 소비. 있었으면 True."""
    name = canonical_name(spec)
    with _LOCK:
        data = _load()
        if name in data["approved"]:
            del data["approved"][name]
            _save(data)
            return True
        return False


def approve(package: str) -> dict:
    """사람 채널 전용: 대기 항목을 승인으로 옮긴다(대기에 없어도 선승인 가능)."""
    name = canonical_name(package)
    if not name:
        raise ValueError("package 가 비었습니다.")
    with _LOCK:
        data = _load()
        entry = data["pending"].pop(name, None) or {"package": name, "spec": name}
        entry["approved_at"] = datetime.now().isoformat(timespec="seconds")
        data["approved"][name] = entry
        _save(data)
        return entry


def reject(package: str) -> Optional[dict]:
    """사람 채널 전용: 대기/승인 어디에 있든 제거. 제거된 엔트리 또는 None."""
    name = canonical_name(package)
    with _LOCK:
        data = _load()
        entry = data["pending"].pop(name, None) or data["approved"].pop(name, None)
        if entry is not None:
            _save(data)
        return entry


def list_state() -> dict:
    with _LOCK:
        return _load()
