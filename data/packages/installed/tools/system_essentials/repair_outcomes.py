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
    programs = session.get('program_activation') or []
    if programs and any(r.get('activation') != 'active' for r in programs):
        complete = False
        missing.append('program_activation')
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
        result["error"] = "정본 반영 후 각인 미완료: " + str(commit.get("error") or commit.get("message") or "커밋 영수증이 없습니다")
    result["root"] = _root_projection(session)
    result['program_scope'] = session.get('program_scope')
    result['program_activation'] = programs
    return result


def _root_projection(session):
    """단일 전이 원장(repair_root)의 투영 — 단계·다음 행동·재개 조건·서비스/전달 결과. 없으면 None."""
    try:
        import repair_root
        from runtime_utils import get_base_path
        root_id = repair_root.root_of_session(session)
        return repair_root.projection(get_base_path(), root_id) if root_id else None
    except Exception:
        return None


def finish(session, result):
    status = progress(session)
    return {**result, **status, "success": status["complete"],
            "message": "정본 반영·활성 확인·커밋 완료" if status["complete"] else
                       status.get("error", "정본 반영 후 완료 영수증을 기다립니다")}


def root_note(method, repo, *args):
    """수리 root 원장 전이(G3). 원장 실패가 수리 동작을 바꾸면 안 되므로 삼키고 한 줄 남긴다."""
    try:
        import repair_root
        return getattr(repair_root, method)(repo, *args)
    except Exception as exc:
        print(f"[수리 스테이징] root 원장 {method} 실패(무시): {type(exc).__name__}: {exc}")
        return None
