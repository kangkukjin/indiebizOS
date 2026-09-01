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

★태스크별 다중 슬롯 (2026-09-01, ep2519/ep2520 수리): 옛 저장소는 싱글턴 슬롯이었고
그 정당화("시스템 AI 는 동시 런이 없다")는 위임 런이 생기면서 반증됐다 — 08-31 23:24,
59초 뒤 시작된 ep2520(녹음기)의 발급이 ep2519(자막 수리, storyteller 위임)의 그랜트를
덮어써 정상 경로(write 자동 적재→apply)를 봉쇄했고, 밀려난 턴은 propose/discard 루프에서
파생물을 만들고 죽이다 미완으로 끝났다. 그랜트는 task_id 별 슬롯에 살고, 발급·회수는
자기 슬롯만 건드린다 — 남의 런의 권한은 존재를 모른 채 지나간다.
"""
import threading
import time

_lock = threading.Lock()
# key(task_id, 없으면 "@"+agent_id) → {"agent_id","task_id","reason","issued_at",
# "last_used_at","episode_ids"}. 만료 레코드는 즉시 지우지 않는다 — denial_note 가
# "만료됐습니다"를 정직하게 말하려면 시체가 필요하다(발급이 넘칠 때만 청소).
_grants: dict = {}

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


def _slot_key(task_id: str, agent_id: str) -> str:
    """저장 슬롯 키 — task_id 가 정상, 신원 유실 심에서만 agent 슬롯."""
    return task_id if task_id else "@" + (agent_id or "")


def issue_grant(agent_id: str, task_id: str, reason: str = "") -> dict:
    """RED 쓰기 그랜트 발급 — agent_pipeline REPAIR 경로 전용.

    자기 슬롯(task_id)에만 쓴다 — 병행 REPAIR 런의 그랜트를 덮어쓰지 않는다
    (2026-09-01 개정 — 모듈 docstring의 ep2519/ep2520 사건)."""
    with _lock:
        _now = time.time()
        # 시체 청소는 발급이 넘칠 때만 — denial_note 의 만료 정직 신고를 위해 남겨둔다.
        if len(_grants) > 8:
            for k in [k for k, g in _grants.items() if _idle_expired(g)]:
                _grants.pop(k, None)
        g = {
            "agent_id": agent_id or "",
            "task_id": task_id or "",
            "reason": (reason or "")[:300],
            "issued_at": _now,
            "last_used_at": _now,
            "episode_ids": _issuer_episode_ids(),
        }
        _grants[_slot_key(task_id or "", agent_id or "")] = g
        return dict(g)


def revoke_grant(task_id: str = None, agent_id: str = None):
    """그랜트 회수 — 자기 슬롯만. task_id(정상) 또는 agent_id(신원 유실 심의 무태스크
    발급분)를 주면 그 슬롯만 지운다 — 다른 런의 finally 가 남의 그랜트를 못 지운다.
    둘 다 없으면 전량 회수(테스트·셀프테스트 정리 전용 — 파이프라인은 쓰지 않는다)."""
    with _lock:
        if task_id:
            _grants.pop(task_id, None)
        elif agent_id:
            _grants.pop("@" + agent_id, None)
        else:
            _grants.clear()


def active_grant(task_id: str = None, agent_id: str = None):
    """현재 호출 컨텍스트에 유효한 그랜트를 반환(없으면 None).

    매칭 규칙(종전과 동일 — 저장만 슬롯화):
    - 호출측 task_id 는 자기 task 슬롯만 연다 — 병행하는 자율 태스크(자기 task_sysai_*
      id 를 갖는다)가 남의 그랜트에 무임승차하지 못한다.
    - 무태스크 발급분(agent 슬롯)은 agent_id 일치로 연다.
    - 호출측 task_id 가 비어 있으면(신원 유실 심) agent_id 일치로만 폴백한다.
    - 둘 다 없으면 허용하지 않는다(fail-closed).
    """
    with _lock:
        candidates = []
        if task_id and task_id in _grants:
            candidates.append(_grants[task_id])
        if agent_id and ("@" + agent_id) in _grants:
            candidates.append(_grants["@" + agent_id])
        if not task_id and agent_id:
            # 신원 유실 심 — 어느 슬롯이든 agent 일치로 폴백(가장 최근 사용분 우선)
            candidates.extend(sorted(
                (g for g in _grants.values() if g.get("agent_id") == agent_id),
                key=lambda g: g.get("last_used_at", 0), reverse=True))
        for g in candidates:
            if _idle_expired(g):
                continue
            if not _identity_ok(g, task_id, agent_id):
                continue
            # 쓰는 동안 데워진다 — 격리 적재로 일하고 있는 턴의 권한은 시계에 죽지 않는다.
            g["last_used_at"] = time.time()
            return dict(g)
        return None


def denial_note(task_id: str = None, agent_id: str = None) -> str:
    """활성 그랜트가 없을 때 **왜** 없는지 한 줄. 있으면 빈 문자열.

    ★왜 (2026-08-23, episode 1746): 게이트는 만료·주인 불일치·미발급을 전부 None 하나로
    뭉갰다. 그래서 만료로 막힌 수리 턴이 자기를 '수리 경로 밖 세션'으로 **오진**하고
    사용자에게 없는 사실을 보고했다 — 판정 불능을 '없음'으로 뭉개면 다음 진단이 거짓말을
    한다. 거절은 그대로 fail-closed 로 두되, 사유만 정직하게 말한다."""
    with _lock:
        if not _grants:
            return ("수리 그랜트가 없습니다 — 이 턴은 REPAIR 경로로 발급된 적이 없습니다"
                    "(사용자가 '#repair' 로 명령한 턴에서만 발급됩니다).")
        # 자기 슬롯이 있으면 그 레코드의 사정(만료)을 말한다.
        g = _grants.get(task_id) if task_id else None
        if g is None and agent_id:
            g = _grants.get("@" + agent_id)
        if g is None and not task_id and agent_id:
            g = next((x for x in sorted(_grants.values(),
                                        key=lambda x: x.get("last_used_at", 0), reverse=True)
                      if x.get("agent_id") == agent_id), None)
        if g is not None:
            if _idle_expired(g):
                _issued = time.strftime("%H:%M:%S", time.localtime(g["issued_at"]))
                _idle_m = int((time.time() - g.get("last_used_at", g["issued_at"])) / 60)
                _tail = ("발급 턴은 이미 닫혔습니다."
                         if _issuer_alive(g) is False else "발급 턴의 생사는 판정 불능입니다.")
                return (f"수리 그랜트가 만료됐습니다 — {_issued} 발급, 마지막 사용 이후 "
                        f"{_idle_m}분 무사용(유휴 한도 {int(_IDLE_TTL_SEC / 60)}분). {_tail}")
            return ""  # 유효한 자기 그랜트 — 거절 사유 없음
        # 슬롯 미스 = 활성 그랜트들은 전부 남의 것
        _owners = ", ".join(
            f"task={x['task_id'] or '(없음)'}/agent={x['agent_id'] or '(없음)'}"
            for x in list(_grants.values())[:3])
        return (f"이 호출은 그랜트의 주인이 아닙니다 — 활성 그랜트 {len(_grants)}건"
                f"({_owners}), 호출 task={task_id or '(없음)'}/agent={agent_id or '(없음)'}.")
