"""Actual projected JSON payload inspection; no tokens/cost estimates or edits."""
import hashlib
import json


def indexed_payload(rows):
    """Keep the exact same JSON serialization for inspection and the model call."""
    return json.dumps([{**row, "_i": i} for i, row in enumerate(rows)], ensure_ascii=False)


def inspect_inputs(rows, *, mode, limit_chars):
    """batch = one whole-array request; each = one request per row, each with _i:0.

    Repetition scan visits dicts to depth 6 and at most 20,000 nodes, stopping at
    lists. It reports identical nonempty list payloads, not redundant reasoning.
    Size inspection is complete; only the repeated-field scan can be partial.
    """
    if mode not in ("batch", "each"):
        raise ValueError("inspect는 batch 또는 each여야 합니다.")
    if len(rows) > 10000:
        raise ValueError("inspect는 최대 10000행을 받습니다. 점검할 요청을 나누세요.")
    sizes = []
    groups = {}
    budget = 20000
    partial = False

    def visit(value, path, request_index, depth=0):
        nonlocal budget, partial
        if budget <= 0 or depth > 6:
            partial = True
            return
        budget -= 1
        if isinstance(value, list) and value:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            key = (path, digest)
            group = groups.setdefault(key, {"path": path, "occurrences": 0,
                                          "chars_each": len(encoded), "element_count": len(value),
                                          "requests": set()})
            group["occurrences"] += 1
            group["requests"].add(request_index)
        elif isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}" if path else key, request_index, depth + 1)

    requests = ([row] for row in rows) if mode == "each" else ([rows] if rows else [])
    for i, request in enumerate(requests):
        payload = indexed_payload(request)
        sizes.append({"request": i, "chars": len(payload), "bytes": len(payload.encode("utf-8"))})
        for row in request:
            visit(row, "", i)
    repeated = []
    for group in groups.values():
        if group["occurrences"] > 1:
            count = group["occurrences"]
            repeated.append({**{k: v for k, v in group.items() if k != "requests"},
                             "request_count": len(group["requests"]),
                             "repeated_chars": (count - 1) * group["chars_each"]})
    repeated.sort(key=lambda g: g["repeated_chars"], reverse=True)
    over = [s for s in sizes if s["chars"] > limit_chars]
    return {"mode": mode, "model_calls": 0, "planned_requests": len(sizes),
            "limit_chars": limit_chars, "total_payload_chars": sum(s["chars"] for s in sizes),
            "total_payload_bytes": sum(s["bytes"] for s in sizes),
            "max_payload_chars": max((s["chars"] for s in sizes), default=0),
            "oversized_count": len(over), "oversized_requests": over[:32],
            "repeated_fields": repeated[:32], "repeated_groups": len(repeated),
            "repetition_scan": "partial" if partial else "complete",
            "note": "모델 호출 없음. 문자 수는 items JSON만 측정(지시·계약·토큰 수 제외). 반복 자료가 불필요하다는 뜻은 아님."}
