"""적용·활성 확인·각인의 영수증을 같은 상태/복구 계약으로 노출한다."""


def progress(session):
    state = session.get("status", "staging")
    activation = session.get("activation_checks") or {}
    commit = session.get("commit") or {}
    commands = (session.get("readiness") or {}).get("activation_commands") or {}
    import hashlib
    missing = [field for field, command in commands.items() if command and (
        activation.get(field, {}).get("state") != "passed" or
        activation.get(field, {}).get("command_sha256") != hashlib.sha256(command.encode()).hexdigest())]
    applied = state == "applied"
    complete = bool(applied and session.get("verified") and commit.get("success")
                    and (session.get("readiness") or {}).get("decision", {}).get("status") == "APPROVED"
                    and not missing)
    stage = ("complete" if complete else "activation" if applied and missing else "commit" if applied
             else "apply" if state in {"apply_scheduled", "applying"} else state)
    action = ("none" if complete else "finish_turn" if state == "apply_scheduled"
              else "inspect_activation" if stage == "activation" else "retry_apply" if stage == "commit"
              else "inspect_status" if state == "applying" else "continue_same_workspace")
    # 기존 apply 실패 응답의 activation.state/receipt를 유지하고 전체 원장은 별도로 제공한다.
    field = missing[0] if missing else next(reversed(activation), None)
    result = {"applied": applied, "complete": complete, "stage": stage,
              "activation": activation.get(field, {}), "activation_checks": activation, "commit": commit,
              "recovery": {"action": action, "stage": stage,
                           "status_args": {"op": "status", "key": session.get("key")}}}
    if action == "retry_apply":
        result["recovery"]["apply_args"] = {"op": "apply"}
    if missing:
        field = missing[0]
        record = activation.get(field) or {}
        receipt = record.get("receipt") or {}
        result["error"] = ("정본 반영 후 활성 확인 미완료: " + field + " (" + record.get("state", "pending") + ")"
                           + (" — " + (receipt.get("output") or record.get("error") or "")[:2000]))
    elif applied and not complete:
        result["error"] = "정본 반영 후 각인 미완료: " + str(commit.get("error") or "커밋 영수증이 없습니다")
    return result


def finish(session, result):
    status = progress(session)
    return {**result, **status, "success": status["complete"],
            "message": "정본 반영·활성 확인·커밋 완료" if status["complete"] else
                       status.get("error", "정본 반영 후 완료 영수증을 기다립니다")}
