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
    if request.get("calls"):
        turns = evidence_store().call_history()
        return {"turns": turns,
                "hint": "input.id 를 read_result:{id, path:[\"code\"]}로 읽으면 그때 실행한 프로그램 원문입니다. "
                        "같은 일을 다른 자료로 반복할 때는 통과한 프로그램(is_error 없는 마지막 호출들)을 읽어 "
                        "경로·입력만 바꿔 다시 실행하세요. result.id 는 그 결과이며 $ref 입력으로 이어 쓸 수 있습니다."}
    if not request.get("id"):
        raise ValueError("read_result에는 id 또는 calls:true가 필요합니다")
    offset, limit = int(request.get("offset", 0)), int(request.get("limit", DEFAULT_LIMIT))
    if offset < 0 or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"offset >= 0, limit 1~{MAX_LIMIT}이 필요합니다")
    path = request.get("path")
    stored = None
    if path is None:
        page = evidence_store().read_evidence_across_turns(request.get("id"), offset, limit)
    else:
        if (not isinstance(path, list) or len(path) > MAX_PATH_DEPTH or
                any(type(p) not in (str, int) for p in path)):
            raise ValueError("path는 객체 키·0 이상 배열 인덱스의 배열입니다(최대 16단계)")
        page = evidence_store().read_evidence_across_turns(request.get("id"), 0, None)
        stored = json.loads(page["text"])
        value = (_walk_typed(stored, path, path) if isinstance(stored, dict) and stored.get("edition") == 2
                 else _walk(stored, path))
        # 문자열 값은 원문 글자로 페이지한다 — 미리보기의 total·offset과 같은 좌표(69회차 F69-2).
        text = value if isinstance(value, str) else page_json(value)
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
    partial_problem = _partial_input_problem(stored, path or [])
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
    elif partial_problem:
        page["input_unavailable"] = partial_problem
    else:
        page["input_args"] = {"입력": {"$ref": request.get("id"), "path": path if path is not None else []}}
    from episode_logger import record_trajectory_event
    record_trajectory_event("context.result_read", {
        "evidence_id": request.get("id"), "offset": offset, "chars": len(page["text"]),
        "selected_path": path is not None, "has_more": page["next_offset"] is not None,
        "path": path if path is not None else [], "complete": complete,
    })
    return page


def page_json(value):
    """read_result 가 구조 값을 넘기는 글자 표기 — 목록은 행마다, 레코드는 필드마다 한 줄.

    들여쓰기 JSON 은 같은 내용을 1.3배로 불렸다(ep4214: 자막 480행 32K자 → 41K자). 줄 단위 페이지는
    지키되 키마다 붙던 들여쓰기·줄바꿈을 없앤다. 글자 수 좌표(_selection_chars)도 이 표기를 쓴다."""
    def one(item):
        return json.dumps(item, ensure_ascii=False, default=str)
    if isinstance(value, (list, tuple)) and value:
        return "[\n" + ",\n".join(one(item) for item in value) + "\n]"
    if isinstance(value, dict) and value:
        return "{\n" + ",\n".join(f"{one(str(key))}: {one(item)}" for key, item in value.items()) + "\n}"
    return one(value)


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


def _partial_source(stored, selection):
    """Walk only runtime-owned diagnostic edges, never similarly named user data."""
    if not isinstance(stored, dict) or stored.get("edition") != 2:
        return None
    node, prefix = stored.get("diagnostic"), ["diagnostic"]
    while isinstance(node, dict):
        partial_path = prefix + ["partial"]
        if selection[:len(partial_path)] == partial_path:
            owner = stored if len(prefix) == 1 else node
            wire_path = ["partial_wire"] if len(prefix) == 1 else prefix + ["partial_wire"]
            return owner, wire_path, selection[len(partial_path):]
        edge = selection[len(prefix):len(prefix) + 3]
        if selection[:len(prefix)] != prefix or len(edge) != 3 or edge[:2] != ["details", "errors"]:
            break
        details = node.get("details")
        errors = details.get("errors") if isinstance(details, dict) else None
        if not isinstance(errors, dict) or not isinstance(edge[2], str) or edge[2] not in errors:
            break
        node, prefix = errors[edge[2]], prefix + edge
    return None


def _partial_input_problem(stored, selection):
    partial = _partial_source(stored, selection)
    if partial:
        owner, wire_path, _ = partial
        if owner.get("partial_wire_error"):
            return "부분 결과의 손실 없는 값 전송이 지원되지 않습니다. 원 실행의 진단과 프로토콜을 확인하세요."
        if len(wire_path) > 1 and not _wire(owner, "partial_wire"):
            return "이 실패 가지에는 손실 없는 부분 값이 없습니다. 원문 읽기는 가능하며 표시값을 실제 값으로 대체하지 마세요."
    return None


def _value_source(stored, selection):
    """참조가 실제로 읽는 저장본 자리. 판본 2의 업무 값·부분 결과는 손실 없는 wire 위를 걷는다."""
    if isinstance(stored, dict) and stored.get("edition") == 2:
        if selection[:1] == ["value"] and _wire(stored, "value_wire"):
            return ["value_wire"]
        partial = _partial_source(stored, selection)
        if partial and _wire(partial[0], "partial_wire"):
            return partial[1]
    return list(selection)


def _masked_selection(masked, source):
    """선택한 값이 저장 시 가린 자리와 겹치는가. wire 안 위치는 값 경로로 대응하지 않으므로 한 곳이라도 가려지면 전체."""
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


def _resolve_reference(name, value, notes, at, store=None):
    """참조 하나를 업무 값으로 — 최상위·목록·레코드 안이 모두 이 한 규칙을 쓴다."""
    ref_id, path = value["$ref"], value.get("path")
    where = f"inputs.{name}" + "".join(f"[{p!r}]" for p in at)
    if path is not None and (not isinstance(path, list) or len(path) > MAX_PATH_DEPTH
                             or any(type(p) not in (str, int) for p in path)):
        raise ValueError(f"{where}: path는 객체 키·0 이상 배열 인덱스의 배열입니다(최대 {MAX_PATH_DEPTH}단계)")
    try:
        page = (store or evidence_store()).read_evidence_across_turns(ref_id, 0, None)
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
    partial = _partial_source(stored, selection)
    if _masked_selection(page.get("masked_paths", []), source):
        raise ValueError(f"{where}: {_MASKED_INPUT}")
    partial_problem = _partial_input_problem(stored, selection)
    if partial_problem:
        raise ValueError(f"{where}: {partial_problem}")
    if source == ["value_wire"]:
        from ibl_v2_ir import unpack
        resolved = _walk_typed(unpack(stored["value_wire"]["data"]), selection[1:], selection)
    elif partial and _wire(partial[0], "partial_wire"):
        from ibl_v2_ir import unpack
        resolved = _walk_typed(unpack(partial[0]["partial_wire"]["data"]), partial[2], selection)
    else:
        resolved = _walk(stored, selection)
    notes.append({"name": name, **({"at": at} if at else {}), "id": ref_id,
                  "path": source if path is None and source == ["value_wire"] else selection,
                  "evidence": input_ref_evidence(stored),
                  # 앞 턴이 저장한 값이면 그 턴을 밝힌다 — 그때 조회한 값이지 지금 원천의 상태가 아니다.
                  **({"from_turn": page["from_turn"]} if page.get("from_turn") else {}),
                  "chars": len(json.dumps(resolved, ensure_ascii=False, default=str))})
    return resolved


def _resolve_nested(name, value, notes, at, store=None):
    """목록·레코드 안의 참조도 같은 규칙으로 푼다(69회차 B69-2). 참조 모양($ref·path만)이 아닌 $ref 객체는 데이터다."""
    if _is_reference(value):
        return _resolve_reference(name, value, notes, at, store)
    if isinstance(value, dict):
        return {k: _resolve_nested(name, v, notes, at + [k], store) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_nested(name, v, notes, at + [i], store) for i, v in enumerate(value)]
    return value


def resolve_input_refs(inputs, *, store=None):
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
            out[name] = _resolve_reference(name, value, notes, [], store)
        elif is_ref(value):
            resolved, err = resolve_ref(value)
            if err:
                raise ValueError(f"inputs.{name}: {err}")
            out[name] = resolved
            notes.append({"name": name, "ref": value["ref"].get("path"),
                          "evidence": input_ref_evidence(resolved),
                          "chars": len(json.dumps(resolved, ensure_ascii=False, default=str))})
        else:
            out[name] = _resolve_nested(name, value, notes, [], store)
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
    return len(item) if isinstance(item, str) else len(page_json(item))


def _failed_partial_references(ref, result):
    """Bounded references to partial data inside failed parallel branches.

    These are not successful branches. Keep their failure and original envelope
    reachable even when the useful row list is selected for the default read.
    """
    pending = [(result.get("diagnostic"), ["diagnostic"], [])]
    reads, found, visited, limited = [], 0, 0, False
    while pending and visited < 64:
        fault, prefix, branches = pending.pop(0)
        visited += 1
        if not isinstance(fault, dict):
            continue
        details = fault.get("details")
        errors = details.get("errors") if isinstance(details, dict) else None
        if isinstance(errors, dict):
            for index, child in errors.items():
                if not isinstance(index, str) or not index.isascii() or not index.isdecimal():
                    continue
                if len(index) > 10 or str(int(index)) != index:
                    continue
                child_path = prefix + ["details", "errors", index]
                if len(child_path) + 2 > MAX_PATH_DEPTH or visited + len(pending) >= 64:
                    limited = True
                    continue
                pending.append((child, child_path, branches + [int(index)]))
        # Root partial success mappings already have partial_reads. This list
        # specifically exposes data hidden in the failed branches' diagnostics.
        if not branches or fault.get("has_partial") is not True:
            continue
        found += 1
        if len(reads) == 6:
            continue
        path = prefix + ["partial"]
        value = fault.get("partial")
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            path += ["items"]
        def request(at):
            return {"id": ref["id"], "path": at, "offset": 0, "limit": DEFAULT_LIMIT}
        entry = {"branch_path": branches, "source_complete": False,
                 "code": fault.get("code"), "kind": fault.get("kind"),
                 "read_args": request(path), "diagnostic_read_args": request(prefix),
                 "partial_read_args": request(prefix + ["partial"])}
        problem = _partial_input_problem(result, path)
        if problem:
            entry["input_unavailable"] = problem
        elif _masked_selection(ref.get("masked_paths") or [], _value_source(result, path)):
            entry["input_unavailable"] = _MASKED_INPUT
        else:
            entry["input_args"] = {"입력": {"$ref": ref["id"], "path": path}}
        reads.append(entry)
    if not reads and not limited:
        return {}
    return {"failed_partial_reads": reads, "failed_partial_reads_omitted": found - len(reads),
            "failed_partial_scan_incomplete": limited or bool(pending),
            "failed_partial_hint": "실패 가지에서 회수한 불완전 자료입니다. 오류 행·누락을 확인하고 필요한 부분만 읽거나 가공하세요. 진단 전문은 diagnostic_read_args로 조회합니다."}


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
    read_path = (prefix if result.get('edition') == 2 or isinstance(value, list)
                 else paths[0]["path"] if paths else prefix)
    # Only the explicit stored-function envelope declares items as its final
    # return. Ordinary records retain their whole-value default and semantics.
    function_items = (isinstance(value, dict) and value.get("_fn_result") is True
                      and isinstance(value.get("items"), list))
    if function_items:
        read_path = prefix + ["items"]
    out = {
        **{k: ref[k] for k in ("id", "chars")},
        "max_limit": MAX_LIMIT,
        "paths": paths,
        "read_args": {"id": ref["id"], "offset": 0, "limit": DEFAULT_LIMIT,
                      "path": read_path},
        "read": 'execute_ibl(code="", read_result=result_ref.read_args); 일부만 필요하면 paths에서 path를 선택. 다음 페이지는 next_read 그대로. read_scope.complete=true인 본문이 문맥에 있으면 재독하지 마세요. 원래 code를 재실행하지 마세요',
    }
    if function_items:
        out["read_hint"] = ("read_args는 함수의 최종 items 본문을 직접 엽니다. "
                            "execution_ref는 중간 실행 진단용입니다. "
                            "계산용 input_args는 전체 반환 값을 유지합니다.")
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
        out.update(_failed_partial_references(ref, result))
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


def retained_value_reference(value, *, complete=True, origin=None):
    """Reuse the existing typed, secret-masked evidence channel for repair values."""
    from ibl_v2_ir import pack, projection
    stored = {"edition": 2, "success": True, "source_complete": complete,
              "value": projection(value),
              "value_wire": {"protocol": "ibl-value/2", "data": pack(value)}}
    if origin:
        stored["origin"] = origin
    ref = evidence_store().evidence(json.dumps(stored, ensure_ascii=False))
    return _read_reference(ref, stored)


def retain_failed_inputs(result, inputs, notes=()):
    """A rejected program can change code without retyping its large arguments."""
    if (not isinstance(result, dict) or result.get("success") is True
            or result.get("ok") is True or not isinstance(inputs, dict) or not inputs):
        return
    args, unavailable = {}, {}
    for name, value in inputs.items():
        if not isinstance(name, str) or not name.isidentifier() or name in {"it", "i", "error"}:
            continue
        origins = [n for n in notes if n.get("name") == name]
        from ibl_v2_ir import Fault
        try:
            ref = retained_value_reference(value, complete=not any(
                n.get("evidence", {}).get("incomplete") for n in origins), origin=origins)
        except Fault:
            unavailable[name] = "입력값의 손실 없는 전송을 지원하지 않습니다. 원래 입력 오류를 먼저 수정하세요."
            continue
        if ref.get("input_args"):
            args[name] = ref["input_args"]["입력"]
        else:
            unavailable[name] = ref.get("input_unavailable", "원형 보존 미확인")
    result["request_inputs"] = {"input_args": args, "unavailable": unavailable,
        "hint": "수정 호출의 inputs로 input_args를 사용하세요. unavailable 이름은 원천에서 다시 공급해야 합니다. 입력 참조는 도구 재실행을 막지 않으므로 이전 실행은 continuation도 확인하세요."}


def completed_call_references(result):
    """Bound the display, not access to completed values and resolved failure inputs."""
    from ibl_v2_ir import unpack
    completed = [r for r in result.get("recordings", []) if "value" in r and "error" not in r]
    events = {event['id']: event for event in result.get('evidence', [])}

    def incomplete(receipt, arguments=False):
        if arguments and 'argument_incomplete' in receipt:
            return bool(receipt['argument_incomplete'])
        pending = (list(receipt.get('argument_evidence', [])) if arguments else
                   [event['id'] for event in events.values()
                    if event.get('kind') == 'invoke' and event.get('request_hash') == receipt.get('request_hash')])
        seen = set()
        while pending:
            eid = pending.pop()
            if eid in seen:
                continue
            seen.add(eid)
            event = events.get(eid, {})
            if event.get('incomplete') or arguments and not event:
                return True
            pending.extend(event.get('parents', []))
        return not arguments and bool((receipt.get('evidence') or {}).get('incomplete'))

    def entry(index, receipt, arguments=False):
        evidence = receipt.get("evidence") or {}
        complete = not incomplete(receipt, arguments)
        ref = retained_value_reference(unpack(receipt['arguments' if arguments else 'value']),
            complete=complete,
            origin={"run_id": (result.get("resume") or {}).get("run_id"),
                    "request_hash": receipt.get("request_hash"), "evidence": evidence,
                    'kind': 'resolved_arguments' if arguments else 'completed_value'})
        return {"index": index, "action": receipt.get("action"), "source_complete": complete,
                **{k: ref[k] for k in ("read_args", "input_args", "input_unavailable") if k in ref}}

    entries = [entry(i, r) for i, r in enumerate(completed)]
    failed = [entry(i, r, True) for i, r in enumerate(result.get('recordings', []))
              if 'error' in r and 'arguments' in r]
    out = {'completed_calls': entries[:6], 'completed_calls_omitted': max(0, len(entries) - 6),
           'failed_calls': failed[:6], 'failed_calls_omitted': max(0, len(failed) - 6)}
    if len(entries) > 6 or len(failed) > 6:
        index = evidence_store().evidence({'completed_calls': entries, 'failed_calls': failed})
        out['calls_read_args'] = {'id': index['id'], 'offset': 0, 'limit': DEFAULT_LIMIT}
    if failed:
        out['failed_calls_hint'] = ('실패 호출에 전달된 해석 완료 인자입니다. input_args로 회수한 $입력은 '
                                    '도구 인자 Record입니다. 실패 원인을 수정하고 필요한 호출만 새로 실행하세요. '
                                    '참조 회수는 재시도 승인이나 외부 효과의 취소를 뜻하지 않습니다.')
    return out if entries or failed else {}


#: 예산의 이 비율 이상을 쓴 실행에만 비싼 줄을 모델 사본에 싣는다.
_USAGE_DETAIL_SHARE = 0.2
#: 이보다 오래 걸린 실행에는 도구 시간이 든 줄을 싣는다 — 걸음 수는 도구 호출의 시간을 세지 않는다.
_USAGE_SLOW_MS = 10_000


def model_usage(usage):
    """모델 사본의 비용 표시 — 합계는 늘, 비싼 줄은 예산을 눈에 띄게 쓴 실행에만.

    노드별 걸음 수 목록이 업무 값보다 컸다(ep4213 실행 20회: 값 30%·usage 31%, 쓰기 한 번의 150자 결과에 1.2K자).
    전문은 저장본에 그대로 있고 read_result path ["usage"] 로 읽는다."""
    if not isinstance(usage, dict):
        return usage
    out = {k: usage[k] for k in ("steps", "rows", "elapsed_ms", "model") if k in usage}
    limits = usage.get("limits") if isinstance(usage.get("limits"), dict) else {}
    heavy = any(type(limits.get(k)) is int and limits[k] > 0 and type(usage.get(k)) is int
                and usage[k] >= limits[k] * _USAGE_DETAIL_SHARE for k in ("steps", "rows"))
    if heavy:
        lines = [row for row in usage.get("steps_by_line") or [] if isinstance(row, dict)][:3]
        sources = {row.get("source_hash") for row in lines}
        out["limits"] = limits
        out["steps_by_line"] = [{k: v for k, v in row.items() if k != "source_hash" or len(sources) > 1}
                                for row in lines]
        out["detail"] = 'read_result path ["usage"]'
    if type(usage.get("elapsed_ms")) is int and usage["elapsed_ms"] >= _USAGE_SLOW_MS:
        slow = [row for row in usage.get("tool_ms_by_line") or [] if isinstance(row, dict)][:3]
        if slow:
            sources = {row.get("source_hash") for row in slow}
            out["tool_ms_by_line"] = [{k: v for k, v in row.items() if k != "source_hash" or len(sources) > 1}
                                      for row in slow]
            out["detail"] = 'read_result path ["usage"]'
    return out


def _mirrored_rows(value):
    """생산자가 본문의 미러라고 선언한 문단 목록 필드 이름. 선언·본문·목록이 다 있을 때만."""
    display = value.get("_display")
    mirrors = display.get("mirror_fields") if isinstance(display, dict) else None
    if (isinstance(mirrors, list) and mirrors and isinstance(mirrors[0], str)
            and isinstance(value.get(mirrors[0]), str) and value[mirrors[0]]
            and isinstance(value.get("items"), list) and value["items"]):
        return "items"
    return None


def _fold_twin_fields(value, where, notes, depth=0):
    """같은 큰 값을 두 이름으로 실은 형제 필드는 표시 사본에서 한 벌만 보인다(ep4214: 자막 segments·items).

    어휘 이름을 고르지 않는다 — 값이 같은지만 본다. 저장본·wire 는 그대로라 어느 이름으로도 읽고 참조한다."""
    import hashlib
    if depth > 3:
        return value
    if isinstance(value, list):
        return [_fold_twin_fields(item, where + [i], notes, depth + 1) if i < 20 else item
                for i, item in enumerate(value)]
    if not isinstance(value, dict):
        return value
    seen, out = {}, {}
    mirrored = _mirrored_rows(value)
    for key, item in value.items():
        if key == mirrored:
            # 생산자가 "text 는 items 의 미러"라고 선언했다(_display.mirror_fields). 옛 판본 표시는 이 선언으로
            # 한쪽을 접었는데 판본 2 표시는 둘 다 실었다(ep4212: 본문 372자에 문단 목록 4.2K자).
            # 모델에는 본문을 보이고 문단 목록은 가리킨다 — 실행기 안의 값과 저장본은 그대로다.
            out[key] = {"$model_mirror_of": value["_display"]["mirror_fields"][0], "rows": len(item)}
            notes.append({"path": where + [key], "mirror_of": where + [value["_display"]["mirror_fields"][0]]})
            continue
        if isinstance(item, (list, dict)) and item:
            raw = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if len(raw) >= 400:
                mark = (type(item).__name__, len(raw), hashlib.sha256(raw.encode("utf-8")).hexdigest())
                if mark in seen:
                    out[key] = {"$model_same_as": seen[mark]}
                    notes.append({"path": where + [key], "same_as": where + [seen[mark]]})
                    continue
                seen[mark] = key
        out[key] = _fold_twin_fields(item, where + [key], notes, depth + 1)
    return out


def project_v2_result(result):
    """Typed values keep their meaning; verbose execution evidence stays on disk."""
    raw = json.dumps(result, ensure_ascii=False, default=str)
    ref = evidence_store().evidence(raw)
    policy = display_policy()
    out = {k: v for k, v in result.items() if k not in {"evidence", "recordings", "source_map"}}
    if "usage" in out:
        out["usage"] = model_usage(out["usage"])
    out["evidence_summary"] = {"events": len(result.get("evidence", [])),
                               "source_complete": result.get("source_complete")}
    failures = [e for e in result.get('evidence', []) if e.get('kind') == 'tool_failure']
    out['evidence_summary'].update(tool_failures=len(failures),
                                  source_failures=sum(e.get('incomplete') is True for e in failures))
    outcomes = {o['id']: o for e in result.get('evidence', []) if e.get('kind') == 'tool_evidence'
                for o in e.get('operation_outcomes', [])
                if isinstance(o, dict) and isinstance(o.get('id'), str)
                and o.get('status') in ('passed', 'failed')}
    if outcomes:
        out['evidence_summary']['operation_outcomes'] = list(outcomes.values())
        out['evidence_summary']['operation_failures'] = sum(o['status'] == 'failed' for o in outcomes.values())
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
            twins = []
            out["value"] = _fold_twin_fields(out["value"], ["value"], twins)
            if twins:
                out["_model_shared"] = {"fields": twins[:8], "omitted": max(0, len(twins) - 8),
                                        "note": "같은 내용이 두 필드로 실려 표시 사본에서 한 벌만 보였습니다(같은 값, 또는 본문과 그 문단 목록). 접힌 필드도 그 경로로 읽고 inputs $ref 로 참조할 수 있습니다."}
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
        if isinstance(diagnostic, dict) and isinstance(diagnostic.get("details"), dict):
            shown, preview = preview_value(diagnostic["details"], policy["issues_chars"],
                                          ref["id"], path=["diagnostic", "details"])
            if preview:
                out["diagnostic"] = {**out["diagnostic"], "details": shown}
                out["diagnostic_details_preview"] = preview
    out["result_ref"] = _read_reference(ref, result)
    if result.get("success") is False:
        out["result_ref"].update(completed_call_references(result))
    if 'value' in result:
        out['result_ref']['value_chars'] = len(json.dumps(result['value'], ensure_ascii=False, default=str))
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
                        **({"target_description": spec["authoring_hint"]} if spec.get("authoring_hint") else {}),
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
