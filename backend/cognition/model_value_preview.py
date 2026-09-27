"""Budgeted display copies. Omission paths always address the untouched evidence."""
import json


def _size(value):
    return len(json.dumps(value, ensure_ascii=False))


def _shares(sizes, budget):
    """Small values remain whole; only larger siblings share the remaining space."""
    result = [0] * len(sizes)
    pending = set(range(len(sizes)))
    while pending:
        quota = max(0, budget // len(pending))
        small = [i for i in pending if sizes[i] <= quota]
        if not small:
            for i in sorted(pending):
                result[i] = quota
            break
        for i in small:
            result[i] = sizes[i]
            budget -= sizes[i]
            pending.remove(i)
    return result


def preview_value(value, budget, ref_id, *, path=None):
    """Keep order and shape where possible, with bounded, actionable omissions.

    This is not a source completeness judgement or a replacement for typed values.
    No action/column names or data-dependent ranking determines which rows survive.
    """
    from result_read_contract import DEFAULT_LIMIT
    root = ["value"] if path is None else path
    notices, changes = [], 0

    def note(where, kind, shown, total):
        nonlocal changes
        changes += 1
        if len(notices) < 16:
            notices.append({"path": where, "kind": kind, "shown": shown, "total": total,
                            "read_args": {"id": ref_id, "path": where,
                                          "offset": 0, "limit": DEFAULT_LIMIT}})

    def visit(item, cap, where, depth):
        size = _size(item)
        if size <= cap:
            return item
        if isinstance(item, str):
            # JSON escaping is part of the budget; a slice never exceeds it.
            lo, hi = 0, len(item)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if _size(item[:mid] + "…") <= cap:
                    lo = mid
                else:
                    hi = mid - 1
            note(where, "text", lo, len(item))
            return item[:lo] + "…"
        if not isinstance(item, (list, dict)):
            return item
        if depth >= 12 or cap < 8:
            note(where, "depth" if depth >= 12 else "budget", 0, len(item))
            return [] if isinstance(item, list) else {}
        if isinstance(item, list):
            # A bounded prefix prevents enormous arrays of empty row placeholders.
            count = min(len(item), max(1, cap // 96))
            if count < len(item):
                note(where, "list", count, len(item))
            children = item[:count]
            shares = _shares([_size(v) for v in children], max(0, cap - 2 * count - 2))
            return [visit(v, share, where + [i], depth + 1)
                    for i, (v, share) in enumerate(zip(children, shares))]
        keys, overhead = [], 2
        for key in item:
            cost = _size(key) + 4
            if overhead + cost + 8 * (len(keys) + 1) > cap:
                break
            overhead += cost
            keys.append(key)
        if len(keys) < len(item):
            note(where, "record", len(keys), len(item))
        shares = _shares([_size(item[k]) for k in keys], max(0, cap - overhead))
        return {k: visit(item[k], share, where + [k], depth + 1)
                for k, share in zip(keys, shares)}

    shown = visit(value, budget, root, 0)
    meta = {"scope": "display", "value_chars": _size(value), "shown_chars": _size(shown),
            "changes": notices, "changes_total": changes,
            "changes_omitted": changes - len(notices),
            "read_args": {"id": ref_id, "path": root, "offset": 0, "limit": DEFAULT_LIMIT},
            "note": "표시용 사본입니다. 생략된 후보·필드는 미검토입니다. 조건 적용은 원문 inputs 참조로, 추가 읽기는 각 read_args로 수행하세요."}
    return shown, meta if changes else None
