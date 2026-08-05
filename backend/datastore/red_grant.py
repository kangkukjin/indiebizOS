"""
red_grant.py - RED 구역(살아있는 기질) 쓰기 그랜트 원장
IndieBiz OS Core

헌법 개정(2026-08-05, 사용자 확정): 자기 몸(RED) 수정에 사람 승인 게이트(Floor #4)를
폐기하고 아래 3조건 + 기계 안전판으로 대체한다.
  1. 사람이 명령한 태스크에서만 (task origin = user — 스케줄러·자가점검 등 자율 태스크 제외)
  2. 최고(고급) 모델만 (기어가 절약이어도 수리 태스크는 고급으로 승격 — model_resolver 'system_repair')
  3. 의식 각성 상태에서만 (의식 토글 OFF 여도 REPAIR 는 THINK 경로 강제)
기계 안전판(Floor #3·#5)은 유지·강화: 사전 py_compile → 백업 → 쓰기 → 헬스체크 → 자동 롤백.

그랜트는 인지 파이프라인(agent_pipeline 의 REPAIR 경로)만 발급하고, 쓰기 게이트
(system_essentials handler)가 조회한다. 발급 없이 게이트를 여는 다른 경로는 없다.

★스레드 로컬이 아니라 프로세스 전역인 이유: claude_code 프로바이더의 도구 호출은
MCP→HTTP 재진입(api_ibl 워커 스레드)으로 실행돼 스레드 로컬이 끊긴다. task_id 는
그 심(seam)을 건너 복원되므로(mcp_server 헤더 → api_ibl set_current_task_id)
task_id 매칭을 1순위로 쓴다.
"""
import threading
import time

_lock = threading.Lock()
_grant = None  # {"agent_id","task_id","reason","issued_at"}

# 파이프라인 finally 가 정상 회수하지만, 프로세스가 그 전에 죽는 크래시 대비 TTL.
_TTL_SEC = 30 * 60


def issue_grant(agent_id: str, task_id: str, reason: str = "") -> dict:
    """RED 쓰기 그랜트 발급 — agent_pipeline REPAIR 경로 전용.

    싱글턴 슬롯(시스템 AI 는 동시 런이 없다). 새 발급이 이전 그랜트를 대체한다."""
    global _grant
    with _lock:
        _grant = {
            "agent_id": agent_id or "",
            "task_id": task_id or "",
            "reason": (reason or "")[:300],
            "issued_at": time.time(),
        }
        return dict(_grant)


def revoke_grant(task_id: str = None):
    """그랜트 회수. task_id 를 주면 그 태스크가 발급한 그랜트일 때만 회수한다
    (동시에 다른 런의 finally 가 남의 그랜트를 지우는 것 방지)."""
    global _grant
    with _lock:
        if _grant is None:
            return
        if task_id and _grant.get("task_id") and _grant["task_id"] != task_id:
            return
        _grant = None


def active_grant(task_id: str = None, agent_id: str = None):
    """현재 호출 컨텍스트에 유효한 그랜트를 반환(없으면 None).

    매칭 규칙:
    - 그랜트에 task_id 가 있으면 호출측 task_id 와 일치해야 한다 — 그랜트가 살아있는
      동안 병행하는 자율 태스크(자기 task_sysai_* id 를 갖는다)가 무임승차하지 못한다.
    - 호출측 task_id 가 비어 있으면(신원 유실 심) agent_id 일치로만 폴백한다.
    - 둘 다 없으면 허용하지 않는다(fail-closed).
    """
    with _lock:
        g = _grant
        if not g:
            return None
        if time.time() - g["issued_at"] > _TTL_SEC:
            return None
        if g["task_id"]:
            if task_id:
                return dict(g) if task_id == g["task_id"] else None
            if agent_id and agent_id == g["agent_id"]:
                return dict(g)
            return None
        if agent_id and agent_id == g["agent_id"]:
            return dict(g)
        return None
