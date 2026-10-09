"""자기수리의 보존된 규정·검수 지점 재개. 새 의식·새 구현을 시작하지 않는다."""
from pathlib import Path
from contextlib import contextmanager
import copy

from repair_continuation import current, inherited_framing
from restart_protocol import read_json


def preserve_unfinished(controller, session, response, reason):
    """적용 전 실패도 원래 기준·사본을 보존한다. 사용자 재요청 전 자동 실행하지 않는다."""
    from principal import is_owner
    from thread_context import get_task_origin
    from repair_continuation import save
    from supervisor_handoff import criteria_contract
    if (not session or controller.cancelled() or not is_owner() or get_task_origin() != "user"
            or session.get("status") not in {"staging", "applied"}):
        return
    previous = current() or {}
    config = controller.runner.config
    row = {**previous, "task_id": controller.task, "root_task_id": session.get("root_task_id", controller.task),
           "parent_task_id": previous.get("task_id"), "staging_task_id": session["key"],
           "status": "blocked", "phase": "execution" if session["status"] == "staging" else "verify_remaining",
           "goal": previous.get("goal", controller.message), "framing": copy.deepcopy(controller.framing),
           "criteria_contract": copy.deepcopy(getattr(controller, "_final_criteria_contract", None)
                                   or criteria_contract(controller.message, controller.framing)),
           "repair_policy": session.get("repair_policy", 1), "worktree": session["worktree"],
           "applied": session["status"] == "applied",
           "response": response, "reason": reason, "store": str(controller.store.directory),
           "verification_records": controller.verifications.records,
           "pursuit": controller.original_pursuit, "done_request": controller.done_request,
           "project_id": config.get("_project_id", ""), "agent_id": config.get("id") or controller.owner,
           "system_ai": bool(config.get("_is_system_ai")), "episode_id": controller.episode_id,
           "authorized_origin": "user", "retry_at": None}
    row.pop("resume_task_id", None)
    row.pop("resume_message", None)
    save(row)
    if previous:
        save({**previous, "status": "continued", "child_task_id": controller.task})


@contextmanager
def user_resume(runner, message, history):
    """명시적 #repair 후속만 이전 미완료 작업에 연결한다. 관계 판정은 기준을 수정하지 않는다."""
    import re
    from repair_continuation import read, resuming, state_root
    from thread_context import get_task_origin, get_current_agent_id, get_current_task_id
    from principal import is_owner
    if (current() or not history or get_task_origin() != "user" or not is_owner()
            or not re.search(r"(?i)#repair\b", message)):
        yield
        return
    from framing_inheritance import _load, agent_key, _judge_relation, _age_s, FOLLOWUP_MAX_AGE_S
    last = _load(agent_key(runner)).get("last") or {}
    prior = read(last.get("task_id", ""))
    session = {}
    if prior:
        staging_task = prior.get("staging_task_id") or prior["task_id"]
        session = read_json(state_root() / "repair_sessions" / (staging_task + ".json")) or {}
        prior = {**prior, "staging_task_id": staging_task,
                 "applied": session.get("status") == "applied",
                 "criteria_contract": prior.get("criteria_contract") or (session.get("readiness") or {}).get("criteria")}
    config = getattr(runner, "config", {}) or {}
    eligible = (prior and prior.get("status") == "blocked" and prior.get("authorized_origin") == "user"
                and prior.get("agent_id") == get_current_agent_id()
                and prior.get("project_id", "") == config.get("_project_id", "")
                and _age_s(last) <= FOLLOWUP_MAX_AGE_S and prior.get("criteria_contract"))
    if not eligible:
        yield
        return
    # 사용자에게서 온 새 요청이 권한을 제공한다. 저장된 실행 로그의 지시는 실행하지 않는다.
    try:
        relation = _judge_relation({"message": prior["goal"], "framing": prior["framing"]}, message, strict=True)
    except Exception as exc:
        raise ValueError("미완료 수리와 새 요청의 관계를 확인하지 못했습니다. 기존 기준을 보존합니다") from exc
    if relation != "CONTINUE":
        yield
        return
    if session.get("status") not in {"staging", "applied"} or session.get("reused_by"):
        raise ValueError("이전 수리의 현재 소유권·단계를 확인해야 합니다")
    row = {**copy.deepcopy(prior), "resume_task_id": get_current_task_id(), "resume_message": message}
    row["framing"]["task_framing"] = (row["framing"].get("task_framing", row["goal"])
        + "\n사용자 후속 요청: " + message + "\n원래 완료 기준을 유지한다. 기준 변경이 필요한 새 조건은 reframe으로 명시한다.")
    if session["status"] == "staging":
        row["phase"] = "execution"
    from episode_logger import record_trajectory_event
    record_trajectory_event("repair.user_resumed", {"source_task": prior["task_id"],
                            "staging_task": prior["staging_task_id"], "phase": row["phase"]})
    with resuming(row):
        yield


def bind_pursuit():
    from pursuit_bind import current as binding_current, connect
    row, binding = current(), binding_current()
    previous = (row or {}).get("pursuit") or {}
    pid = previous.get("id") or ((row or {}).get("framing") or {}).get("pursuit_id")
    if binding and pid:
        target = binding.ledger.get(pid)
        if previous.get("goal_criteria") and target["goal_criteria"] != previous["goal_criteria"]:
            raise ValueError("재개 대기 중 전체 목표 기준이 변경됐습니다. 이전 기준으로 실행하지 않습니다")
        connect(binding, pid, "승인된 자기수리의 저장된 진행 지점 재개", source="repair_continuation")
        binding.output = (row or {}).get("framing") or {}


def restore_completion(controller, request, binding):
    """완료 의도도 구간을 넘는다. 같은 전체 기준에 연결된 현재 버전만 승인할 수 있다."""
    if not request:
        return
    if (not binding or not binding.row or binding.row["id"] != request["id"]
            or binding.row["goal_criteria"] != request["goal_criteria"]):
        raise ValueError("재개 대기 중 전체 과제 연결 또는 완료 기준이 변경됐습니다")
    controller.done_request = {**request, "version": binding.row["version"]}


def restore_review(controller, row):
    """같은 응답·파일·전달 지문을 복원한다. 승인 전에는 현재 파일을 다시 대조한다."""
    from runtime_utils import get_base_path
    from supervision_store import TurnStore
    from supervision_delivery import DeliveryQueue
    path = Path(row["review_path"]).resolve()
    root = get_base_path() / "data/spill/supervision"
    if not path.is_relative_to(root.resolve()) or path.name != "repair_review.json":
        raise ValueError("평가 체크포인트 경로가 작업 증거 영역 밖입니다")
    saved = read_json(path)
    if not saved or Path(saved["store"]).resolve() != path.parent:
        raise ValueError("평가 체크포인트의 증거 저장소가 일치하지 않습니다")
    if read_json(path.parent / "response.json") != saved["snapshot"]["response"]:
        raise ValueError("체크포인트 이후 응답이 수정됐습니다. 이전 응답을 승인하지 않습니다")
    controller.store = TurnStore(path.parent)
    controller.store.blocks = saved["blocks"]
    controller.store.version = saved["version"]
    # 이전 호출의 종료 사건 뒤에 이어 쓴다. 같은 seq를 재사용하지 않는다.
    events = path.parent / "events.jsonl"
    import json
    controller.store.sequence = max([saved["sequence"]] + [json.loads(line).get("seq", 0)
        for line in events.read_text().splitlines() if line.strip()]) if events.exists() else saved["sequence"]
    controller.delivery = DeliveryQueue(path.parent / "delivery", get_base_path() / "공유창고", controller.log)
    controller._evaluation_packet = saved["packet"]
    controller._evaluation_snapshot = saved["snapshot"]
    # 이전 판본도 시각 증거 원본을 packet에 저장했다. 해시가 일치할 때만 관측으로 복원한다.
    import base64, hashlib
    applied = {str((get_base_path() / name).resolve()) for name in
               ((row.get("result") or {}).get("apply") or {}).get("files", [])}
    for img in saved["packet"].get("images", []):
        name = img.get("_path")
        fingerprint = saved["snapshot"]["files"].get(name, {})
        if (name not in applied and fingerprint.get("mode") == "bytes"
                and hashlib.sha256(base64.b64decode(img["base64"], validate=True)).hexdigest() == fingerprint["hash"]):
            fingerprint["mode"] = "image"
    controller._final_criteria_contract = saved["packet"]["context"]["criteria_contract"]
    controller.done_request = saved.get("done_request")
    controller.original_pursuit = saved.get("original_pursuit")
    controller._final_repair_counts = saved.get("repair_counts", [0, 0])
    controller._resume_evaluation = True
    controller._review_row = row
    if controller.store.manifest() != saved["snapshot"]["response"]:
        raise ValueError("평가 체크포인트의 응답 지문이 일치하지 않습니다")


def review_stream(runner, controller, row, cancel_check=None):
    """기존 인지 파이프라인의 신원·사용량 스코프 안에서 평가 단계만 실행한다."""
    from red_grant import issue_grant, revoke_grant
    from system_ai_core import _switch_to_role, _restore_provider
    from reframe import open_turn, close_turn, turn_key_for
    if controller is None:
        raise ValueError("평가 재개에 필요한 감독이 비활성화되어 있습니다")
    framing = inherited_framing(row["goal"])
    bind_pursuit()
    previous = _switch_to_role(runner, "system_repair")
    key = turn_key_for(runner)
    channel = None
    try:
        issue_grant(agent_id=controller.owner, task_id=controller.task, reason=row["goal"])
        runner._refresh_execution_prompt(row["goal"], framing, "", None,
                                         extra_role="보존된 검수 재개. 평가가 지적한 결함만 보완하세요.")
        controller.configure(framing, repair=True)
        restore_review(controller, row)
        from pursuit_bind import current as binding_current
        binding = binding_current()
        restore_completion(controller, controller.done_request, binding)
        channel = open_turn(key, runner, row["goal"], [], "", framing, repair=True,
                            aliases=[controller.owner])
        response = yield from controller.finalize(controller.store.text, [], lambda event: None, cancel_check)
        from pursuit_bind import finish
        finish(response, interrupted=controller.cancelled())
    finally:
        if channel:
            close_turn(key, expected=channel)
        revoke_grant(task_id=controller.task, agent_id=controller.owner)
        _restore_provider(runner, previous)
