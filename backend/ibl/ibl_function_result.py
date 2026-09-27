"""Function return boundary: retain values, reference execution detail, qualify blame."""
from common.currency import coerce_json_param


def compact_execution(out):
    """Call only after return selection. Never traverse or rewrite business values."""
    if not isinstance(out, dict) or out.get("_results_summarized"):
        return out
    rows = out.get("results")
    if not isinstance(rows, list) or not rows:
        return out
    from supervision_store import current_evidence_store
    from result_read_contract import DEFAULT_LIMIT
    from ibl_envelope import summarize_step
    from ibl_honesty import completion_evidence

    try:
        ref = current_evidence_store().evidence(out)
    except (OSError, ValueError, TypeError):
        # Storage failure must not discard evidence or replay completed effects.
        return {**out, "execution_ref_error": "실행 기록 저장 실패 — 원문을 그대로 반환합니다."}
    result = {**out, "results": [summarize_step(row) for row in rows],
              "_results_summarized": True,
              "execution_ref": {
                  "id": ref["id"], "chars": ref["chars"], "scope": "current_execution",
                  "read_args": {"id": ref["id"], "path": ["results"],
                                "offset": 0, "limit": DEFAULT_LIMIT},
                  "read": "execute_ibl(code=\"\", read_result=execution_ref.read_args); 다음 페이지는 next_read 그대로. 재실행 불필요.",
              }}
    incomplete = completion_evidence(out)
    if incomplete:
        result["incomplete_steps"] = incomplete
    return result


def failure_origin(out, steps, required):
    """Use producer diagnostics and direct argument flow, never error prose.

    A field mismatch identifies an input boundary, not proof that the caller is
    culpable: a hard-coded field name in the definition could itself be wrong.
    Internal transformations, nested failures and opaque exceptions stay unknown.
    """
    origin = {"kind": "unknown", "definition_failure": False}
    leaf = coerce_json_param(out.get("final_result"))
    tb = out.get("traceback") or {}
    frames = tb.get("frames") or []
    if not isinstance(leaf, dict) or len(frames) != 1:
        return origin
    frame = frames[0]
    if not isinstance(frame, dict) or type(frame.get("step")) is not int:
        return origin
    index = frame["step"] - 1
    if frame.get("kind") != "pipeline" or not 0 <= index < len(steps):
        return origin
    detail = leaf.get("input_contract")
    if leaf.get("error_code") != "MISSING_FIELDS" or not isinstance(detail, dict):
        return origin
    origin.update(step=index + 1, input_contract=detail)
    previous = steps[index - 1] if index > 0 else {}
    if not isinstance(previous, dict) or not isinstance(steps[index], dict):
        return origin
    # Only an untransformed, whole caller parameter immediately feeding the
    # failed operation is known. Do not infer provenance through arbitrary code.
    if (previous.get("_var_emit") and previous.get("_free")
            and previous.get("name") in required and not previous.get("path")
            and not steps[index].get("_seq_boundary")
            and not set((steps[index].get("params") or {})) & {"items", "data", "input", "_prev_result"}):
        origin.update(kind="input_shape", parameter=previous["name"])
    return origin


def record_idiom_outcome(code, out, elapsed_ms, origin=None):
    """Keep execution failures observable without treating every one as bad code."""
    ok = out.get("success", True) is True
    origin = origin or {"kind": "unknown", "definition_failure": False}
    attributed = ok or origin.get("definition_failure") is True
    if attributed:
        from ibl_usage_db import IBLUsageDB
        IBLUsageDB().update_success_by_code(code, ok, elapsed_ms=elapsed_ms if ok else None)
    from episode_logger import record_trajectory_event
    from hashlib import sha256
    record_trajectory_event("ibl.function_feedback", {
        "code_sha256": sha256(code.encode()).hexdigest(), "success": ok,
        "attributed": attributed, "failure_origin": None if ok else origin,
    })
    return attributed


def annotate_failure(out, name, origin, code=None):
    out["failure_origin"] = origin
    if origin.get("definition_failure") and code:
        from hippo_tree import phrase_def_block
        out["def"] = phrase_def_block(name, code)
        out["hint"] = f"[fn:{name}] 정의의 오류를 확인했습니다. 제공된 def의 해당 문장을 수정하세요."
    elif origin["kind"] == "input_shape":
        parameter = origin["parameter"]
        out["hint"] = (f"[fn:{name}]의 ${parameter} 입력과 필요한 필드가 맞지 않습니다. "
                       "병렬 결과의 가지·넘긴 값과 호출 계약을 먼저 확인하세요. "
                       "관용구 정의의 결함으로 확정하지 않았으며 실패 점수 귀속은 보류했습니다.")
    else:
        out["hint"] = (f"[fn:{name}] 실행 실패의 원인 귀속은 미확정입니다. "
                       "입력·실패 단계·원천 상태를 확인하세요. 정의 수정과 실패 점수 귀속은 보류했습니다.")
    return out
