"""수리 적용은 권한·충돌·고정 바이트를 확인한다. 적합성 판단은 실행자에게 남긴다."""
import copy
import json

VERSION = 2


def direct_framing(message):
    return {"_repair_policy": VERSION, "_framing_source": "repair_execution",
            "needs_repair": True, "task_framing": message,
            "criteria": [{"text": message, "user_quote": message, "verification_phase": "workspace"}],
            "capability_focus": {"hint": "변경 대상부터 확인하세요. 관리 연산으로 개정하는 정의·데이터는 그 연산으로 수정하고 새 호출로 검증합니다. "
                "관용구는 workflow detail의 revision을 expected_revision으로 save합니다. 코드 적용 없이 원래 목표를 평가합니다. "
                "보호 코어 밖의 일반 프로그램 구현 변경이 필요하면 같은 사본에서 수정·검사하세요. "
                "관련 검사·오류를 보고 적합성을 판단한 뒤 apply하세요. 검사 이력은 적용 허가 조건이 아닙니다. "
                "검사를 함께 실행하려면 verification_plan:[{command:'검사 명령'}]을 전달하세요. "
                "적용은 전체 업무의 완료가 아닙니다. 반영 뒤 남은 업무를 이어가세요."}}


def enabled(controller):
    return (getattr(controller, "repair_granted", False)
            and (getattr(controller, "framing", None) or {}).get("_repair_policy") == VERSION)


def receipt_completion(controller):
    """첫 종료와 재개가 같은 기준으로 영수증 완료 경로를 선택한다."""
    from repair_continuation import current
    from repair_readiness import requires_code_receipts
    if (not enabled(controller) or not requires_code_receipts(controller)
            or controller.completion_review_required or (current() or {}).get('pending_delivery')
            or controller.delivery.manifest()):
        return False
    from repair_continuation import staging_session
    from runtime_utils import get_base_path
    row = current() or {}
    try:
        session = staging_session(row.get("staging_task_id") or controller.task, get_base_path()) or {}
    except (OSError, ValueError):
        return True
    # 적용 전에는 같은 사본을 이어가고, 한정 자식 수리는 영수증으로 부모에 복귀한다.
    # 일반 업무는 코드 반영만으로 목표 달성을 선언하지 않고 기존 실행·최종평가로 돌아간다.
    return (session.get("status") != "applied" or bool(session.get("task_scope")))


def failure(stage, message, **details):
    return {"success": False, "applied": False, "error": message, "stage": stage,
            "recovery": {"action": "continue_same_workspace", "stage": stage}, **details}


def prepare(controller, repo, session, verify, candidate):
    """실행자가 요청한 확인과 게시를 수행한다. 과거 검사 결과는 허가 조건이 아니다."""
    from red_report import current_owner
    from supervisor_handoff import criteria_contract

    def finish(result):
        session["preparation_result"] = {"result": result}
        controller._repair_failure = None if result.get("success") else result
        return result

    if controller.cancelled() or session.get("owner") != current_owner():
        return finish(failure("ownership", "취소됐거나 수리 소유자가 일치하지 않습니다"))
    contract = copy.deepcopy(getattr(controller, "_final_criteria_contract", None)
                             or criteria_contract(controller.message, controller.framing))
    # 명시한 명령은 이번 호출에서만 실행한다. 다음 apply에 옛 실패·계획을 강제하지 않는다.
    plan = session.pop("verification_plan", None) or []
    if (not isinstance(plan, list) or any(not isinstance(p, dict) or
            p.get("command") is not None and not isinstance(p["command"], str) for p in plan)):
        return finish(failure("plan", "verification_plan은 command 문자열을 담은 객체의 목록입니다"))
    try:
        candidate.refresh(repo, session)
        from repair_check_runner import check as run_check
        for item in plan:
            if not item.get("command"):
                continue
            record = run_check(repo, session, candidate, item["command"], controller)
            if record.get("exit_code") != 0:
                return finish(failure("test", "요청한 명령이 실패했습니다. 결과를 보고 다음 행동을 결정하세요.",
                                      checks=[record]))
        # 빌드·형식 검사 실패도 실행자가 판단할 관측이다. 게시 권한·충돌·고정 바이트는
        # candidate.seal/validate가 소유하며 검사 수·형식·성공 이력으로 대신하지 않는다.
        if controller.cancelled():
            return finish(failure("ownership", "수리가 취소됐습니다"))
        decision = {"status": "APPROVED", "method": "executor_apply"}
        candidate.seal(repo, session, session.get("publication_checks", []), decision, contract)
    except (ValueError, OSError) as exc:
        return finish(failure("prepare", str(exc)))
    controller.log("repair.workspace_ready", role="harness", method=decision["method"],
                   candidate_hash=session["readiness"]["candidate_hash"], criteria=contract)
    return finish({"success": True, "ready": True, "applied": False, "method": decision["method"]})


def symptom_recheck(session, row, base):
    """원 증상 재검사 판정(G5): 활성 확인 통과 | 사본 재현(수정 전 실패·후 통과) | 미확인(사유)."""
    ready = session.get("readiness") or {}
    active = (session.get("activation_checks") or {}).get("active_verify_cmd") or {}
    if active.get("state") == "passed" or ((row or {}).get("active_verify") or {}).get("state") == "passed":
        return "verified", "활성 세대에서 active_verify_cmd 통과"
    reproduced = [r for r in ready.get("regression_evidence") or [] if r.get("status") == "reproduced"]
    if reproduced:
        return "verified", "사본에서 같은 검사가 수정 전 실패·수정 후 통과(" + ", ".join(
            sorted({r.get("command") or "" for r in reproduced})) + ")"
    if ready.get("activation_commands", {}).get("active_verify_cmd"):
        return "unverified", "active_verify_cmd 가 아직 통과 영수증을 남기지 않았습니다"
    return "unverified", "원 증상의 수정 전 실패 영수증과 활성 확인 명령이 모두 없습니다 — 검사 통과만으로 재현을 주장하지 않습니다"


def finalize(controller, response):
    """적용·각인 결과만 회수한다. 미적용을 새 개발 과제로 재분류하지 않는다."""
    from repair_continuation import current, key, staging_session
    from runtime_utils import get_base_path
    from thread_context import set_goal_eval_outcome
    from episode_logger import record_trajectory_event
    row = current() or {}
    task = key(row.get("staging_task_id") or controller.task)
    try:
        session = staging_session(task, get_base_path()) or {}
        if not isinstance(session, dict):
            raise ValueError("수리 기록은 객체여야 합니다")
    except (OSError, ValueError) as exc:
        session = {}
        controller._repair_failure = {"error": "수리 기록을 읽지 못해 코드 적용을 확인할 수 없습니다: " + str(exc)}
    passed, receipt_reason = completion(session, row, get_base_path())
    if controller.cancelled():
        passed = False
    failure_info = getattr(controller, "_repair_failure", None) or session.get("preparation_result", {}).get("result") or {}
    reason = "검사한 변경의 정본 반영·활성 확인·커밋을 확인했습니다" if passed else (
        failure_info.get("error") or receipt_reason)
    if passed and controller.delivery.manifest():
        passed, reason = False, "코드 외 공개 대기 산출물은 별도 확인이 필요합니다"
    from repair_resume import continue_staging
    pending = not passed and continue_staging(controller, session, response, reason)
    status = "ACHIEVED" if passed else "PENDING_EXECUTION" if pending else "UNKNOWN"
    set_goal_eval_outcome(passed, 0, status=status, reason=reason, method="repair_receipts", goal_status=status,
                          review_status="NOT_RUN", goal_reason=reason,
                          goal_evidence=[receipt_reason] if passed else [])
    controller.store.put_response(response)
    controller.log("repair.completion", role="harness", status=status, method="repair_receipts", reason=reason)
    record_trajectory_event("validation.completed", {"validator": "repair_receipts", "status": status,
                            "achieved": passed, "goal_status": status, "review_status": "NOT_RUN", "final": True,
                            "feedback_text": reason, "method": "repair_receipts"})
    (controller.store.directory / "review_status.json").write_text(json.dumps({
        "status": status, "goal_status": status, "review_status": "NOT_RUN",
        "reason": reason, "validator": "repair_receipts", "original_goal": controller.message,
        "episode_id": controller.episode_id, "learning": "eligible" if passed else "deferred"}, ensure_ascii=False))
    print(f"[RepairCheck] 최종 판정: {status}")
    recheck, recheck_note = symptom_recheck(session, row, get_base_path())
    try:
        import repair_root
        root_id = repair_root.root_of_session(session) or row.get("root_task_id") or controller.task
        if pending:
            repair_root.transition(get_base_path(), root_id, stage='prepare', outcome='pending',
                                   reason=reason, next_action='ACTIVE에서 같은 사본의 남은 실행 자동 재개')
        elif session:
            repair_root.close(get_base_path(), root_id, complete=passed, reason=reason,
                              symptom_recheck={"verdict": recheck, "note": recheck_note},
                              resume_condition=None if passed else "실패 원인을 같은 사본에서 고친 뒤 일반 후속 요청으로 재개")
    except Exception as exc:
        print(f"[RepairCheck] 수리 root 종결 기록 실패(무시): {exc}")
    if not passed and not pending and session.get('status') != 'staging':
        from repair_resume import preserve_unfinished
        preserve_unfinished(controller, session, response, reason)
    tail = "" if passed else ("\n\n[작업 계속] 같은 사본과 전체 기준으로 남은 수리를 자동 재개합니다." if pending
                              else "\n\n[수리 미완료] " + reason)
    return response + tail


def completion(session, row, base):
    """정본 바이트·각인·활성·원 증상 영수증으로 완료를 판정한다. 검사를 다시 실행하지 않는다."""
    import hashlib
    import subprocess
    ready = session.get("readiness") or {}
    committed = session.get("commit") or {}
    if session.get("status") == "applied" and not committed.get("success") and committed:
        return False, "정본 반영 후 각인 실패: " + str(committed.get("error") or committed.get("message") or "커밋 미확인")
    if (session.get("repair_policy") != VERSION or session.get("status") != "applied"
            or not session.get("verified") or not committed.get("success")
            or ready.get("version") != VERSION
            or ready.get("decision", {}).get("status") != "APPROVED"):
        return False, "정본 반영·검사·커밋 영수증이 아직 완성되지 않았습니다"
    commands = ready.get("activation_commands") or {}
    for field, command in commands.items():
        if not command:
            continue
        record = session.get("activation_checks", {}).get(field) or {}
        expected = hashlib.sha256(command.encode()).hexdigest()
        if record.get("state") == "passed" and record.get("command_sha256") == expected:
            continue
        result = row.get("result") or {}
        if (result.get("outcome") == "healthy" and result.get(field) == command
                and (field == "verify_cmd" or row.get("active_verify", {}).get("state") == "passed"
                     and row["active_verify"].get("command_sha256") == expected)):
            continue
        return False, "활성 확인 영수증이 없습니다: " + field
    sealed = session.get("sealed") or {}
    artifacts_only = bool(sealed) and all(item.get("artifact") for item in sealed.values())
    # G4: 검사·정본 커밋·활성 판본이 같은 변경을 가리켜야 한다 — 활성 세대의 바이트를 대조한다.
    try:
        from red_apply import _load_handler as _lh
        verdict, detail = _lh({"repo": str(base)})._staging_mod()._candidate.active_generation_bytes(base, session)
    except Exception as exc:
        verdict, detail = "unknown", f"활성 바이트 대조 실패: {exc}"
    if verdict == "mismatch":
        return False, detail
    commit = committed.get("commit", "")
    if artifacts_only and (not committed.get("artifacts_only") or committed.get("bundle_hash") != ready.get("bundle_hash")):
        return False, "산출물 적용 영수증이 일치하지 않습니다"
    if not artifacts_only and not __import__("re").fullmatch(r"[a-f0-9]{7,64}", commit):
        return False, "유효한 커밋 식별자가 없습니다"
    if not artifacts_only:
        resolved = subprocess.run(["git", "rev-parse", "--verify", commit + "^{commit}"],
                              cwd=base, capture_output=True, text=True, timeout=30)
        if resolved.returncode:
            return False, "커밋이 존재하지 않습니다"
        commit = resolved.stdout.strip()
    from red_apply import _load_handler
    candidate = _load_handler({"repo": str(base)})._staging_mod()._candidate
    sealed = session.get("sealed") or {}
    if not sealed or candidate.digest(sealed) != ready.get("bundle_hash"):
        return False, "검사한 적용 묶음이 손상됐습니다"
    for rel, item in sealed.items():
        if candidate.fingerprint(candidate.target(base, rel)) != item["after"]:
            return False, "적용 후 정본이 변경됐습니다: " + rel
        if item.get("artifact"):
            continue
        actual = subprocess.run(["git", "show", commit + ":" + rel], cwd=base, capture_output=True, timeout=30)
        if item["after"] is None:
            if actual.returncode == 0:
                return False, "삭제 각인을 확인하지 못했습니다: " + rel
        elif actual.returncode or hashlib.sha256(actual.stdout).hexdigest() != item["after"]["sha"]:
            return False, "각인 내용이 검사한 변경과 다릅니다: " + rel
    return True, "관련 검사·정본 반영·활성 확인·커밋 완료"
