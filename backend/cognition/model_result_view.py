"""모델에는 최종 내용 한 벌과 단계 상태만. 원 계약은 턴 증거로 보존한다."""
import json
from hashlib import sha256

from result_read_contract import DEFAULT_LIMIT, MAX_LIMIT, MAX_PATH_DEPTH


def display_policy():
    from ibl_envelope import PREVIEW_DEFAULT
    from ibl_retyping import load_policy_block
    defaults = {**PREVIEW_DEFAULT, "metadata_chars": 3000, "step_rows": 40,
                "step_chars": 1000, "issues_chars": 2000}
    configured = load_policy_block("envelope_preview", defaults)
    return {key: configured[key] if type(configured[key]) is int and configured[key] > 0 else value
            for key, value in defaults.items()}


def evidence_store():
    from supervision_bus import current
    controller = current()
    if controller:
        return controller.store
    from runtime_utils import get_base_path
    from thread_context import execution_key
    from supervision_store import TurnStore
    # 턴 밖 직접 호출도 다른 사용자의 증거와 섞이지 않는 독립 네임스페이스다.
    agent, task = execution_key()
    from member_runtime import is_member, private_path
    root = private_path("tool_evidence") if is_member() else get_base_path() / "data" / "spill" / "tool_evidence"
    # 구분자를 포함한 신원도 충돌하지 않는다. 구분이 명백한 기존 작업의 참조는 유지한다.
    legacy = root / sha256(f"{agent or None}:{task or None}".encode()).hexdigest()
    if ":" not in agent and ":" not in task and legacy.is_dir():
        return TurnStore(legacy)
    key = sha256(json.dumps([agent, task], ensure_ascii=False).encode()).hexdigest()
    return TurnStore(root / key)


def read_result(request):
    offset, limit = int(request.get("offset", 0)), int(request.get("limit", DEFAULT_LIMIT))
    if offset < 0 or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"offset >= 0, limit 1~{MAX_LIMIT}이 필요합니다")
    path = request.get("path")
    if path is None:
        page = evidence_store().read_evidence(request.get("id"), offset, limit)
    else:
        if (not isinstance(path, list) or len(path) > MAX_PATH_DEPTH or
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
    page["next_read"] = ({"id": request.get("id"), "offset": page["next_offset"],
                          "limit": limit, **({"path": path} if path is not None else {})}
                         if page["next_offset"] is not None else None)
    # 조회자가 고른 페이지를 MCP/프로바이더의 액션당 16K 한도로 다시 접지 않는다.
    # 문서와 같은 표시 계약을 사용해 JSON escaping·다음 조회 인자까지 함께 전달한다.
    page["_display"] = {"max_chars": limit}
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


def _read_reference(ref, result):
    """표시 사본이 아닌 원 봉투에서 조회 가능한 큰 필드를 찾는다(최대 6개)."""
    prefix = ["final_result"] if "final_result" in result else []
    value = _decode_json(result["final_result"] if prefix else result)
    paths = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (str, list, dict)):
                chars = len(json.dumps(_decode_json(item), ensure_ascii=False, indent=2, default=str))
                if chars >= 400:
                    paths.append({"path": prefix + [key], "chars": chars})
    paths.sort(key=lambda entry: entry["chars"], reverse=True)
    paths = paths[:6]
    return {
        **{k: ref[k] for k in ("id", "chars")},
        "max_limit": MAX_LIMIT,
        "paths": paths,
        "read_args": {"id": ref["id"], "offset": 0, "limit": DEFAULT_LIMIT,
                      "path": paths[0]["path"] if paths else prefix},
        "read": 'execute_ibl(code="", read_result=result_ref.read_args); 다음 페이지는 next_read 그대로. 원래 code를 재실행하지 마세요',
    }


def _compact_currency(value, metadata_chars):
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
        if size > metadata_chars:
            omitted[key] = {"chars": size, "type": type(item).__name__}
            if isinstance(item, list):
                omitted[key]["count"] = len(item)
            out.pop(key)
    if omitted:
        out["_model_omitted"] = omitted
    return out


def _project_currency(value, metadata_chars, depth=0):
    """모델 사본에서만 병렬 봉투 직렬화를 풀고 동일 필드를 한 벌로 보인다."""
    if depth > 8:
        return value
    if isinstance(value, list):
        decoded = [_decode_json(v) for v in value]
        # 일반 텍스트 행을 임의로 JSON으로 해석하지 않는다. 통화 봉투 묶음만 푼다.
        if decoded and all(isinstance(v, (dict, list)) for v in decoded):
            return [_project_currency(v, metadata_chars, depth + 1) for v in decoded]
        return value
    if not isinstance(value, dict):
        return value
    out = dict(value)
    items = value.get("items")
    data = value.get("data")
    if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict) and isinstance(data, dict):
        from ibl_honesty import HONESTY_KEYS
        from common.value_semantics import structural_equal
        protected = set(HONESTY_KEYS) | {"source", "warning", "error", "traceback"}
        shared = [k for k, v in data.items() if k in items[0] and k not in protected and
                  structural_equal(v, items[0][k], lambda a, b: type(a) is type(b) and a == b)]
        if shared:
            candidate = {**out, "data": {k: v for k, v in data.items() if k not in shared},
                         "_model_shared": {"data": {"same_as": "items[0]", "fields": shared}}}
            if len(json.dumps(candidate, ensure_ascii=False)) < len(json.dumps(out, ensure_ascii=False)):
                out = candidate
    return _compact_currency(out, metadata_chars)


def _bound(value, cap=1000):
    raw = json.dumps(value, ensure_ascii=False)
    if len(raw) <= cap:
        return value
    # step/type/error와 정직 표지의 키·스칼라를 문자열 excerpt 속에 묻지 않는다.
    # 구조 비용은 전송 경계가 다루며 여기서는 진단 문자열만 표시 사본에서 접는다.
    def clip(item):
        if isinstance(item, str) and len(item) > cap:
            return item[:cap] + f"…(전체 {len(item)}자, result_ref 참조)"
        if isinstance(item, list):
            return [clip(v) for v in item]
        if isinstance(item, dict):
            return {k: clip(v) for k, v in item.items()}
        return item
    return clip(value)


def project_v2_result(result):
    """Typed values keep their meaning; verbose execution evidence stays on disk."""
    raw = json.dumps(result, ensure_ascii=False, default=str)
    ref = evidence_store().evidence(raw)
    policy = display_policy()
    out = {k: v for k, v in result.items() if k not in {"evidence", "recordings", "source_map"}}
    out["evidence_summary"] = {"events": len(result.get("evidence", [])),
                               "source_complete": result.get("source_complete")}
    if len(json.dumps(out, ensure_ascii=False)) > policy["min_chars"]:
        out.pop("value_wire", None)
        if "value" in out:
            def preview(value, depth=0):
                if depth >= 5 and isinstance(value, (dict, list)):
                    return "…(result_ref 참조)"
                if isinstance(value, list):
                    return [preview(v, depth + 1) for v in value[:6]]
                if isinstance(value, dict):
                    return {k: preview(v, depth + 1) for k, v in list(value.items())[:12]}
                if isinstance(value, str) and len(value) > 500:
                    return value[:500] + "…(result_ref 참조)"
                return value
            out["value"] = preview(out["value"])
        out["_preview"] = True
    out["result_ref"] = _read_reference(ref, result)
    out["_hint"] = ("판본 2의 업무 값은 value, 손실 없는 타입 전송은 value_wire입니다. "
                    "전체 값·소스맵·실행 증거는 result_ref.read_args로 조회하세요. 다음 호출 입력은 inputs에 명시합니다.")
    return out


def project_result(result, verbose=False):
    if isinstance(result, dict) and result.get("edition") == 2:
        return project_v2_result(result)
    from ibl_envelope import diet_envelope, preview_envelope
    if not isinstance(result, dict):
        return result
    store = evidence_store()
    raw = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    ref = store.evidence(raw)
    policy = display_policy()
    out = diet_envelope(result, verbose=False)
    # Preserve image bytes before text previewing can fold them into a result_ref.
    # Work on a serialized copy; raw evidence and live IBL variables stay intact.
    from image_envelopes import harvest_images
    cleaned, images = harvest_images(json.dumps(out, ensure_ascii=False, default=str))
    if images:
        out = json.loads(cleaned)
    # 오류 본문도 크롤 전문을 품을 수 있다. 상태·오류 위치를 남기고 전문은 증거로 읽는다.
    if out.get("_results_summarized") and isinstance(out.get("results"), list):
        out = dict(out)
        rows = out["results"]
        out["results"] = [_bound(row, policy["step_chars"]) for row in rows[:policy["step_rows"]]]
        if len(rows) > policy["step_rows"]:
            out["steps_omitted"] = len(rows) - policy["step_rows"]
        from ibl_honesty import completion_evidence
        errors = completion_evidence(result)
        if errors:
            out["completion_issues"] = _bound(errors, policy["issues_chars"])
    # verbose는 새 실행의 중간 본문을 복제하는 스위치가 아니다. 전체는 read_result로 회수한다.
    # 파이프 결과의 JSON 문자열을 한 번 해제해 items 밖 data까지 같은 표시 정책에 넣는다.
    # 기존 final_result의 문자열/객체 타입과 작은 원문 바이트는 보존한다.
    if "final_result" in out:
        final = out["final_result"]
        value = _decode_json(final)
        compact = _project_currency(value, policy["metadata_chars"])
        if compact != value:
            # 작은 기존 객체/문자열은 그대로. 바뀐 사본은 객체로 보내 이중 escaping을 없앤다.
            out = {**out, "final_result": compact}
    else:
        out = _project_currency(out, policy["metadata_chars"])
    out = preview_envelope(out, verbose=False, policy=policy)
    if not images and out == result and len(raw) < policy["min_chars"]:
        return out
    out = dict(out)
    out["result_ref"] = _read_reference(ref, result)
    out["_hint"] = ('파이프 최종 값은 final_result, 단일 결과는 이 객체입니다. 생략된 값은 result_ref로 조회. '
                    'result_ref.paths는 실제 원문 경로이며 read_args로 바로 읽을 수 있습니다. '
                    '같은 턴 $변수는 원자료를 보존하므로 선택·필터에 재사용하세요.')
    if images:
        out["images"] = [{"base64": e["b64"], "media_type": e.get("media_type", "image/png")}
                         for e in images]
        out["_hint"] += ' 이미지는 별도 이미지 블록으로 첨부됩니다. base64 원문을 분할 조회하지 마세요.'
    # 문자열 JSON 속 중복도 정규화한 최종 값은 미리보기기가 소유한다.
    from episode_logger import record_trajectory_event
    text_view = ({**out, "images": [{"media_type": e.get("media_type", "image/png")} for e in images]}
                 if images else out)
    record_trajectory_event("context.result_projected", {"raw_chars": len(raw),
                            "model_chars": len(json.dumps(text_view, ensure_ascii=False)),
                            "image_count": len(images),
                            "evidence_id": ref["id"], "verbose_requested": verbose})
    return out


def describe_actions(names, allowed_nodes, edition=None):
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
            if edition == 2:
                from ibl_v2_contracts import handler_contract
                spec = {**spec, "callable_contract": spec.get("callable_contract") or handler_contract(node, action, spec)}
            answer.append({"action": name, "definition": spec})
    return {"actions": answer, "executed": False}
