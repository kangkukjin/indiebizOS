"""approval_tokens.py — 사람 승인 토큰(1회성·수명·요청 지문 결속) (2026-10-05, 설치 목록 ② 권한 연결).

설계 정본: docs/APP_COMMON_FOUNDATION_GAPS_2026_10_05.md §1-②.
"누구인가"(principal)와 "무엇을 허용받았나"(requires)와 "사람이 이 변경을 승인했나"는 서로 다른 사실이다.
이 모듈은 셋째만 맡는다 — 특정 요청(주체·액션·프로그램+입력의 지문 = challenge)에 대해 사람이 보는 표면이
발급한 토큰을 저장하고, 실행기 관문(action_requires.gate)이 **그 지문**에 대해서만 한 번 소비한다.

- 발급은 사람 통로(HTTP /ibl/approve — 런처 세션 또는 로컬 브라우저 출처 검사)에서만. IBL 안에서는 발급할 수 없다
  (에이전트의 도구는 execute_ibl 하나 — install_approvals 와 같은 Floor #1 패턴).
- 토큰은 challenge 에 묶인다: 승인 뒤 내용(프로그램·입력)을 바꾸면 지문이 달라져 토큰이 맞지 않는다(Codex 검토 2).
- 1회 소비·기본 120초 수명. 프로세스 메모리에만 둔다(재기동이면 다시 승인 — 승인은 그 자리의 사람 행위다).
"""
import hashlib
import secrets
import threading
import time
from typing import Optional

DEFAULT_TTL_SECONDS = 120
_LOCK = threading.Lock()
_TOKENS: dict = {}   # token -> {"challenge": str, "expires": float}


def challenge(principal_key: str, action_key: str, request_digest: str, op: Optional[str] = None) -> str:
    """승인 대상의 지문 — 주체·액션(op)·요청(프로그램+입력) 셋을 묶는다. 같은 셋이면 같은 값(표면이 재전송할 수 있게)."""
    body = "|".join([principal_key or "", action_key or "", op or "", request_digest or ""])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


def request_digest(code: str, inputs=None, declared_inputs=None) -> str:
    """요청 지문 — 코드 원문과 입력(이름·값·선언)의 해시. 표면이 같은 요청을 재전송하면 같은 값."""
    import json
    payload = json.dumps({"code": code or "", "inputs": inputs or {}, "declared": sorted(declared_inputs or [])},
                         ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sweep(now: float) -> None:
    dead = [t for t, row in _TOKENS.items() if row["expires"] <= now]
    for t in dead:
        _TOKENS.pop(t, None)


def issue(challenge_id: str, ttl: int = DEFAULT_TTL_SECONDS) -> dict:
    """사람 통로가 부른다. 반환 {token, expires_in}. challenge 는 hex 32자."""
    if not isinstance(challenge_id, str) or len(challenge_id) != 32 or any(c not in "0123456789abcdef" for c in challenge_id):
        raise ValueError("challenge 는 hex 32자입니다")
    ttl = max(10, min(int(ttl), 600))
    token = secrets.token_hex(16)
    now = time.monotonic()
    with _LOCK:
        _sweep(now)
        _TOKENS[token] = {"challenge": challenge_id, "expires": now + ttl}
    return {"token": token, "expires_in": ttl}


def consume(token: Optional[str], challenge_id: str) -> bool:
    """관문이 부른다. 토큰이 이 challenge 에 발급된 살아 있는 것이면 **한 번** 소비하고 참."""
    if not token or not isinstance(token, str):
        return False
    now = time.monotonic()
    with _LOCK:
        _sweep(now)
        row = _TOKENS.get(token)
        if not row or row["challenge"] != challenge_id:
            return False
        del _TOKENS[token]
        return True


def pending_count() -> int:
    with _LOCK:
        _sweep(time.monotonic())
        return len(_TOKENS)
