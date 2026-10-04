"""판본 2 수리: 검사 근거로 적용하고 필요한 의미 조건만 평가한다."""
import copy
import json
from pathlib import Path

VERSION = 2


def direct_framing(message):
    return {"_repair_policy": VERSION, "_framing_source": "repair_execution",
            "needs_repair": True, "task_framing": message,
            "achievement_criteria": message,
            "criteria": [{"text": message, "user_quote": message, "verification_phase": "workspace"}],
            "capability_focus": {"hint": "같은 사본에서 요청을 수정하고 관련 검사를 실행하세요. "
                "apply에 verification_plan:[{criterion_id:'C1', command:'단일 pytest 또는 node --test 명령', "
                "method:'test'}]를 전달하면 같은 후보의 검사 결과를 재사용하거나 검사 후 적용합니다. "
                "판단이 필요한 조건은 method:'semantic'으로 지정합니다. 생성/빌드는 검사 전에 끝내세요. "
                "설계 판단이 필요하면 기존 reframe을 사용하세요. 실제 적재 확인은 active_verify_cmd입니다."}}


def enabled(controller):
    return (getattr(controller, "repair_granted", False)
            and (getattr(controller, "framing", None) or {}).get("_repair_policy") == VERSION)


def failure(stage, message, **details):
    return {"success": False, "applied": False, "error": message, "stage": stage,
            "recovery": {"action": "continue_same_workspace", "stage": stage}, **details}


def prepare(controller, repo, session, verify, candidate):
    """같은 입력의 실패도 재사용한다. 검증 함수는 후보를 변경할 수 없다."""
    from red_report import current_owner
    from supervisor_handoff import criteria_contract
    if controller.cancelled() or session.get("owner") != current_owner():
        return failure("ownership", "취소됐거나 수리 소유자가 일치하지 않습니다")
    if session.get("repair_policy") != VERSION:
        return failure("policy", "진행 중인 이전 판본 수리는 기존 정책으로 마무리해야 합니다")
    contract = copy.deepcopy(getattr(controller, "_final_criteria_contract", None)
                             or criteria_contract(controller.message, controller.framing))
    plan = session.get("verification_plan") or []
    criteria = {c["id"]: c for c in contract["criteria"] if c.get("verification_phase") != "activation"}
    if not criteria or not isinstance(plan, list) or not plan or len(plan) > 40:
        return failure("plan", "요청의 각 기능 기준에 검사 명령 또는 의미 검토를 연결하세요", missing_criteria=list(criteria))
    if any(not isinstance(p, dict) or p.get("criterion_id") not in criteria
           or p.get("method", "test") not in {"test", "semantic"}
           or (p.get("method", "test") == "test" and not p.get("command")) for p in plan):
        return failure("plan", "verification_plan의 criterion_id, method, command를 확인하세요")
    missing = sorted(set(criteria) - {p["criterion_id"] for p in plan})
    if missing:
        return failure("plan", "검사에 연결되지 않은 기능 기준이 있습니다", missing_criteria=missing)
    wt = Path(repo) / session["worktree"]
    before = candidate.collect(repo, session)
    env = candidate.environment(wt)
    supporting = {r["result"]["id"] for r in controller.store.tool_index(limit=10000)
                  if not r.get("is_error") and r.get("result", {}).get("id")}
    token = candidate.digest({"candidate": before, "env": env, "contract": contract, "plan": plan,
                              "supporting": sorted(supporting),
                              "activation": session.get("activation_commands"),
                              "evidence": session.get("execution_checks", [])})
    drift = candidate.conflicts(repo, session)
    if drift:
        return failure("conflict", "정본 변경을 사본에 합친 뒤 검사하세요", changed_files=sorted(drift))
    cached = session.get("preparation_result", {})
    if cached.get("input_hash") == token and (not cached.get("retryable") or cached.get("attempts", 1) >= 2):
        return {**cached["result"], "reused": True}
    def finish(result):
        session["preparation_result"] = {"input_hash": candidate.digest({
            "candidate": before, "env": env, "contract": contract, "plan": plan,
            "supporting": sorted(supporting),
            "activation": session.get("activation_commands"), "evidence": session.get("execution_checks", [])}),
            "attempts": cached.get("attempts", 1) + 1 if cached.get("input_hash") == token else 1,
            "result": result, "retryable": result.get("decision", {}).get("retryable", False)}
        controller._repair_failure = None if result.get("success") else result
        return result
    coverage, semantic, evidence = [], [], []
    # 명령 실행은 호스트의 기존 격리 실행기를 사용하고 과거 같은 후보의 영수증을 재사용한다.
    from repair_check_runner import check as run_check
    for item in plan:
        if item.get("method", "test") == "semantic":
            semantic.append(criteria[item["criterion_id"]])
            continue
        try:
            record = run_check(repo, session, candidate, item["command"], controller)
        except (ValueError, OSError) as exc:
            return finish(failure("test", str(exc), missing_criteria=[item["criterion_id"]]))
        evidence.append(record)
        if record.get("status") != "passed" or not (record.get("test_report") or {}).get("passed"):
            return finish(failure("test", "관련 검사가 통과하지 않았습니다", checks=[record],
                                  missing_criteria=[item["criterion_id"]]))
        coverage.append({"criterion_id": item["criterion_id"], "status": "passed", "evidence_ids": [record["id"]]})
    ok, checks = verify(repo, session)
    after = candidate.collect(repo, session)
    if before != after or env != candidate.environment(wt):
        return finish(failure("candidate_changed", "검사 중 후보가 변경됐습니다. 변경 후 관련 검사를 다시 실행하세요",
                              changed_files=sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))))
    if not ok:
        return finish(failure("gate", "필수 기계 검사가 통과하지 않았습니다", checks=checks))
    decision = {"status": "APPROVED", "method": "tests", "workspace_coverage": coverage}
    if semantic:
        current_hash = candidate.digest(before)
        observations = [r for r in session.get("execution_checks", [])
                        if r.get("candidate_hash") == r.get("before_hash") == current_hash
                        and r.get("environment_hash") == env]
        decision = semantic_review(controller, contract, semantic, session, observations)
        covered, invalid = normalize_coverage(decision, observations, supporting)
        missing = sorted({c["id"] for c in semantic} - covered)
        if decision.get("status") != "APPROVED" or missing:
            message = ("의미 검토의 증거 연결이 유효하지 않습니다. 현재 사본의 검사 id와 보충 증거 id를 확인하세요"
                       if decision.get("status") == "APPROVED" else decision.get("reason", "의미 조건 미확인"))
            return finish(failure("semantic", message, decision=decision,
                                  missing_criteria=missing, invalid_evidence=invalid,
                                  allowed_evidence_ids=[e["id"] for e in observations]))
        decision.update(method="mixed" if coverage else "semantic",
                        workspace_coverage=coverage + decision.get("workspace_coverage", []))
    if controller.cancelled() or before != candidate.collect(repo, session) or env != candidate.environment(wt):
        return finish(failure("candidate_changed", "검사 이후 후보·환경 변경 또는 취소가 발생했습니다"))
    # activation은 기능 심사로 다루지 않고 실제 적용 서비스의 계획과 영수증으로 확인한다.
    for c in contract["criteria"]:
        if c.get("verification_phase") != "activation":
            continue
        activation = c.get("activation_plan") or {}
        if not isinstance(activation, dict) or (activation.get("kind") not in {"controller_active", "commit"}
                and activation.get("command") not in session.get("activation_commands", {}).values()):
            return finish(failure("activation_plan", "활성 확인 계획이 없습니다", missing_criteria=[c["id"]]))
    candidate.seal(repo, session, checks, decision, contract)
    controller.log("repair.workspace_ready", role="harness", method=decision["method"],
                   candidate_hash=candidate.digest(before), criteria=contract)
    return finish({"success": True, "ready": True, "applied": False, "method": decision["method"]})


def normalize_coverage(decision, observations, supporting):
    """현재 후보의 검사를 앵커로 삼고 같은 턴의 보충 관측은 별도로 보존한다."""
    aliases = {r["id"]: r["id"] for r in observations if r.get("status") == "passed"}
    aliases.update({r["evidence_ref"]["id"]: r["id"] for r in observations
                    if r.get("status") == "passed" and r.get("evidence_ref", {}).get("id")})
    covered, invalid = set(), []
    for row in decision.get("workspace_coverage", []):
        if not isinstance(row, dict) or row.get("status") != "passed":
            continue
        refs = row.get("evidence_ids", [])
        extra = row.get("supporting_evidence_ids", [])
        if not isinstance(refs, list) or not isinstance(extra, list) or not all(
                isinstance(ref, str) for ref in refs + extra):
            invalid.append({"criterion_id": row.get("criterion_id"), "reason": "증거 id는 문자열 목록이어야 합니다"})
            continue
        anchors = list(dict.fromkeys(aliases[ref] for ref in refs if ref in aliases))
        supplements = list(dict.fromkeys(ref for ref in refs + extra if ref not in aliases and ref in supporting))
        unknown = [ref for ref in refs + extra if ref not in aliases and ref not in supporting]
        if not anchors or unknown:
            invalid.append({"criterion_id": row.get("criterion_id"), "unknown_ids": unknown,
                            "missing_current_check": not anchors})
            continue
        row.update(evidence_ids=anchors, supporting_evidence_ids=supplements)
        covered.add(row.get("criterion_id"))
    return covered, invalid


def semantic_review(controller, contract, criteria, session, evidence):
    from final_evaluator import prepare, invoke, snapshot_error
    old_packet = getattr(controller, "_evaluation_packet", None)
    old_snapshot = getattr(controller, "_evaluation_snapshot", None)
    try:
        packet = prepare(controller)
        limited = {**contract, "criteria": list({c["id"]: c for c in criteria}.values())}
        packet["criteria"] = json.dumps(limited, ensure_ascii=False)
        packet["context"].update(criteria_contract=limited, evaluation_target="repair_semantic",
                                  workspace=session["worktree"], workspace_evidence=[{**r, "output": r.get("output", "")[:15000] + "\n" + r.get("output", "")[-15000:]} for r in evidence],
                                  workspace_files=[r["rel"] for r in session["files"].values()])
        result = json.loads(invoke(controller, phase="semantic"))
        # 원문 부족이면 이미 저장된 같은 턴 증거만 한 번 보충한다. 새 개발은 시작하지 않는다.
        if result.get("recoverable"):
            refs = __import__("re").findall(r"\b[a-f0-9]{64}\b", result.get("reason", ""))
            recovered = []
            for ref in dict.fromkeys(refs[:8]):
                try:
                    page = controller.store.read_evidence(ref, 0, None)
                    if len(page["text"]) > 120000:
                        page["text"] = page["text"][:30000] + "\n…\n" + page["text"][-90000:]
                    recovered.append(page)
                except (OSError, ValueError, KeyError):
                    pass
            if recovered:
                packet["context"]["recovered_evidence"] = recovered
                result = json.loads(invoke(controller, phase="semantic"))
        error = snapshot_error(controller)
        if error:
            return {"status": "UNKNOWN", "reason": error}
        return result
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "UNKNOWN", "reason": "의미 검토 응답 오류: " + str(exc)}
    finally:
        controller._evaluation_packet, controller._evaluation_snapshot = old_packet, old_snapshot


def finalize(controller, response):
    """적용·각인 결과만 회수한다. 미적용을 새 개발 과제로 재분류하지 않는다."""
    from repair_continuation import current, key
    from restart_protocol import read_json
    from runtime_utils import get_base_path
    from thread_context import set_goal_eval_outcome
    from episode_logger import record_trajectory_event
    row = current() or {}
    task = key(row.get("staging_task_id") or controller.task)
    session = read_json(get_base_path() / "data/system_ai_state/repair_sessions" / (task + ".json")) or {}
    passed, receipt_reason = completion(session, row, get_base_path())
    if controller.cancelled():
        passed = False
    failure_info = getattr(controller, "_repair_failure", None) or session.get("preparation_result", {}).get("result") or {}
    reason = "검사한 변경의 정본 반영·활성 확인·커밋을 확인했습니다" if passed else (
        failure_info.get("error") or receipt_reason)
    if passed and controller.delivery.manifest():
        passed, reason = False, "코드 외 공개 대기 산출물은 별도 확인이 필요합니다"
    status = "ACHIEVED" if passed else "UNKNOWN"
    set_goal_eval_outcome(passed, 0, status=status, reason=reason, method="repair_receipts")
    controller.store.put_response(response)
    controller.log("repair.completion", role="harness", status=status, method="repair_receipts", reason=reason)
    record_trajectory_event("validation.completed", {"validator": "repair_receipts", "status": status,
                            "achieved": passed, "feedback_text": reason, "method": "repair_receipts"})
    (controller.store.directory / "review_status.json").write_text(json.dumps({
        "status": status, "reason": reason, "validator": "repair_receipts", "original_goal": controller.message,
        "episode_id": controller.episode_id, "learning": "eligible" if passed else "deferred"}, ensure_ascii=False))
    print(f"[RepairCheck] 최종 판정: {status}")
    return response + ("" if passed else "\n\n[수리 미완료] " + reason)


def completion(session, row, base):
    """정본 바이트·각인·활성 영수증을 검증한다. 모델이나 셸 검사를 다시 실행하지 않는다."""
    import hashlib
    import subprocess
    ready = session.get("readiness") or {}
    committed = session.get("commit") or {}
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
    commit = committed.get("commit", "")
    if not __import__("re").fullmatch(r"[a-f0-9]{7,64}", commit):
        return False, "유효한 커밋 식별자가 없습니다"
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
        actual = subprocess.run(["git", "show", commit + ":" + rel], cwd=base, capture_output=True, timeout=30)
        if item["after"] is None:
            if actual.returncode == 0:
                return False, "삭제 각인을 확인하지 못했습니다: " + rel
        elif actual.returncode or hashlib.sha256(actual.stdout).hexdigest() != item["after"]["sha"]:
            return False, "각인 내용이 검사한 변경과 다릅니다: " + rel
    return True, "관련 검사·정본 반영·활성 확인·커밋 완료"
