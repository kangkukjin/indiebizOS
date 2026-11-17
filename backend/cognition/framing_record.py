"""직전 규정의 기록 — 턴이 끝날 때 그 턴의 유효 규정을 자아별로 적는다.

읽는 곳
- 의식의 계획 작성(`cognitive_consciousness._run_consciousness`): 같은 대화의 최근 연구계획을 후보 자료로
  본다. 관련성은 의식이 판단한다.
- 수리 재개(`repair_resume.user_resume`): 사용자의 말이 미완료 수리 작업을 가리키는지 찾는다.

기록의 원칙: 권한은 남기지 않는다(needs_repair·_repair_policy 는 벗긴다). 심층실행의 주문 단계와 첫
걸음은 그 턴의 것이라 남기지 않는다.

이 기록을 물려 쓰는 '규정 계승'은 없다. 2026-10-07~11-17 에는 THINK 턴이 '같은 과제의 후속'이거나 같은
문장의 정기 실행이면 의식을 깨우지 않고 직전 규정을 경량 모델이 고쳐 써서 실행자에게 넘겼다(의식 호출
약 1분·10만 토큰을 아끼려는 것). 에피소드 6192 에서 시제품 제작 요청이 직전 조사의 후속으로 판정돼
92분짜리 과제의 규정을 경량 모델이 7.7초에 새로 썼고, 사용자가 주문한 심층실행 10단계는 옮겨 적을 칸이
없어 1단계로 돌았다. **THINK 판정이면 의식이 새로 규정한다.** 되살리지 말 것 — data/decisions.yaml
`think-always-fresh-framing`.

모듈 이름은 2026-11-17 까지 framing_inheritance 였다. 계승이 없어진 뒤 남은 세 가지 일을 맡은 곳으로
나눴다: 기록은 여기, 수리 재개 판정은 repair_resume.judge_resume, 위임 완료 통지 판별은
cognitive_consciousness.is_delegation_report.

저장소 = data/system_ai_state/framing_inherit/<agent>.json — 자아별 한 파일(last + 문장별 최근 REPEAT_KEEP 건).
폴더 이름은 옛 이름 그대로다. 바꾸면 쌓인 기록을 옮기는 절차와 백업이 필요한데 얻는 것이 없다.
"""
import hashlib
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from consciousness_agent import project_framing

RECENT_WINDOW_S = 24 * 3600           # 직전 기록을 '최근 것'으로 보는 창 — 그보다 오래되면 읽지 않는다
REPEAT_KEEP = 40                      # 자아별 문장 기록 보존 수

# 저장본에서 벗기는 키 — 권한·턴 전용 표식
STRIP_ALWAYS = ("needs_repair", "_repair_policy", "_framing_source", "_inherited_from",
                "deep_execution", "first_step",  # 심층실행의 주문 단계와 첫 걸음은 그 턴의 것이다
                "scope", "pursuit_id", "title", "goal_criteria", "pursuit_reason", "detach_pursuit")


# ── 저장소 ─────────────────────────────────────────────────────────────────

def _store_root() -> Path:
    """시스템 AI 상태 루트 아래 — repair_continuation.state_root 를 따르므로 회귀 격리
    (conftest 의 isolated_runtime_stores · INDIEBIZ_RUNTIME_STATE_DIR)가 그대로 미친다."""
    from repair_continuation import state_root
    return Path(state_root()) / "framing_inherit"


def agent_key(runner) -> str:
    """자아 키 — 도구 실행이 실어 오는 agent_id 와 같은 식(reframe.turn_key_for 와 동형)."""
    try:
        from thread_context import get_current_agent_id
        key = get_current_agent_id() or ""
    except Exception:
        key = ""
    config = getattr(runner, "config", {}) or {}
    if not key:
        key = config.get("id") or ("system_ai" if config.get("_is_system_ai") else "")
    from conversation_sessions import current
    binding = current()
    return str(key or "") + ("@session:" + binding.session_id + __import__("conversation_sessions").revision_suffix(binding) if binding else "")


def _store_path(key: str) -> Path:
    return _store_root() / (re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".json")


def _load(key: str) -> dict:
    from restart_protocol import read_json
    data = read_json(_store_path(key), default=None)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("last", None)
    data.setdefault("repeat", {})
    return data


def _save(key: str, data: dict) -> None:
    from restart_protocol import atomic_json
    repeat = data.get("repeat") or {}
    if len(repeat) > REPEAT_KEEP:
        keep = sorted(repeat.items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:REPEAT_KEEP]
        data["repeat"] = dict(keep)
    atomic_json(_store_path(key), data)


def normalize_message(message: str) -> str:
    text = re.sub(r"\s+", " ", (message or "")).strip()
    return text.rstrip(" .。!?~…")


def _message_hash(message: str) -> str:
    return hashlib.sha1(normalize_message(message).encode("utf-8")).hexdigest()[:16]


def _age_s(record: dict) -> float:
    try:
        return max(0.0, time.time() - datetime.fromisoformat(record["at"]).timestamp())
    except Exception:
        return float("inf")


def _storable(framing: dict) -> dict:
    """권한·과거 과제 표식을 다음 실행에 전달하지 않는다."""
    return {k: v for k, v in (project_framing(framing) or {}).items() if k not in STRIP_ALWAYS}


def remember(runner, message: str, framing: dict, *, completed: bool = True) -> Optional[dict]:
    """턴 종료에 이 턴의 유효 규정을 자아별로 적는다(last + 문장별). 평가 판정과 함께."""
    from dialogue_continuation import recall_query
    message = recall_query(message)
    if not isinstance(framing, dict) or not framing:
        return None
    key = agent_key(runner)
    if not key:
        return None
    from thread_context import get_goal_eval_outcome, get_current_task_id, get_task_origin
    evaluation = get_goal_eval_outcome() or {}
    achieved = {"ACHIEVED": True, "NOT_ACHIEVED": False}.get(evaluation.get("goal_status"))
    episode_id = None
    try:
        from episode_logger import EpisodeLogger
        ep = EpisodeLogger.current()
        episode_id = getattr(ep, "episode_id", None)
    except Exception:
        pass
    record = {
        "message": (message or "")[:4000],
        "framing": _storable(framing),
        "at": datetime.now().isoformat(timespec="seconds"),
        "task_id": get_current_task_id() or "",
        "origin": get_task_origin() or "",
        "achieved": achieved, "goal_status": evaluation.get("goal_status", "UNKNOWN"),
        "review_status": evaluation.get("review_status", "NOT_RUN"),
        "completed": bool(completed),
        "episode_id": episode_id,
    }
    data = _load(key)
    data["last"] = record
    data["repeat"][_message_hash(message)] = record
    _save(key, data)
    return record
