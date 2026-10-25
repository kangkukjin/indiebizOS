"""Bound review context and repair citation receipts without rerunning the task."""
import difflib
import json


def ibl_error_render_repair_key(name, payload):
    """Recognize error-object formatting repairs in the final projection only.

    The acquisition program, input values, branch conditions and tool arguments
    remain exact. A successful rendering does not resolve a different source
    failure. Never normalize formatting used to choose or invoke an operation.
    """
    if not str(name).endswith("execute_ibl") or not payload.get("code"):
        return None
    from ibl_v2_parser import parse
    from ibl_v2_ir import Node, pack, Fault
    from model_result_view import resolve_input_refs
    from supervision_store import digest

    def exact(value):
        if isinstance(value, Node):
            return [value.kind, exact(value.data)]
        if isinstance(value, dict):
            return {k: exact(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [exact(v) for v in value]
        return pack(value)

    def builtin(value, names):
        return (isinstance(value, Node) and value.kind == "pure_call"
                and value.data["fn"].kind == "builtin"
                and value.data["fn"].data["name"] in names
                and len(value.data["args"]) == 1)

    found = False

    def projection(value):
        nonlocal found
        if not isinstance(value, Node):
            return exact(value)
        base = value
        if value.kind == "slice":
            lower, upper = value.data["lower"], value.data["upper"]
            if (lower is not None and lower.kind == "literal" and lower.data["value"] == 0
                    and upper is not None and upper.kind == "literal"
                    and type(upper.data["value"]) is int and upper.data["value"] > 0
                    and value.data["stride"] is None):
                base = value.data["base"]
        if builtin(base, {"text", "json"}) and builtin(base.data["args"][0], {"error_of"}):
            found = True
            return ["error_render", exact(base.data["args"][0])]
        if value.kind == "record":
            return ["record", {k: projection(v) for k, v in value.data["fields"].items()}]
        if value.kind == "conditional":
            return ["conditional", exact(value.data["condition"]),
                    projection(value.data["yes"]), projection(value.data["no"])]
        if value.kind == "pipe" and value.data["op"] == ">>":
            call = value.data["right"]
            if (call.kind == "call" and call.data["node"] == "table"
                    and call.data["action"] == "each" and call.data.get("body") is not None
                    and call.data["params"].data.get("fields") == {}):
                statements = call.data["body"].data["statements"]
                if len(statements) == 1 and statements[0].kind == "return":
                    return ["project_each", exact(value.data["left"]),
                            projection(statements[0].data["value"])]
        return exact(value)

    try:
        statements = parse(payload["code"]).data["statements"]
        if not statements or statements[-1].kind != "return":
            return None
        inputs, _ = resolve_input_refs(payload.get("inputs", {}))
        result = projection(statements[-1].data["value"])
        if found:
            return digest(json.dumps(["error_render", exact(statements[:-1]), result, pack(inputs)],
                                     sort_keys=True, ensure_ascii=False))
    except (Fault, ValueError, TypeError, KeyError, OSError, RecursionError):
        pass
    return None


def ibl_shape_repair_key(name, payload):
    """Match straight-line projection repairs, retaining calls, inputs and order.

    Binding a call before projecting its result is equivalent to projecting it
    in the binding. Evidence IDs may differ while their immutable values agree.
    Control flow, changed source arguments and unresolved inputs never match.
    """
    if not str(name).endswith("execute_ibl") or not payload.get("code"):
        return None
    from ibl_v2_parser import parse
    from ibl_v2_ir import Node, pack, Fault
    from model_result_view import resolve_input_refs
    from supervision_store import digest

    bindings, calls = {}, []

    def canonical(value, projections=True):
        if isinstance(value, Node):
            if value.kind == "ref" and value.data["name"] in bindings:
                return canonical(bindings[value.data["name"]], projections)
            # Only the row-envelope projection is a shape repair. Different
            # business fields (left/right, gross/net, etc.) remain distinct.
            if value.kind == "field" and projections and value.data["key"] == "items":
                return canonical(value.data["base"], projections)
            return [value.kind, {k: canonical(v, projections and value.kind != "call")
                                 for k, v in value.data.items()}]
        if isinstance(value, dict):
            return {k: canonical(v, projections) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [canonical(v, projections) for v in value]
        return pack(value)

    def visit(value):
        if isinstance(value, Node):
            if value.kind not in {"field", "ref", "literal", "record", "list", "pipe", "parallel", "call"}:
                raise ValueError("not a straight-line projection repair")
            if value.kind == "call":
                if value.data.get("body") is not None:
                    raise ValueError("control body")
                # Arguments are exact, including callbacks and their projections.
                calls.append(canonical(value))
                return
            if value.kind == "pipe":
                if value.data.get("op") != ">>":
                    raise ValueError("conditional execution")
                visit(value.data["left"])
                visit(value.data["right"])
                calls.append(["pipe_input", canonical(value.data["left"]), canonical(value.data["right"])])
                return
            if value.kind == "parallel":
                # Combining already acquired values is safe; do not flatten
                # concurrent calls into a misleading sequential fingerprint.
                def has_call(v):
                    if isinstance(v, Node):
                        return v.kind == "call" or has_call(v.data)
                    if isinstance(v, dict):
                        return any(has_call(x) for x in v.values())
                    if isinstance(v, (list, tuple)):
                        return any(has_call(x) for x in v)
                    return False
                if has_call(value):
                    raise ValueError("parallel calls")
            visit(value.data)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    try:
        program = parse(payload["code"])
        inputs, _ = resolve_input_refs(payload.get("inputs", {}))
        result = None
        expressions = []
        for statement in program.data["statements"]:
            if statement.kind == "bind":
                key = statement.data["name"]
                if key in bindings or key in inputs:
                    return None
                value = statement.data["value"]
                visit(value)
                bindings[key] = value
                result = canonical(value)
            else:
                value = statement.data["value"] if statement.kind == "return" else statement
                visit(value)
                result = canonical(value)
                expressions.append(result)
                if statement.kind == "return":
                    break
        # A bound final value and an explicit return have the same completion.
        if not expressions or expressions[-1] != result:
            expressions.append(result)
        key = [calls, expressions, pack(inputs)]
        return digest(json.dumps(key, sort_keys=True, ensure_ascii=False))
    except (Fault, ValueError, TypeError, KeyError, OSError, RecursionError):
        return None


def missing_read_observation(name, payload, result):
    """순수 파일 조회의 ENOENT만 탐색 결과로 취급한다. 쓰기·권한·네트워크 실패는 제외."""
    if (not str(name or "").endswith("execute_ibl") or not isinstance(payload, dict)
            or not isinstance(payload.get("code"), str)):
        return False
    from ibl_v2_parser import parse
    from common.expression_ir import Node

    def reads_only(node):
        if not isinstance(node, Node):
            return False
        if node.kind == 'parallel':
            return reads_only(node.data['left']) and reads_only(node.data['right'])
        if node.kind in ('return', 'expr'):
            return reads_only(node.data['value'])
        if node.kind != 'call' or (node.data['node'], node.data['action']) != ('self', 'read'):
            return False
        from ibl_v2_learning import walk_nodes
        return not any(n.kind in ('call', 'invoke') for n in walk_nodes(node.data['params']))

    try:
        program = parse(payload['code']).data['statements']
        if not program or not all(reads_only(n) for n in program):
            return False
    except Exception:
        return False

    def errors(value):
        if isinstance(value, str):
            try:
                return errors(json.loads(value))
            except (ValueError, TypeError):
                from common.currency import is_plain_failure
                return [value] if is_plain_failure(value) else []
        if isinstance(value, list):
            return [e for item in value for e in errors(item)]
        if isinstance(value, dict):
            found = [str(value["error"])] if value.get("error") else []
            for key in ("results", "result", "final_result", "branches"):
                if key in value:
                    found.extend(errors(value[key]))
            return found
        return []

    failures = errors(result)
    return bool(failures) and all("[Errno 2]" in e and "No such file or directory" in e
                                  and "[Errno 13]" not in e for e in failures)


def response_review_page(controller, limit=12000):
    """같은 기준·원천의 재검수는 실제 변경 바이트만 전송한다. 의미 승인을 재사용하지 않는다."""
    from supervision_store import digest
    store = controller.store
    basis = digest(json.dumps({"goal": controller.message, "framing": controller.framing,
                               "evidence": store.tool_index(), "artifacts": controller.content_artifacts},
                              ensure_ascii=False, sort_keys=True, default=str))
    if getattr(controller, "_response_review_basis", None) != basis:
        store.coverage.clear()
        controller._response_review_basis = basis
        return {"mode": "full_read_required", **store.read_response(0, limit, mark=True)}
    unread = [b for b in store.blocks if (b["id"], b["hash"]) not in store.coverage]
    result = {"mode": "changed_blocks", "version": store.version, "hash": store.manifest()["hash"],
              "blocks": [], "previously_read_unchanged": len(store.blocks) - len(unread),
              "dependent_claims": "변경된 수치·주장의 합계·시간표·요약·한계를 함께 대조한다. 필요한 기존 블록은 response id로 읽는다.",
              "remaining_ids": []}
    used = 0
    for b in unread:
        size = len(json.dumps(b, ensure_ascii=False))
        if result["blocks"] and used + size > limit:
            result["remaining_ids"].append(b["id"])
            continue
        result["blocks"].append(dict(b))
        store.coverage.add((b["id"], b["hash"]))
        used += size
    return result


def content_changes(controller):
    """Transfer only previously read identical spans; show changed bytes explicitly."""
    store = controller.store
    previous = getattr(controller, "_reviewed_artifacts", {})
    current = {a["path"]: a for a in controller.content_artifacts}
    controller._reviewed_artifacts = current
    changes, budget = [], 12000
    for path, artifact in current.items():
        old = previous.get(path)
        if not old or not store.evidence_fully_read(old["evidence_id"]):
            changes.append({"path": path, "mode": "full_read_required"})
            continue
        key = artifact["evidence_id"]
        if old["hash"] == artifact["hash"]:
            changes.append({"path": path, "mode": "unchanged", "hash": artifact["hash"]})
            continue
        before = store.read_evidence(old["evidence_id"], 0, None)["text"].splitlines(keepends=True)
        after = store.read_evidence(key, 0, None)["text"].splitlines(keepends=True)
        offsets = [0]
        for line in after:
            offsets.append(offsets[-1] + len(line))
        pages = []
        for tag, i, j, a, b in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
            if tag == "equal":
                # The old body was fully read. Identical bytes retain that provenance.
                store.evidence_coverage.setdefault(key, []).append((offsets[a], offsets[b]))
                continue
            start, end = offsets[max(0, a - 2)], offsets[min(len(after), b + 2)]
            size = min(end - start, budget)
            page = store.read_evidence(key, start, size, mark=True) if size else None
            pages.append({"change": tag, "old_text": "".join(before[i:j])[:1000],
                          "page": page, "remaining_offset": start + size if start + size < end else None})
            budget -= size
        changes.append({"path": path, "mode": "changed_ranges", "hash": artifact["hash"],
                        "previous_hash": old["hash"], "pages": pages})
    return changes


def final_state(controller):
    """Evidence stays addressable; do not replay the whole execution log at each verdict."""
    state = controller.state()
    state.pop("events", None)
    state.pop("tools", None)
    framing = state.get("framing") or {}
    state["framing"] = {k: framing[k] for k in ("task_framing", "assumptions") if k in framing}
    previous = state.get("previous_review")
    if previous:
        ref = controller.store.evidence(previous)
        state["previous_review"] = {k: previous[k] for k in ("status", "reason", "instruction") if k in previous}
        state["previous_review"]["evidence"] = {k: ref[k] for k in ("id", "chars")}
    state["evidence_index"] = controller.store.tool_index()
    state["content_changes"] = content_changes(controller)
    state["review_policy"] = ("첫 검수는 사용자 목표·핵심 주장·산출물을 대조하고 결함을 한 번에 실행자에게 넘긴다. "
                              "재검수는 아래 changed_ranges와 의존 주장부터 확인한다. 동일 바이트의 읽기 근거는 유지되며 "
                              "변경된 바이트·새 출처·결론의 타당성은 새로 판단한다. 새 조사는 REWORK로 넘긴다.")
    return state


def recover_citations(controller, decision, issue):
    """One source-only confirmation for a receipt gap, never an automatic approval."""
    if getattr(issue, "kind", None) != "citation" or getattr(controller, "_citation_repair_used", False):
        return decision
    store, pages, budget = controller.store, [], 8000
    for check in decision.get("content_checks", []):
        if not isinstance(check, dict):
            return decision
        for facet in ("meaning", "sources", "counts"):
            value = check.get(facet, {})
            if not isinstance(value, dict) or not isinstance(value.get("evidence", []), list):
                return decision
            for ref in value.get("evidence", []):
                if not isinstance(ref, dict):
                    return decision
                key, quote = ref.get("id"), ref.get("quote")
                if store.evidence_quote_read(key, quote):
                    continue
                try:
                    text = store.read_evidence(key, 0, None)["text"]
                except (ValueError, OSError, TypeError):
                    return decision
                if not isinstance(quote, str) or not quote.strip():
                    return decision
                escaped = json.dumps(quote, ensure_ascii=False)[1:-1]
                found = next(((text.find(q), len(q)) for q in (quote, escaped) if q in text), None)
                if found is None:
                    return decision  # A fabricated quote requires an executor correction.
                pos, length = found
                start, end = max(0, pos - 200), min(len(text), pos + length + 200)
                if end - start > budget:
                    return decision
                budget -= end - start
                pages.append({"path": check.get("path"), "facet": facet, "claim": check[facet].get("reason"),
                              "meaning": check.get("meaning", {}).get("reason"),
                              "citation": ref, "start": start, "end": end})
    if not pages:
        return decision
    controller._citation_repair_used = True
    # Mark only the exact ranges included in the confirmation input.
    for row in pages:
        start, end = row.pop("start"), row.pop("end")
        row["page"] = store.read_evidence(row["citation"]["id"], start, end - start, mark=True)
    prompt = json.dumps({"goal": controller.message, "reason": str(issue),
                         "previous_approval": decision.get("reason", ""), "source_pages": pages}, ensure_ascii=False)
    from supervisor_runtime import invoke, parse_decision
    controller._citation_review = True
    try:
        try:
            raw = invoke(controller, prompt, phase="receipt")
        except Exception as exc:
            controller.log("citation.recheck_failed", role="harness", error=str(exc))
            raw = ""
        if controller.call_stop or controller.cancelled():
            raw = ""
    finally:
        controller._citation_review = False
        controller.phase = "final"
    confirmation = parse_decision(raw)
    controller.log("citation.rechecked", role="consciousness", status=confirmation["status"],
                   reason=confirmation.get("reason"), evidence_ids=[r["citation"]["id"] for r in pages])
    if confirmation["status"] == "APPROVED":
        return decision
    return {"status": "REWORK", "reason": confirmation.get("reason", "출처 확인 미완료"),
            "instruction": confirmation.get("instruction") or str(issue), "repair_scope": "local"}
