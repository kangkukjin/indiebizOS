"""수리 적용은 실제 검사와 고정 바이트를 확인한다. 업무의 완료 판단은 실행자에게 남긴다."""
import copy
import json
from pathlib import Path

VERSION = 2


def direct_framing(message):
    return {"_repair_policy": VERSION, "_framing_source": "repair_execution",
            "needs_repair": True, "task_framing": message,
            "achievement_criteria": message,
            "criteria": [{"text": message, "user_quote": message, "verification_phase": "workspace"}],
            "capability_focus": {"hint": "변경 대상부터 확인하세요. 관리 연산으로 개정하는 정의·데이터는 그 연산으로 수정하고 새 호출로 검증합니다. "
                "관용구는 workflow detail의 revision을 expected_revision으로 save합니다. 코드 적용 없이 원래 목표를 평가합니다. "
                "보호 코어 밖의 일반 프로그램 구현 변경이 필요하면 같은 사본에서 수정·검사하세요. "
                "관련 검사를 실행한 뒤 apply하면 같은 후보·환경의 통과 결과를 재사용합니다. "
                "검사를 함께 실행하려면 verification_plan:[{command:'pytest 명령'}]을 전달하세요. "
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
    """같은 입력의 실패도 재사용한다. 검증 함수는 후보를 변경할 수 없다."""
    from red_report import current_owner
    from supervisor_handoff import criteria_contract
    if controller.cancelled() or session.get("owner") != current_owner():
        return failure("ownership", "취소됐거나 수리 소유자가 일치하지 않습니다")
    contract = copy.deepcopy(getattr(controller, "_final_criteria_contract", None)
                             or criteria_contract(controller.message, controller.framing))
    plan = copy.deepcopy(session.get("verification_plan") or [])
    if not isinstance(plan, list) or any(not isinstance(p, dict) for p in plan):
        return failure("plan", "verification_plan은 검사 명령 객체의 목록입니다")
    # 이전 기준 ID·semantic 항목은 적용 조건이 아니다. 원래 업무 기준은 그대로 보존한다.
    if any(p.get("command") is not None and not isinstance(p["command"], str) for p in plan):
        return failure("plan", "검사 command는 문자열입니다")
    commands = list(dict.fromkeys(p["command"] for p in plan if p.get("command")))
    wt = Path(repo) / session["worktree"]
    # The same preparation owns dependency refresh for direct apply and shell
    # entry. Sync before capturing evidence; never change inputs during checks.
    try:
        before = candidate.refresh(repo, session)
    except (ValueError, OSError) as exc:
        return failure("conflict", str(exc))
    env = candidate.execution_environment(wt, session)
    token = candidate.digest({"candidate": before, "env": env, "contract": contract, "commands": commands,
                              "activation": session.get("activation_commands"),
                              "evidence": session.get("execution_checks", [])})
    drift = candidate.conflicts(repo, session)
    if drift:
        return failure("conflict", "정본 변경을 사본에 합친 뒤 검사하세요", changed_files=sorted(drift))
    cached = session.get("preparation_result", {})
    if cached.get("input_hash") == token:
        return {**cached["result"], "reused": True}
    def finish(result):
        session["preparation_result"] = {"input_hash": candidate.digest({
            "candidate": before, "env": env, "contract": contract, "commands": commands,
            "activation": session.get("activation_commands"), "evidence": session.get("execution_checks", [])}),
            "result": result}
        controller._repair_failure = None if result.get("success") else result
        return result
    from repair_check_runner import check as run_check
    for command in commands:
        drift = candidate.conflicts(repo, session)
        if drift:
            return finish(failure("conflict", "검사 사이 정본이 변경됐습니다", changed_files=sorted(drift)))
        try:
            record = run_check(repo, session, candidate, command, controller)
        except (ValueError, OSError) as exc:
            return finish(failure("test", str(exc)))
        if record.get("status") != "passed" or not (record.get("test_report") or {}).get("passed"):
            return finish(failure("test", "관련 검사가 통과하지 않았습니다", checks=[record]))
    observations = [r for r in session.get("execution_checks", [])
                    if r.get("candidate_hash") == r.get("before_hash") == candidate.digest(before)
                    and r.get("environment_hash") == env]
    passed = [r for r in observations if r.get("status") == "passed" and (r.get("test_report") or {}).get("passed")]
    if not passed:
        return finish(failure("test", "현재 사본의 통과 검사 결과가 없습니다. 관련 검사를 실행하세요.",
                              checks=observations))
    unresolved = unresolved_checks(session, candidate.digest(before), env)
    if unresolved:
        return finish(failure("test", "같은 후보에 미해결 검사 실패가 남아 있습니다. 원래 범위를 다시 검사하세요",
                              checks=unresolved))
    drift = candidate.conflicts(repo, session)
    if drift:
        return finish(failure("conflict", "검사 중 정본이 변경됐습니다. 적용 관문을 실행하지 않습니다",
                              changed_files=sorted(drift)))
    ok, checks = verify(repo, session)
    after = candidate.collect(repo, session)
    if before != after or env != candidate.execution_environment(wt, session):
        return finish(failure("candidate_changed", "검사 중 후보가 변경됐습니다. 변경 후 관련 검사를 다시 실행하세요",
                              changed_files=sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))))
    if not ok:
        return finish(failure("gate", "필수 기계 검사가 통과하지 않았습니다", checks=checks))
    regression = regression_evidence(session, [{"command": r["command"]} for r in passed])
    decision = {"status": "APPROVED", "method": "tests",
                "check_evidence": [check_evidence(r) for r in passed]}
    if controller.cancelled() or before != candidate.collect(repo, session) or env != candidate.execution_environment(wt, session):
        return finish(failure("candidate_changed", "검사 이후 후보·환경 변경 또는 취소가 발생했습니다"))
    candidate.seal(repo, session, checks, decision, contract)
    session["readiness"]["regression_evidence"] = regression
    controller.log("repair.workspace_ready", role="harness", method=decision["method"],
                   candidate_hash=candidate.digest(before), criteria=contract,
                   regression_evidence=regression)
    return finish({"success": True, "ready": True, "applied": False, "method": decision["method"],
                   "regression_evidence": regression})


def check_evidence(record):
    return {key: record.get(key) for key in ("id", "command", "candidate_hash", "before_hash",
                                            "environment_hash", "test_report", "selection", "evidence_ref", "failure_kind")}


def unresolved_checks(session, candidate_hash, environment_hash):
    latest = {}
    for row in session.get("execution_checks", []):
        if (row.get("before_hash") == row.get("candidate_hash") == candidate_hash
                and row.get("environment_hash") == environment_hash and row.get("test_report")):
            latest[row.get("command")] = row
    return [check_evidence(row) for row in latest.values() if row.get("status") != "passed"]


def regression_evidence(session, plan):
    """같은 검사가 수정 전 실패·수정 후 통과했는가(G5 원 증상 재검사의 사본 측 근거).

    실행자가 사본에서 같은 명령을 실패시킨 영수증(다른 candidate_hash)이 있으면 before_failed 로 연결한다.
    없으면 unknown — 통과만으로 재현을 주장하지 않는다."""
    records = session.get("execution_checks") or []
    out = []
    for item in plan:
        if item.get("method", "test") != "test":
            continue
        command = item.get("command")
        passed = next((r for r in reversed(records) if r.get("command") == command and r.get("status") == "passed"), None)
        failed = next((r for r in reversed(records) if r.get("command") == command and r.get("status") == "failed"
                       and (not passed or r.get("candidate_hash") != passed.get("candidate_hash"))), None)
        out.append({"command": command,
                    "before_failed_check": failed.get("id") if failed else None,
                    "after_passed_check": passed.get("id") if passed else None,
                    "status": "reproduced" if failed and passed else "unknown"})
    return out


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
    if passed and recheck != "verified":
        tail += "\n\n[원 증상 재검사 미확인] " + recheck_note
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
