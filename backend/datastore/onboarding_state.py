"""onboarding_state.py — 첫 성공 온보딩의 상태 원장 (2026-09-02, ① D)

"설치 완료"와 "사용 가능"은 다른 상태다. 이 원장은 그 차이를 기계가 재는 자리 —
시스템 AI 가 **실제로 한 번 답했다**(first_reply_at)가 온보딩의 종료조건이다.
localStorage 가 아니라 서버 파일인 이유: 원격 런처·폰·데스크톱 3표면이 같은 상태를 본다.

기록 지점 = system_ai_memory.save_conversation(role="assistant") 한 곳 — HTTP(/system-ai/chat)와
WebSocket 스트림이 모두 그 자리를 지나므로 경로마다 훅을 심지 않는다.
파일: data/onboarding_state.json (gitignore — 사용자 상태).
"""
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from runtime_utils import get_data_path

_LOCK = threading.Lock()
_marked_this_process = False   # 답변마다 파일을 읽지 않기 위한 프로세스 플래그(첫 1회만 쓴다)


def _path() -> Path:
    return get_data_path() / "onboarding_state.json"


def _default() -> dict:
    return {"first_reply_at": None, "first_reply_provider": None, "first_reply_model": None,
            "dismissed_at": None}


def get_state() -> dict:
    p = _path()
    if not p.exists():
        return _default()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 깨진 원장은 '없음'으로 눙치지 않는다 — 다만 온보딩은 다시 보여주는 쪽이 안전(fail-open 아님:
        # 온보딩 재표시는 권한이 아니라 안내다).
        return {**_default(), "corrupt": True}
    return {**_default(), **data}


def _write(state: dict) -> None:
    p = _path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def is_completed() -> bool:
    return bool(get_state().get("first_reply_at"))


def mark_first_reply(provider: str = None, model: str = None) -> bool:
    """첫 응답 기록. 이미 기록돼 있으면 no-op. 반환 = 이번 호출이 새로 기록했는가."""
    global _marked_this_process
    if _marked_this_process:
        return False
    with _LOCK:
        if _marked_this_process:
            return False
        state = get_state()
        if state.get("first_reply_at"):
            _marked_this_process = True
            return False
        state["first_reply_at"] = datetime.now().isoformat(timespec="seconds")
        state["first_reply_provider"] = provider
        state["first_reply_model"] = model
        state.pop("corrupt", None)
        try:
            _write(state)
        except OSError:
            return False
        _marked_this_process = True
        return True


def mark_dismissed() -> dict:
    """사용자가 온보딩을 건너뜀 — 다음 기동에 다시 밀어붙이지 않는다(설정에서 언제든)."""
    with _LOCK:
        state = get_state()
        state["dismissed_at"] = datetime.now().isoformat(timespec="seconds")
        state.pop("corrupt", None)
        _write(state)
        return state


def reset_for_tests() -> None:
    global _marked_this_process
    with _LOCK:
        _marked_this_process = False
        try:
            _path().unlink()
        except FileNotFoundError:
            pass
