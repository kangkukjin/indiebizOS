"""모델에는 최종 내용 한 벌과 단계 상태만. 원 계약은 턴 증거로 보존한다."""
import json
from hashlib import sha256


def evidence_store():
    from supervision_bus import current
    controller = current()
    if controller:
        return controller.store
    from runtime_utils import get_base_path
    from thread_context import get_current_agent_id, get_current_task_id
    from supervision_store import TurnStore
    # 턴 밖 직접 호출도 다른 사용자의 증거와 섞이지 않는 독립 네임스페이스다.
    identity = f"{get_current_agent_id()}:{get_current_task_id()}"
    key = sha256(identity.encode()).hexdigest()
    return TurnStore(get_base_path() / "data" / "spill" / "tool_evidence" / key)


def read_result(request):
    offset, limit = int(request.get("offset", 0)), int(request.get("limit", 12000))
    if offset < 0 or not 1 <= limit <= 24000:
        raise ValueError("offset >= 0, limit 1~24000이 필요합니다")
    path = request.get("path")
    if path is None:
        page = evidence_store().read_evidence(request.get("id"), offset, limit)
    else:
        if (not isinstance(path, list) or len(path) > 16 or
                any(type(p) not in (str, int) for p in path)):
            raise ValueError("path는 객체 키·0 이상 배열 인덱스의 배열입니다(최대 16단계)")
        page = evidence_store().read_evidence(request.get("id"), 0, None)
        value = json.loads(page["text"])
        for part in path:
            value = _decode_json(value)
            if isinstance(value, dict) and isinstance(part, str) and part in value:
                value = value[part]
            elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
                value = value[part]
            else:
                raise ValueError(f"저장된 결과에 경로 {path!r}가 없습니다 (실패: {part!r})")
        value = _decode_json(value)
        text = json.dumps(value, ensure_ascii=False, indent=2)
        page.update(source_chars=page["chars"], chars=len(text), path=path,
                    offset=offset, text=text[offset:offset + limit])
    page["next_offset"] = offset + len(page["text"]) if offset + len(page["text"]) < page["chars"] else None
    from episode_logger import record_trajectory_event
    record_trajectory_event("context.result_read", {
        "evidence_id": request.get("id"), "offset": offset, "chars": len(page["text"]),
        "selected_path": path is not None, "has_more": page["next_offset"] is not None,
    })
    return page


def _decode_json(value):
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def _compact_currency(value):
    """items와 함께 온 큰 보조 원자료는 표시 사본에서만 참조로 접는다."""
    from ibl_honesty import HONESTY_KEYS
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        return value
    out = dict(value)
    preserve = set(HONESTY_KEYS) | {"items", "rows", "text", "content", "_preview", "_display",
                                  "error", "warning", "reason", "traceback"}
    omitted = {}
    for key, item in value.items():
        if key in preserve or not isinstance(item, (dict, list, str)):
            continue
        size = len(json.dumps(item, ensure_ascii=False, default=str))
        if size > 3000:
            omitted[key] = {"chars": size, "type": type(item).__name__}
            if isinstance(item, list):
                omitted[key]["count"] = len(item)
            out.pop(key)
    if omitted:
        out["_model_omitted"] = omitted
    return out


def _bound(value, cap=1000):
    raw = json.dumps(value, ensure_ascii=False)
    return value if len(raw) <= cap else {"excerpt": raw[:cap], "total_chars": len(raw), "truncated": True}


def project_result(result, verbose=False):
    from ibl_envelope import diet_envelope, preview_envelope
    if not isinstance(result, dict):
        return result
    store = evidence_store()
    raw = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    ref = store.evidence(raw)
    out = diet_envelope(result, verbose=False)
    # 오류 본문도 크롤 전문을 품을 수 있다. 상태·오류 위치를 남기고 전문은 증거로 읽는다.
    if out.get("_results_summarized") and isinstance(out.get("results"), list):
        out = dict(out)
        rows = out["results"]
        out["results"] = [_bound(row) for row in rows[:40]]
        if len(rows) > 40:
            out["steps_omitted"] = len(rows) - 40
        from ibl_honesty import completion_evidence
        errors = completion_evidence(result)
        if errors:
            out["completion_issues"] = _bound(errors, 2000)
    # verbose는 새 실행의 중간 본문을 복제하는 스위치가 아니다. 전체는 read_result로 회수한다.
    # 파이프 결과의 JSON 문자열을 한 번 해제해 items 밖 data까지 같은 표시 정책에 넣는다.
    # 기존 final_result의 문자열/객체 타입과 작은 원문 바이트는 보존한다.
    if "final_result" in out:
        final = out["final_result"]
        value = _decode_json(final)
        compact = _compact_currency(value)
        if compact != value:
            out = {**out, "final_result": json.dumps(compact, ensure_ascii=False, default=str)
                   if isinstance(final, str) else compact}
    else:
        out = _compact_currency(out)
    out = preview_envelope(out, verbose=False)
    if out == result and len(raw) < 3000:
        return out
    out = dict(out)
    out["result_ref"] = {k: ref[k] for k in ("id", "chars")}
    out["result_ref"]["read"] = 'execute_ibl(code="", read_result={id,offset,limit,path?}); 원래 code를 재실행하지 마세요'
    out["_hint"] = ('파이프 최종 값은 final_result, 단일 결과는 이 객체입니다. 생략된 값은 result_ref로 조회. '
                    'path:["final_result","items"] 또는 ["items"]로 해당 값만 읽을 수 있습니다. '
                    '같은 턴 $변수는 원자료를 보존하므로 선택·필터에 재사용하세요.')
    # 문자열 JSON 속 중복도 정규화한 최종 값은 미리보기기가 소유한다.
    from episode_logger import record_trajectory_event
    record_trajectory_event("context.result_projected", {"raw_chars": len(raw),
                            "model_chars": len(json.dumps(out, ensure_ascii=False)),
                            "evidence_id": ref["id"], "verbose_requested": verbose})
    return out


def describe_actions(names, allowed_nodes):
    from ibl_access import load_nodes_raw, resolve_allowed_nodes
    from ibl_registry import self_can_run
    if not isinstance(names, list) or not 1 <= len(names) <= 6:
        raise ValueError("describe는 node:action 이름 1~6개 배열입니다")
    allowed = resolve_allowed_nodes(allowed_nodes)
    nodes = load_nodes_raw().get("nodes", {})
    answer = []
    for name in dict.fromkeys(names):
        node, action = name.split(":", 1)
        spec = nodes.get(node, {}).get("actions", {}).get(action)
        if not isinstance(spec, dict) or (allowed is not None and node not in allowed) or not self_can_run(node, action, spec):
            answer.append({"action": name, "error": "사용 가능한 액션이 아닙니다"})
        else:
            answer.append({"action": name, "definition": spec})
    return {"actions": answer, "executed": False}
