"""Bound review context and repair citation receipts without rerunning the task."""
import difflib
import json


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
