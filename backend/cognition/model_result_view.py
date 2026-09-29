"""모델에는 최종 내용 한 벌과 단계 상태만. 원 계약은 턴 증거로 보존한다."""
import json

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
    from supervision_store import current_evidence_store
    return current_evidence_store()


def read_result(request):
    offset, limit = int(request.get("offset", 0)), int(request.get("limit", DEFAULT_LIMIT))
    if offset < 0 or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"offset >= 0, limit 1~{MAX_LIMIT}이 필요합니다")
    path = request.get("path")
    stored = None
    if path is None:
        page = evidence_store().read_evidence(request.get("id"), offset, limit)
    else:
        if (not isinstance(path, list) or len(path) > MAX_PATH_DEPTH or
                any(type(p) not in (str, int) for p in path)):
            raise ValueError("path는 객체 키·0 이상 배열 인덱스의 배열입니다(최대 16단계)")
        page = evidence_store().read_evidence(request.get("id"), 0, None)
        stored = json.loads(page["text"])
        value = (_walk_typed(stored, path, path) if isinstance(stored, dict) and stored.get("edition") == 2
                 else _walk(stored, path))
        # 문자열 값은 원문 글자로 페이지한다 — 미리보기의 total·offset과 같은 좌표(69회차 F69-2).
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        page.update(source_chars=page["chars"], chars=len(text), path=path,
                    offset=offset, text=text[offset:offset + limit])
    all_masked = page.pop("masked_paths", [])
    shown = [p for p in all_masked if _overlaps(p, path or [])]
    if shown:
        page["masked_paths"] = shown[:20]
        page["masked_hint"] = ("이 범위의 ****는 저장 시 비밀 후보로 가린 자리이며 원래 값과 다릅니다(69회차 B69-5). "
                               "원래 값이 필요한 계산은 원천을 읽는 같은 프로그램 안에서 하세요.")
    # 입력 연결은 참조 해석기와 같은 규칙으로 판정한다 — 판본 2 업무 값은 wire 를 읽는다.
    input_blocked = _masked_selection(all_masked, _value_source(stored, path or []))
    page["next_offset"] = offset + len(page["text"]) if offset + len(page["text"]) < page["chars"] else None
    page["next_read"] = ({"id": request.get("id"), "offset": page["next_offset"],
                          "limit": limit, **({"path": path} if path is not None else {})}
                         if page["next_offset"] is not None else None)
    # 끝 페이지와 전체 읽기는 다르다. 현재 응답이 전달한 범위만 표시한다.
    complete = offset == 0 and page["next_offset"] is None
    page["read_scope"] = {"path": path if path is not None else [],
                          "start": offset, "end": offset + len(page["text"]),
                          "total_chars": page["chars"], "complete": complete,
                          # text = 선택한 문자열의 원문 글자, json = 선택 값의 JSON, stored = 저장본 그대로
                          "format": "stored" if path is None else "text" if isinstance(value, str) else "json"}
    if complete:
        page["read_hint"] = ("선택 경로 전체(하위 내용 포함)를 전달했습니다. 현재 문맥에 이 본문이 "
                             "남아 있으면 하위 경로를 다시 읽지 말고 사용하세요. 가공은 input_args로 연결하세요.")
    # 조회자가 고른 페이지를 MCP/프로바이더의 액션당 16K 한도로 다시 접지 않는다.
    # 문서와 같은 표시 계약을 사용해 JSON escaping·다음 조회 인자까지 함께 전달한다.
    page["_display"] = {"max_chars": limit}
    # 읽은 페이지를 재작성하지 않고 선택한 전체 값을 다음 프로그램에 연결한다.
    if input_blocked:
        page["input_unavailable"] = _MASKED_INPUT
    else:
        page["input_args"] = {"입력": {"$ref": request.get("id"), "path": path if path is not None else []}}
    from episode_logger import record_trajectory_event
    record_trajectory_event("context.result_read", {
        "evidence_id": request.get("id"), "offset": offset, "chars": len(page["text"]),
        "selected_path": path is not None, "has_more": page["next_offset"] is not None,
        "path": path if path is not None else [], "complete": complete,
    })
    return page


def _decode_json(value):
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def _walk(value, path):
    """저장 결과 안의 실제 키/인덱스 경로 — read_result 와 inputs 참조가 같은 규칙으로 걷는다."""
    for part in path:
        value = _decode_json(value)
        if isinstance(value, dict) and isinstance(part, str) and part in value:
            value = value[part]
        elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
            value = value[part]
        else:
            raise ValueError(f"저장된 결과에 경로 {path!r}가 없습니다 (실패: {part!r})")
    return _decode_json(value)


def _overlaps(a, b):
    """두 경로 중 하나가 다른 하나의 접두인가 — 선택이 가린 자리를 품거나 그 안에 있다."""
    n = min(len(a), len(b))
    return list(a[:n]) == list(b[:n])


def _wire(stored, key):
    wire = stored.get(key) if isinstance(stored, dict) else None
    return wire if isinstance(wire, dict) and "data" in wire else None


def _value_source(stored, selection):
    """참조가 실제로 읽는 저장본 자리. 판본 2의 업무 값·부분 결과는 손실 없는 wire 위를 걷는다."""
    if isinstance(stored, dict) and stored.get("edition") == 2:
        if selection[:1] == ["value"] and _wire(stored, "value_wire"):
            return ["value_wire"]
        if selection[:2] == ["diagnostic", "partial"] and _wire(stored, "partial_wire"):
            return ["partial_wire"]
    return list(selection)


def _masked_selection(masked, source):
    """선택한 값이 저장 시 가린 자리와 겹치는가. wire 안 위치는 값 경로로 대응하지 않으므로 한 곳이라도 가려지면 전체."""
    if source[:1] in (["value_wire"], ["partial_wire"]):
        return any(not p or p[:1] == source[:1] for p in masked)
    return any(_overlaps(p, source) for p in masked)


_MASKED_INPUT = ("저장 사본의 원형 보존을 확인할 수 없거나 비밀 후보로 가린 자리(****)가 이 값에 있습니다. 원래 값은 영속 저장하지 않으므로 "
                 "참조로 넘기면 가려진 문자열이 업무 값이 됩니다. 이 값이 필요한 계산은 원천을 읽는 같은 프로그램 안에서 하세요.")


def _walk_typed(value, path, full_path):
    """wire 를 푼 타입 값 위의 경로. 문자열 값을 JSON 으로 다시 해석하지 않는다."""
    for part in path:
        if isinstance(value, dict) and isinstance(part, str) and part in value:
            value = value[part]
        elif isinstance(value, (list, tuple)) and type(part) is int and 0 <= part < len(value):
            value = value[part]
        else:
            raise ValueError(f"저장된 결과에 경로 {full_path!r}가 없습니다 (실패: {part!r})")
    return value


def _is_reference(value):
    return isinstance(value, dict) and isinstance(value.get("$ref"), str) and set(value) <= {"$ref", "path"}


def _resolve_reference(name, value, notes, at):
    """참조 하나를 업무 값으로 — 최상위·목록·레코드 안이 모두 이 한 규칙을 쓴다."""
    ref_id, path = value["$ref"], value.get("path")
    where = f"inputs.{name}" + "".join(f"[{p!r}]" for p in at)
    if path is not None and (not isinstance(path, list) or len(path) > MAX_PATH_DEPTH
                             or any(type(p) not in (str, int) for p in path)):
        raise ValueError(f"{where}: path는 객체 키·0 이상 배열 인덱스의 배열입니다(최대 {MAX_PATH_DEPTH}단계)")
    try:
        page = evidence_store().read_evidence(ref_id, 0, None)
    except (ValueError, OSError, TypeError) as exc:
        raise ValueError(f"{where}: 저장된 결과 {ref_id!r}를 읽을 수 없습니다: {exc}") from exc
    stored = _decode_json(page["text"])
    v2 = isinstance(stored, dict) and stored.get("edition") == 2
    if path is None:
        if v2 and (_wire(stored, "value_wire") or (stored.get("success") is True and "value" in stored)):
            selection = ["value"]
        elif v2:
            # 실패 봉투 자체는 업무 값이 아니다(69회차 B69-4). 명시 경로는 그대로 허용한다.
            raise ValueError(f"{where}: 참조한 실행은 실패해 업무 값이 없습니다(success=false). 성공한 가지는 "
                             "result_ref.partial_reads[].input_args로, 진단이 필요하면 path를 [\"diagnostic\"]로 명시하세요.")
        elif isinstance(stored, dict) and "final_result" in stored:
            selection = ["final_result"]
        else:
            selection = []
    else:
        selection = list(path)
    source = _value_source(stored, selection)
    if _masked_selection(page.get("masked_paths", []), source):
        raise ValueError(f"{where}: {_MASKED_INPUT}")
    if source == ["value_wire"]:
        from ibl_v2_ir import unpack
        resolved = _walk_typed(unpack(stored["value_wire"]["data"]), selection[1:], selection)
    elif source == ["partial_wire"]:
        from ibl_v2_ir import unpack
        resolved = _walk_typed(unpack(stored["partial_wire"]["data"]), selection[2:], selection)
    elif v2 and selection[:2] == ["diagnostic", "partial"] and stored.get("partial_wire_error"):
        raise ValueError("부분 결과의 손실 없는 값 전송이 지원되지 않습니다. 원 실행의 진단과 프로토콜을 확인하세요.")
    else:
        resolved = _walk(stored, selection)
    notes.append({"name": name, **({"at": at} if at else {}), "id": ref_id,
                  "path": source if path is None and source == ["value_wire"] else selection,
                  "evidence": input_ref_evidence(stored),
                  "chars": len(json.dumps(resolved, ensure_ascii=False, default=str))})
    return resolved


def _resolve_nested(name, value, notes, at):
    """목록·레코드 안의 참조도 같은 규칙으로 푼다(69회차 B69-2). 참조 모양($ref·path만)이 아닌 $ref 객체는 데이터다."""
    if _is_reference(value):
        return _resolve_reference(name, value, notes, at)
    if isinstance(value, dict):
        return {k: _resolve_nested(name, v, notes, at + [k]) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_nested(name, v, notes, at + [i]) for i, v in enumerate(value)]
    return value


def resolve_input_refs(inputs):
    """inputs 값 자리의 참조를 저장 결과의 실제 값으로 푼다 — 앞 실행의 결과를 *복사 없이* 다음 프로그램에 넘기는 통로.

    형태: {"$ref": result_ref.id, "path": [키·인덱스…]}. 이름의 값 자리뿐 아니라 그 안의 목록·레코드 원소에도 쓴다.
    판본 2 봉투의 업무 값(path 생략 또는 ["value", …])과 부분 결과(["diagnostic","partial", …])는 손실 없는 wire 를 풀어
    걷는다 — 저장 사본의 공개 투영은 표시용이다(69회차 B69-1). 실패 봉투의 기본 참조와 저장 시 가린 자리는 거절한다.
    옛 봉투는 final_result, 둘 다 없으면 저장 본문 전체. 전송 절단 봉투의 스필 참조({"ref": {"path"…}, "_spilled": true})도 푼다.
    값은 여전히 *명시 입력*이다 — 이전 턴 변수의 자동 주입이 아니라 모델이 이름·출처를 적은 것만 들어온다(2026-09-26).
    실패는 ValueError 로 — 호출자가 실행 전 거절 봉투로 돌려준다."""
    if not isinstance(inputs, dict):
        return inputs, []
    if "$ref" in inputs:
        example = {"inputs": {"입력": {k: inputs[k] for k in ("$ref", "path") if k in inputs}},
                   "code": "return $입력"}
        raise ValueError("$ref는 inputs 자체가 아니라 이름의 값 자리에 둡니다. "
                         "입력 이름은 코드에서 사용하는 변수에 맞추세요: " + json.dumps(example, ensure_ascii=False))
    from common.spill import is_ref, resolve_ref
    out, notes = {}, []
    for name, value in inputs.items():
        if isinstance(value, dict) and "$ref" in value:
            if set(value) - {"$ref", "path"}:
                raise ValueError(f"inputs.{name}: $ref 참조에는 path만 함께 씁니다")
            out[name] = _resolve_reference(name, value, notes, [])
        elif is_ref(value):
            resolved, err = resolve_ref(value)
            if err:
                raise ValueError(f"inputs.{name}: {err}")
            out[name] = resolved
            notes.append({"name": name, "ref": value["ref"].get("path"),
                          "evidence": input_ref_evidence(resolved),
                          "chars": len(json.dumps(resolved, ensure_ascii=False, default=str))})
        else:
            out[name] = _resolve_nested(name, value, notes, [])
    if notes:
        try:
            from episode_logger import record_trajectory_event
            record_trajectory_event("context.input_ref_resolved", {
                "inputs": sorted({n["name"] for n in notes}), "chars": sum(n["chars"] for n in notes)})
        except Exception:
            pass
    return out, notes


def input_evidence_by_name(notes):
    """실행기에 넘길 이름별 입력 근거. 한 이름 안의 여러 참조(목록·레코드 원소)는 불완전 여부를 합친다."""
    grouped = {}
    for note in notes:
        grouped.setdefault(note["name"], []).append(note)
    out = {}
    for name, group in grouped.items():
        if len(group) == 1 and not group[0].get("at"):
            out[name] = group[0]
        else:
            out[name] = {"name": name, "refs": group, "evidence": {
                "incomplete": any((n.get("evidence") or {}).get("incomplete") is True for n in group)}}
    return out


def input_ref_evidence(stored):
    """Preserve source status at the reference boundary, never infer it from business values."""
    from ibl_v2_ir import digest
    out = {"fingerprint": digest(stored)}
    if not isinstance(stored, dict):
        return out
    if stored.get("edition") == 2:
        # Only the execution envelope owns these fields. A selected value's
        # `error` or `source_complete` key is ordinary data.
        out["incomplete"] = stored.get("source_complete") is False
        out["execution_success"] = stored.get("success")
        out["run_id"] = (stored.get("resume") or {}).get("run_id")
    else:
        from ibl_honesty import completion_evidence, truncation_evidence
        incomplete = completion_evidence(stored)
        truncation = truncation_evidence(stored)
        out["incomplete"] = bool(incomplete or any(
            t.get("scope") != "selection" for t in truncation.get("truncations", [])))
    return out


def _selection_chars(item, *, typed=False):
    """read_result 가 그 경로에서 돌려줄 글자 수 — 문자열은 원문 글자, 구조는 JSON 페이지(F69-2와 같은 좌표)."""
    item = item if typed else _decode_json(item)
    return len(item) if isinstance(item, str) else len(json.dumps(item, ensure_ascii=False, indent=2, default=str))


def _read_reference(ref, result):
    """표시 사본이 아닌 원 봉투에서 조회 가능한 큰 필드를 찾는다(최대 6개)."""
    typed_value = result.get("edition") == 2 and "value" in result
    prefix = ["value"] if typed_value else ["final_result"] if "final_result" in result else []
    # Failure recovery opens the diagnostic, never megabytes of provenance by default.
    if not prefix and result.get('edition') == 2:
        prefix = next(([k] for k in ('diagnostic', 'issues', 'error') if result.get(k)), [])
    native = result.get('edition') == 2
    value = result[prefix[0]] if prefix else result
    value = value if native else _decode_json(value)
    paths = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (str, list, dict)):
                chars = _selection_chars(item, typed=native)
                if chars >= 400:
                    paths.append({"path": prefix + [key], "chars": chars})
        paths.sort(key=lambda entry: entry["chars"], reverse=True)
    elif isinstance(value, list):
        # 병렬 조회/each 결과에도 실제 본문 경로를 제공한다. 전체 묶음을 읽거나
        # 표시 사본의 잘린 문자열 길이로 원문의 offset을 추측할 필요가 없다.
        for index, item in enumerate(value):
            item = item if native else _decode_json(item)
            candidates = []
            fields = item.items() if isinstance(item, dict) else [(None, item)]
            for key, field in fields:
                if isinstance(field, (str, list, dict)):
                    chars = _selection_chars(field, typed=native)
                    if chars >= 400:
                        candidates.append({"path": prefix + [index] + ([] if key is None else [key]),
                                           "chars": chars})
            candidates.sort(key=lambda entry: entry["chars"], reverse=True)
            if candidates:
                paths.append(candidates[0])
            if len(paths) == 6:
                break
    paths = paths[:6]
    out = {
        **{k: ref[k] for k in ("id", "chars")},
        "max_limit": MAX_LIMIT,
        "paths": paths,
        "read_args": {"id": ref["id"], "offset": 0, "limit": DEFAULT_LIMIT,
                      "path": prefix if result.get('edition') == 2 or isinstance(value, list)
                      else paths[0]["path"] if paths else prefix},
        "read": 'execute_ibl(code="", read_result=result_ref.read_args); 일부만 필요하면 paths에서 path를 선택. 다음 페이지는 next_read 그대로. read_scope.complete=true인 본문이 문맥에 있으면 재독하지 마세요. 원래 code를 재실행하지 마세요',
    }
    masked = ref.get("masked_paths") or []
    if typed_value and _masked_selection(masked, _value_source(result, ["value"])):
        out["input_unavailable"] = _MASKED_INPUT
    elif typed_value:
        wire = result.get("value_wire")
        value_path = {} if isinstance(wire, dict) and "data" in wire else {"path": ["value"]}
        out["input_args"] = {"입력": {"$ref": ref["id"], **value_path}}
        out["input_hint"] = "다음 execute_ibl의 inputs에 input_args를 넣으면 $입력은 이미 업무 값입니다(.value를 다시 붙이지 않습니다). 이름 변경·path 선택 가능. 가공은 참조로 하고 판단에 필요한 경로만 read_result로 읽으세요."
    diagnostic = result.get("diagnostic") or {}
    if result.get("edition") == 2 and isinstance(diagnostic, dict):
        partial = diagnostic.get("partial")
        details = diagnostic.get("details") or {}
        indices = details.get("successful_indices") if isinstance(details, dict) else None
        # 원래 가지 번호와 압축된 partial 위치는 다르다. 확인된 대응만 제공한다.
        if (isinstance(partial, list) and isinstance(indices, list)
                and len(indices) == len(partial)
                and all(type(i) is int and i >= 0 for i in indices)
                and len(set(indices)) == len(indices)):
            reads = []
            for position, (branch, value) in enumerate(zip(indices[:6], partial[:6])):
                path = ["diagnostic", "partial", position]
                read = {"id": ref["id"], "path": path, "offset": 0, "limit": DEFAULT_LIMIT}
                entry = {"branch_index": branch, "partial_index": position, "read_args": read,
                         "input_args": {"입력": {"$ref": ref["id"], "path": path}}}
                if result.get("partial_wire_error"):
                    entry.pop("input_args")
                    entry["input_unavailable"] = "원 실행의 partial_wire_error를 확인하세요. 표시 값을 실제 값으로 대체하지 마세요."
                elif _masked_selection(masked, _value_source(result, path)):
                    entry.pop("input_args")
                    entry["input_unavailable"] = _MASKED_INPUT
                if isinstance(value, dict) and isinstance(value.get("text"), str):
                    entry["text_read_args"] = {**read, "path": path + ["text"]}
                reads.append(entry)
            out["partial_reads"] = reads
            out["partial_reads_omitted"] = len(partial) - len(reads)
            out["partial_mapping_read_args"] = {
                "id": ref["id"], "path": ["diagnostic", "details"],
                "offset": 0, "limit": DEFAULT_LIMIT}
    return out


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
    failures = [e for e in result.get('evidence', []) if e.get('kind') == 'tool_failure']
    out['evidence_summary'].update(tool_failures=len(failures),
                                  source_failures=sum(e.get('incomplete') is True for e in failures))
    if failures:
        out['evidence_summary']['failures'] = [
            {k: e[k] for k in ('id', 'action', 'code', 'failure_kind', 'incomplete') if k in e}
            for e in failures[:8]]
        out['evidence_summary']['failures_omitted'] = max(0, len(failures) - 8)
    from image_envelopes import harvest_images
    # Harvest before string/depth previews can destroy base64. The stored original
    # retains typed values; only this display copy loses duplicate wire bytes.
    image_view = {k: v for k, v in out.items() if k not in {"value_wire", "partial_wire"}}
    cleaned, images = harvest_images(json.dumps(image_view, ensure_ascii=False))
    if images:
        out = json.loads(cleaned)
    if len(json.dumps(out, ensure_ascii=False)) > policy["min_chars"]:
        out.pop("value_wire", None)
        out.pop("partial_wire", None)
        from model_value_preview import preview_value
        if "value" in out:
            out["value"], preview = preview_value(out["value"], policy["prose_chars"], ref["id"])
            if preview:
                out["_preview"] = preview
        diagnostic = out.get("diagnostic")
        if isinstance(diagnostic, dict) and diagnostic.get("has_partial"):
            shown, preview = preview_value(diagnostic.get("partial"), policy["prose_chars"],
                                          ref["id"], path=["diagnostic", "partial"])
            out["diagnostic"] = {**diagnostic, "partial": shown}
            if preview:
                out["partial_preview"] = preview
    out["result_ref"] = _read_reference(ref, result)
    out["_hint"] = ("판본 2의 업무 값은 value, 손실 없는 타입 전송은 value_wire입니다. "
                    + ("다음 계산은 inputs:result_ref.input_args로 연결하고, 판단에 필요한 본문만 read_args로 읽으세요. "
                       if "input_args" in out["result_ref"] else "진단을 확인하고 완료된 읽기가 있으면 continuation으로 부분 수리를 이어가세요. ")
                    + "success는 실행 상태이며 업무 완료·자료 완전성을 대신 판정하지 않습니다.")
    if images:
        out["images"] = [{**{k: v for k, v in image.items() if k != "b64"},
                          "base64": image["b64"]} for image in images]
        out["_hint"] += " 이미지는 별도 이미지 블록으로 첨부됩니다. base64 원문을 되읽지 마세요."
    # 원문·복구 참조까지 붙인 표시 사본만 예산 안에 있을 때 전달 한도를 협상한다.
    if len(raw) > policy["min_chars"] and len(json.dumps(out, ensure_ascii=False)) <= 2 * policy["prose_chars"]:
        out["_display"] = {"max_chars": policy["prose_chars"]}
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


def observed_returns_of_alias(alias):
    """관용구의 관측 반환 필드(returns_observed JSON) — describe 응답에만 전체를 싣는다."""
    try:
        from ibl_usage_db import IBLUsageDB
        row = IBLUsageDB().find_phrase_by_alias(alias, edition=2)
        raw = (row or {}).get("returns_observed") or ""
        obs = json.loads(raw) if raw else {}
        return obs if isinstance(obs, dict) and obs.get("keys") else {}
    except Exception:
        return {}


def observed_returns(name):
    """describe 에 싣는 관측 반환 모양 — 액션·op(#)·변이(@) 항목 전부. 카탈로그 줄이 아니라 조회 응답에만(토큰 예산)."""
    try:
        from ibl_access import return_shapes
        shapes = return_shapes() or {}
    except Exception:
        return {}
    return {k: {f: v[f] for f in ("kind", "keys", "more", "observed", "source") if f in v}
            for k, v in shapes.items()
            if isinstance(v, dict) and (k == name or k.startswith(name + "#") or k.startswith(name + "@"))}


def describe_actions(names, allowed_nodes, edition=None, program=None):
    from ibl_access import load_nodes_raw, resolve_allowed_nodes
    from ibl_registry import self_can_run
    if not isinstance(names, list) or not 1 <= len(names) <= 6:
        raise ValueError("describe는 node:action 또는 fn:이름 1~6개 배열입니다")
    if any(not isinstance(name, str) or name.count(":") != 1
           or any(not part.strip() for part in name.split(":")) for name in names):
        raise ValueError('describe는 ["node:action"] 또는 ["fn:함수이름"] 형식입니다. 함수 이름 앞에 fn:을 붙이세요.')
    if edition is None:
        edition = 2  # 모델의 새 작성·계약 조회 기본 판본과 일치한다.
    allowed = resolve_allowed_nodes(allowed_nodes)
    nodes = load_nodes_raw().get("nodes", {})
    answer = []
    runtime_registry = None
    local = None
    for name in dict.fromkeys(names):
        node, action = name.split(":", 1)
        if node == "fn" and edition == 2:
            from ibl_v2_store import describe, program_functions
            if local is None:
                # 함께 온 코드의 지역 정의가 저장 함수보다 먼저 — 실행기의 이름 해소 순서와 같다.
                local = program_functions(program, allowed) if program else {}
            if action in local:
                answer.append({"action": name, "definition": local[action]})
                continue
            definition = describe(action, allowed)
            if definition.get("error"):
                answer.append({"action": name, **definition})
                continue
            observed = observed_returns_of_alias(action)
            if observed:
                definition = {**definition, "observed_returns": observed,
                              "observed_note": "실행이 실제로 돌려준 최상위 필드(선언 아님). runs=관측 횟수."}
            guards = definition.get("guards")
            if guards:
                # Callers need the contract; per-expression diagnostics belong to
                # explicit inspection, not every invocation's model context.
                ref = evidence_store().evidence(json.dumps(definition, ensure_ascii=False))
                definition = {k: v for k, v in definition.items() if k != "guards"}
                definition["runtime_checks"] = definition.get("guards_total", len(guards))
                definition["result_ref"] = _read_reference(ref, {"guards": guards})
            answer.append({"action": name, "definition": definition})
            continue
        spec = nodes.get(node, {}).get("actions", {}).get(action)
        if not isinstance(spec, dict) or (allowed is not None and node not in allowed) or not self_can_run(node, action, spec):
            answer.append({"action": name, "error": "사용 가능한 액션이 아닙니다"})
        else:
            if edition == 2:
                from ibl_v2_adapters import load_registry
                if runtime_registry is None:
                    runtime_registry = load_registry()
                adapter = runtime_registry.get(name)
                if adapter is None:
                    answer.append({"action": name, "error": "현재 실행 계약이 없는 액션입니다"})
                    continue
                # Inspection consumes the same schema-resolved contract as the
                # compiler. Never independently reconstruct legacy parameters.
                contract = {k: v for k, v in adapter.contract.items()
                            if k not in {"analysis", "implementation_fingerprint"}}
                spec = {**{k: spec[k] for k in ("description", "guides", "group", "runs_on") if k in spec},
                        **({"target_description": spec["target_description"]}
                           if adapter.contract.get("adapter", {}).get("protocol") in {"legacy-envelope", "document-value/1"}
                           and spec.get("target_description_edition", 2) == edition
                           and spec.get("target_description") else {}),
                        "callable_contract": contract,
                        "operations": (spec.get("ops") or {}).get("values", {})}
                observed = observed_returns(name)
                if observed:
                    spec = {**spec, "observed_returns": observed,
                            "observed_note": "fixture·실사용에서 관측된 반환 필드(선언 아님). 관측 밖 이름 접근은 check 경고."}
            answer.append({"action": name, "definition": spec})
    return {"actions": answer, "executed": False}
