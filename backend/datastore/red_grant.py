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
_grant = None  # {"agent_id","task_id","reason","issued_at","last_used_at","episode_ids"}

# 유휴 회수 한도 — 파이프라인 finally 가 정상 회수하지만, 그 finally 가 돌지 못한 채
# (제너레이터 누수 등) 프로세스는 계속 사는 경우의 누수 방지.
#
# ★시계의 기준은 '발급'이 아니라 '마지막 사용'이다 (2026-08-23, episode 1746 수리):
#   옛 코드는 발급 시각부터 30분을 쟀다. 8배 규모 상상훈련 턴이 45분을 사는 동안
#   16:04 에 4파일을 격리에 쌓고 16:26 에 apply 를 불렀는데, 그 사이 16:22 에
#   **시계가 살아 있는 턴의 권한을 처형**해 apply 가 거절됐다(라이브 미반영 4건).
#   턴이 길수록 수리도 큰데, 시작부터 재는 시계는 큰 수리만 골라 죽인다.
#   ★옛 명분("프로세스가 죽는 크래시 대비")은 자기 저장소와 모순이었다 — 그랜트는
#   프로세스 전역 인메모리라 프로세스가 죽으면 그랜트도 같이 죽는다. 시계가 실제로
#   막는 것은 'finally 누수' 하나뿐이고, 그것은 유휴로 재면 충분하다.
_IDLE_TTL_SEC = 30 * 60


def _issuer_episode_ids() -> set:
    """발급 턴을 가리키는 에피소드 id — 만료를 시계가 아니라 **몸에게** 묻기 위한 손잡이.

    현재 컨텍스트의 에피소드를 알면 그것 하나로 좁히고(정확), 모르면 그 순간 이 프로세스가
    열어 두고 있는 턴 전체를 잡는다(보수적 — 하나라도 살아 있으면 만료를 미룬다).
    에피소드 로거가 없는 몸(폰·분리 수행자 red_apply)에서는 빈 집합 = 판정 불능."""
    try:
        from episode_logger import EpisodeLogger, live_episode_ids
        ep = EpisodeLogger.current()
        if ep is not None and getattr(ep, "episode_id", None):
            return {ep.episode_id}
        return set(live_episode_ids())
    except Exception:
        return set()


def _issuer_alive(g) -> bool | None:
    """발급 턴이 아직 이 프로세스에 열려 있는가. True/False/None(판정 불능).

    31회차(2026-08-23)가 고아 회수에 세운 원칙을 그랜트 층에도 세운다 —
    **생사는 시계로 추정하지 않고 주인에게 묻는다.** 원장(ended_at)이 아니라
    프로세스 자신의 열린-턴 집합(episode_logger._live_episode_ids)이 출처다."""
    ids = g.get("episode_ids")
    if not ids:
        return None
    try:
        from episode_logger import live_episode_ids
        return bool(set(ids) & set(live_episode_ids()))
    except Exception:
        return None


def _idle_expired(g) -> bool:
    """유휴 한도를 넘겼는가 — 발급 턴이 **살아 있으면 묻지 않는다**(일하는 중이다)."""
    if _issuer_alive(g) is True:
        return False
    return time.time() - g.get("last_used_at", g["issued_at"]) > _IDLE_TTL_SEC


def _identity_ok(g, task_id, agent_id) -> bool:
    """이 호출이 그랜트의 주인인가 (종전 매칭 규칙 — 둘 다 없으면 fail-closed)."""
    if g["task_id"]:
        if task_id:
            return task_id == g["task_id"]
        return bool(agent_id and agent_id == g["agent_id"])
    return bool(agent_id and agent_id == g["agent_id"])


def issue_grant(agent_id: str, task_id: str, reason: str = "") -> dict:
    """RED 쓰기 그랜트 발급 — agent_pipeline REPAIR 경로 전용.

    싱글턴 슬롯(시스템 AI 는 동시 런이 없다). 새 발급이 이전 그랜트를 대체한다."""
    global _grant
    with _lock:
        _now = time.time()
        _grant = {
            "agent_id": agent_id or "",
            "task_id": task_id or "",
            "reason": (reason or "")[:300],
            "issued_at": _now,
            "last_used_at": _now,
            "episode_ids": _issuer_episode_ids(),
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
        if _idle_expired(g):
            return None
        if not _identity_ok(g, task_id, agent_id):
            return None
        # 쓰는 동안 데워진다 — 격리 적재로 일하고 있는 턴의 권한은 시계에 죽지 않는다.
        g["last_used_at"] = time.time()
        return dict(g)


def denial_note(task_id: str = None, agent_id: str = None) -> str:
    """활성 그랜트가 없을 때 **왜** 없는지 한 줄. 있으면 빈 문자열.

    ★왜 (2026-08-23, episode 1746): 게이트는 만료·주인 불일치·미발급을 전부 None 하나로
    뭉갰다. 그래서 만료로 막힌 수리 턴이 자기를 '수리 경로 밖 세션'으로 **오진**하고
    사용자에게 없는 사실을 보고했다 — 판정 불능을 '없음'으로 뭉개면 다음 진단이 거짓말을
    한다. 거절은 그대로 fail-closed 로 두되, 사유만 정직하게 말한다."""
    with _lock:
        g = _grant
        if not g:
            return ("수리 그랜트가 없습니다 — 이 턴은 REPAIR 경로로 발급된 적이 없습니다"
                    "(사용자가 '#repair' 로 명령한 턴에서만 발급됩니다).")
        if _idle_expired(g):
            _issued = time.strftime("%H:%M:%S", time.localtime(g["issued_at"]))
            _idle_m = int((time.time() - g.get("last_used_at", g["issued_at"])) / 60)
            _tail = ("발급 턴은 이미 닫혔습니다."
                     if _issuer_alive(g) is False else "발급 턴의 생사는 판정 불능입니다.")
            return (f"수리 그랜트가 만료됐습니다 — {_issued} 발급, 마지막 사용 이후 "
                    f"{_idle_m}분 무사용(유휴 한도 {int(_IDLE_TTL_SEC / 60)}분). {_tail}")
        if not _identity_ok(g, task_id, agent_id):
            return (f"이 호출은 그랜트의 주인이 아닙니다 — 그랜트 task="
                    f"{g['task_id'] or '(없음)'}/agent={g['agent_id'] or '(없음)'}, "
                    f"호출 task={task_id or '(없음)'}/agent={agent_id or '(없음)'}.")
        return ""
