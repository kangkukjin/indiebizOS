"""기존 도구 없는 최종 평가자를 사본 준비 단계에서 호출한다. 완료 판정과 분리한다."""
import copy
import json


def execution_stream(stream):
    """같은 root의 실행자 하나만 사본을 소유한다. 상태 조회는 이 경로를 열지 않는다."""
    from repair_context import active, activation_only
    if not active() or activation_only():
        yield from stream
        return
    from runtime_utils import get_base_path
    from repair_continuation import current, key
    from thread_context import get_current_task_id
    from restart_protocol import OwnerLock
    row = current() or {}
    root = key(row.get("root_task_id") or get_current_task_id())
    lock = OwnerLock(get_base_path() / "data/system_ai_state/repair_sessions" / ("owner-" + root + ".lock"))
    if not lock.acquire():
        raise RuntimeError("같은 수리 사본을 다른 실행자가 수정 중입니다")
    try:
        yield from stream
    finally:
        lock.close()


def completion_error(controller):
    if not controller.repair_granted:
        return None
    from repair_continuation import current, key
    from runtime_utils import get_base_path
    from restart_protocol import read_json
    previous = current() or {}
    session_key = key(previous.get("staging_task_id") or previous.get("task_id") or controller.task)
    session = read_json(get_base_path() / "data/system_ai_state/repair_sessions" / (session_key + ".json"))
    if not session:
        return None  # 조사만 했고 수리 변경이 없는 턴
    if session.get("status") != "applied":
        return "수리 사본이 아직 정본에 반영되지 않았습니다. 사본 준비와 전체 완료는 다릅니다"
    if not (session.get("commit") or {}).get("success"):
        return "정본 반영은 확인했으나 수리 델타의 커밋이 완료되지 않았습니다"
    return None


def prepare(controller, repo, session, verify, candidate):
    from final_evaluator import prepare as prepare_packet, invoke, snapshot_error
    from supervisor_handoff import criteria_contract
    if controller.cancelled() or not controller.repair_granted or not controller.evaluation_enabled:
        return {"success": False, "applied": False, "error": "취소됐거나 사본 완료 기준이 없습니다"}
    from red_report import current_owner
    if session.get("owner") != current_owner():
        return {"success": False, "applied": False, "error": "수리 사본 소유자가 일치하지 않습니다"}
    contract = copy.deepcopy(getattr(controller, "_final_criteria_contract", None)
                             or criteria_contract(controller.message, controller.framing))
    if not contract.get("criteria"):
        return {"success": False, "applied": False, "error": "원래 요청의 완료 기준이 없습니다"}
    old_packet = getattr(controller, "_evaluation_packet", None)
    old_snapshot = getattr(controller, "_evaluation_snapshot", None)
    try:
        ok, checks = verify(repo, session)
        if not ok:
            return {"success": False, "applied": False, "verified": False, "checks": checks,
                    "error": "사본 기계 검증 미달. 같은 사본에서 보완하세요"}
        current_hash = candidate.digest(candidate.collect(repo, session))
        environment_hash = candidate.environment(__import__("pathlib").Path(repo) / session["worktree"])
        evidence = [r for r in session.get("execution_checks", [])
                    if r.get("candidate_hash") == current_hash
                    and r.get("environment_hash") == environment_hash]
        evidence = [{**r, "output": r.get("output", "")[:3000] + "\n…\n" + r.get("output", "")[-3000:]}
                    if len(r.get("output", "")) > 6000 else r for r in evidence]
        if not any(r.get("status") == "passed" for r in evidence):
            return {"success": False, "applied": False, "error": "현재 사본의 유효한 실행 검사 근거가 없습니다. 격리 셸에서 요청 범위를 검사하세요"}
        packet = prepare_packet(controller)
        packet["criteria"] = json.dumps(contract, ensure_ascii=False)
        packet["context"].update(criteria_contract=contract, evaluation_target="repair_workspace",
                                  workspace=session["worktree"], workspace_checks=checks,
                                  activation_commands=session.get("activation_commands", {}),
                                  workspace_evidence=evidence,
                                  workspace_files=[r["rel"] for r in session["files"].values()])
        # 관측된 근거는 신뢰된 서비스의 실행 결과다. 실행자의 Boolean을 근거로 받지 않는다.
        decision = json.loads(invoke(controller, phase="workspace"))
        rows = decision.get("workspace_coverage", [])
        coverage = {r.get("criterion_id"): r for r in rows if isinstance(r, dict)}
        evidence_ids = {r["id"] for r in evidence if r.get("status") == "passed"}
        missing = []
        for criterion in contract["criteria"]:
            row = coverage.get(criterion["id"], {})
            if criterion.get("verification_phase") == "activation":
                plan = criterion.get("activation_plan")
                command = plan.get("command") if isinstance(plan, dict) else plan
                commands = session.get("activation_commands", {}).values()
                service_plan = isinstance(plan, dict) and plan.get("kind") in {"controller_active", "commit"}
                valid = (service_plan or bool(command) and command in commands) and row.get("status") == "activation_pending"
            else:
                refs = row.get("evidence_ids", [])
                valid = row.get("status") == "passed" and bool(refs) and set(refs) <= evidence_ids
            if not valid:
                missing.append(criterion["id"])
        error = snapshot_error(controller)
        if (decision.get("status") != "APPROVED" or missing or error or controller.cancelled()
                or current_hash != candidate.digest(candidate.collect(repo, session))
                or environment_hash != candidate.environment(__import__("pathlib").Path(repo) / session["worktree"])):
            return {"success": False, "applied": False, "ready": False,
                    "missing_criteria": missing, "decision": decision,
                    "error": error or "사본 준비 미달 또는 검증 중 변경. 같은 실행에서 수정·검증을 계속하세요"}
        candidate.seal(repo, session, checks, decision, contract)
        controller.log("repair.workspace_ready", role="evaluate", worktree=session["worktree"],
                       candidate_hash=current_hash, criteria=contract)
        return {"success": True, "ready": True, "applied": False}
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        return {"success": False, "applied": False, "error": "사본 준비 판정 실패: " + str(exc)}
    finally:
        controller._evaluation_packet = old_packet
        controller._evaluation_snapshot = old_snapshot
