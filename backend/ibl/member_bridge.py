"""인증된 회원 턴에서 자신의 손발로만 봉투를 보낸다. 허브 실행 폴백 없음."""
import json
import time

import principal
import member_runtime
import phone_jobs


def connected(device_id):
    import limb_keys
    rec = limb_keys.get_by_device(device_id)
    if not rec or rec.get("revoked") or (rec.get("expires_at") and time.time() >= rec["expires_at"]) or not rec.get("approved"):
        return False
    import device_registry
    entry = next((e for e in device_registry.list_live() if e.get("device_id") == device_id), None)
    return bool(entry) and (rec.get("env") or {}).get("mode") == "member"


def request(command, timeout=None):
    p, state = principal.current(), member_runtime.current()
    if p.kind != principal.KIND_MEMBER or not state or state["device_id"] != p.device_id:
        return {"success": False, "error_type": "permission", "error": "회원 기기 바인딩 없음"}
    if state.get("body_session"):
        import limb_keys
        if (limb_keys.get_by_device(p.device_id) or {}).get("session") != state["body_session"]:
            return {"success": False, "error_type": "no_body", "error": "브라우저 연결이 변경됐습니다"}
    if state["cancel"].is_set() or time.monotonic() >= state["deadline"] or not connected(p.device_id):
        return {"success": False, "error_type": "no_body", "error": "회원 기기가 연결되어 있지 않습니다"}
    with state["lock"]:
        if state["step"] >= int(state["policy"].get("max_jobs_per_turn", 64)):
            return {"success": False, "error_type": "limit", "error": "이 턴의 기기 작업 한도에 닿았습니다"}
        state["step"] += 1
        key = f'{p.key()}:{state["task_id"]}:{state["step"]}'
    envelope = {**command, "request_key": key, "member": True, "task_id": state.get("local_task_id", ""), "body_session": state.get("body_session", "")}
    emit = state.get("on_event")
    if emit and command.get("op") not in {"memory_recall", "memory_save"}:
        emit({"type": "client_action_required", "op": command.get("op"), "request_key": key})
    job = phone_jobs.enqueue(p.device_id, json.dumps(envelope, ensure_ascii=False), p.key())
    state["jobs"].add(job)
    deadline = min(state["deadline"], time.monotonic() + float(timeout or state["policy"].get("command_timeout_s", 120)))
    result = None
    while time.monotonic() < deadline and not state["cancel"].is_set():
        result = phone_jobs.wait_result(job, timeout=min(1, max(0, deadline-time.monotonic())))
        if result is not None:
            break
    if result is None:
        phone_jobs.cancel_pending(job)
        return {"success": False, "error_type": "result_unknown", "request_key": key,
                "error": "결과를 아직 확인하지 못했습니다. 같은 작업을 다시 실행하지 말고 결과를 조회하세요."}
    if not isinstance(result, dict):
        return {"success": False, "error_type": "protocol", "error": "잘못된 손발 결과"}
    if result.get("error") or result.get("state") in ("unknown", "running"):
        result["success"] = False
    if command.get("op") == "write" and result.get("success") is not False and result.get("saved"):
        import hashlib
        import base64
        context = state.get("client_context", {})
        if context.get("capabilities", {}).get("files"):
            try:
                content = base64.b64decode(command.get("content", ""), validate=True) if command.get("encoding") == "base64" else str(command.get("content", "")).encode()
                digest = hashlib.sha256(content).hexdigest()
                if result.get("sha256") != digest or result.get("size") != len(content):
                    return {"success": False, "error_type": "integrity", "error": "기기 저장 영수증이 산출물과 다릅니다"}
            except (ValueError, TypeError):
                return {"success": False, "error_type": "integrity", "error": "기기 저장 영수증 형식 오류"}
        state.setdefault("delivered_files", []).append({"path": result.get("path"), "on": "body", "saved": True,
                                                       "sha256": result.get("sha256"), "request_key": key})
        if emit:
            emit({"type": "delivered", "request_key": key, "path": result.get("path")})
    return result


def translate(mapping, params):
    """값 치환만 한다. eval·액션 이름 분기 없음."""
    if isinstance(mapping, str) and mapping.startswith("$"):
        return params.get(mapping[1:])
    if isinstance(mapping, dict):
        return {k: value for k, v in mapping.items() if (value := translate(v, params)) is not None}
    if isinstance(mapping, list):
        return [translate(v, params) for v in mapping]
    return mapping


def execute(entry, params):
    from member_files import resolve_references
    try:
        params = resolve_references(params)
    except ValueError as exc:
        return {"success": False, "error_type": "input", "error": str(exc)}
    command = translate(entry["limb_op"], params)
    if entry.get("member_transform"):
        from member_files import transform
        return transform(entry, params, command, request)
    if command["op"] == "write" and "content" not in command:
        content = params.get("_prev_result")
        if content is None:
            return {"success": False, "error_type": "input", "error": "content 또는 직전 파이프 결과가 필요합니다"}
        command["content"] = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    result = request(command)
    if result.get("success") is False:
        return result
    if command["op"] == "read" and "content" in result:
        return result["content"]
    if command["op"] == "list":
        return {"items": result.get("items", result.get("files", []))}
    return result
