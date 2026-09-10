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
    page = evidence_store().read_evidence(request.get("id"), offset, limit)
    page["next_offset"] = offset + len(page["text"]) if offset + len(page["text"]) < page["chars"] else None
    return page


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
    out = preview_envelope(out, verbose=False)
    if out == result and len(raw) < 3000:
        return out
    out = dict(out)
    out["result_ref"] = {k: ref[k] for k in ("id", "chars")}
    out["result_ref"]["read"] = 'execute_ibl(code="", read_result={id,offset,limit}); 원래 code를 재실행하지 마세요'
    out["_hint"] = "최종 값은 final_result 한 벌. 중간 원문과 생략된 값은 result_ref로 읽습니다."
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
