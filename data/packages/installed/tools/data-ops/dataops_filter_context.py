"""filter의 명시 context 선택: 같은 그룹 안의 이웃 행, 일치 계수와 실패 보존."""
from common.value_semantics import values_equal


def select_context(rows, where, context, match):
    if not isinstance(context, dict):
        raise ValueError("context는 {before, after, by, limit} 객체여야 합니다")
    unknown = set(context) - {"before", "after", "by", "limit"}
    if unknown:
        raise ValueError(f"알 수 없는 context 인자: {sorted(unknown)}")
    before, after, limit = (context.get("before", 0), context.get("after", 0),
                            context.get("limit", len(rows)))
    for name, value in (("before", before), ("after", after), ("limit", limit)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"context.{name}은 0 이상의 정수여야 합니다")
    by = context.get("by", [])
    by = [by] if isinstance(by, str) else by
    if not isinstance(by, list) or any(not isinstance(k, str) or not k for k in by):
        raise ValueError("context.by는 그룹 열 이름 또는 열 이름 목록이어야 합니다")

    failures = [i for i, row in enumerate(rows) if row.get("_error")]
    # 모든 행이 실패라 text가 없어도 실패 행을 보존한다. 결측을 매치로 세지 않는다.
    failed = set(failures)
    hits = [i for i, row in enumerate(rows) if i not in failed and match(row, where)]
    selected = hits[:limit]
    keep = set(failures)
    for i in selected:
        keep.add(i)
        for direction, size in ((-1, before), (1, after)):
            for distance in range(1, size + 1):
                j = i + direction * distance
                if j < 0 or j >= len(rows) or rows[j].get("_error"):
                    break
                # 결측 그룹 키는 같은 문서라는 증거가 없으므로 경계를 넘지 않는다.
                if any(k not in rows[i] or k not in rows[j] or rows[i][k] is None
                       or rows[j][k] is None or not values_equal(rows[i][k], rows[j][k]) for k in by):
                    break
                keep.add(j)
    indices = sorted(keep)
    return [rows[i] for i in indices], {
        "total_matches": len(hits), "selected_matches": len(selected),
        "omitted_matches": len(hits) - len(selected),
        "match_indices": [i + 1 for i in hits],
        "selected_indices": [i + 1 for i in selected],
        "input_indices": [i + 1 for i in indices],
        "failure_count": len(failures),
    }


def run(prev, params, h):
    where = params.get("where") or params.get("condition")
    fields = h["_where_fields"](where)
    rows, env = h["_get_items_for_fields"](prev, fields)
    table = None
    if rows is None:
        table, env = h["_get_table"](prev)
        if table is None:
            return h["_no_currency_error"]("filter", prev)
        rows = h["_row_dicts"](table)
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("context 입력은 객체 행이어야 합니다")
    valid = [row for row in rows if not row.get("_error")]
    missing = [field for field in fields if valid and not any(field in row for row in valid)]
    if missing:
        return h["_field_missing_error"]("filter", missing, valid)
    kept, info = select_context(rows, where, params["context"], h["_match"])
    if table is not None:
        cols = table.get("columns") or []
        out = h["_emit_table"](env, {"columns": cols,
                                   "rows": [[r.get(str(k)) for k in cols] for r in kept]}, population=True)
    else:
        out = h["_emit_items"](env, kept, population=True)
    out["match_info"] = info
    if info["omitted_matches"]:
        out["truncations"] = list(out.get("truncations") or []) + [{
            "scope": "selection", "source": "filter.context", "unit": "matches",
            "retained": info["selected_matches"], "total": info["total_matches"],
        }]
    return out
