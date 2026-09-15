"""Bound review context and repair citation receipts without rerunning the task."""
import difflib
import json


def missing_read_observation(name, payload, result):
    """순수 파일 조회의 ENOENT만 탐색 결과로 취급한다. 쓰기·권한·네트워크 실패는 제외."""
    if (not str(name or "").endswith("execute_ibl") or not isinstance(payload, dict)
            or not isinstance(payload.get("code"), str)):
        return False
    from ibl_parser import parse

    def reads_only(step):
        if not isinstance(step, dict):
            return False
        if step.get("_parallel"):
            return bool(step.get("branches")) and all(reads_only(s) for s in step["branches"])
        return (step.get("_node") == "self" and step.get("action") == "read"
                and not any(k.startswith("_") and k != "_node" for k in step))

    try:
        program = parse(payload["code"])
        if not program or not all(reads_only(s) for s in program):
            return False
    except Exception:
        return False

    def errors(value):
        if isinstance(value, str):
            try:
                return errors(json.loads(value))
            except (ValueError, TypeError):
                return [value] if value.startswith("Error:") else []
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
