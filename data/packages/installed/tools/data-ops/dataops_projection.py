"""행 투영: 선택·개명·계산·객체/목록 구성을 한 번에. AI·파일 경유 없음."""
from common.safe_expr import compile_projection, eval_projection, projection_fields


def project(prev, spec, h):
    try:
        plan = compile_projection(spec)
    except (SyntaxError, ValueError, TypeError) as exc:
        return {'success': False, 'error': f'select: 투영 식 오류 — {exc}'}
    fields = sorted(projection_fields(plan))
    table, env = h['_get_table'](prev) if h['_explicit_table'](prev) else (None, None)
    if table is not None:
        rows = h['_row_dicts'](table)
    else:
        rows, env = h['_get_items_for_fields'](prev, fields)
    if rows is None:
        return h['_no_currency_error']('select', prev)
    if any(not isinstance(row, dict) for row in rows):
        return {'success': False, 'error': 'select: 투영 입력은 객체 행이어야 합니다.'}
    out = []
    for i, row in enumerate(rows):
        missing = [f for f in fields if f not in row]
        if missing:
            return {'success': False, 'error': f'select: {i + 1}행에 필드 {missing}이 없습니다.'}
        try:
            out.append(eval_projection(plan, row))
        except Exception as exc:
            return {'success': False, 'error': f'select: {i + 1}행 투영 실패 — {exc}'}
    if table is not None:
        cols = list(spec)
        return h['_emit_table'](env, {'columns': cols, 'rows': [[r[c] for c in cols] for r in out]})
    return h['_emit_items'](env, out)
