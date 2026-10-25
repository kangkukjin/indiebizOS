"""Pure fold over tool rows; no IBL program interpreter."""
import json
from typing import Any, Tuple, Optional
from common.currency import currency_shape_note


def _each_input_rows(params: dict) -> Tuple[Optional[list], Any]:
    """입력 통화(items)를 꺼낸다. 반환: (행 목록 또는 None, 파싱된 봉투).

    규약은 data-ops 변환자와 **같다**(2026-08-15 대칭 수리): 파이프 입력(`_prev_result`)이
    먼저이고, 그게 없을 때만 params 에서 통화를 직접 받는다 — 단독 호출·자가점검·
    리터럴 씨앗 지원. 옛 each 는 `_prev_result` 만 읽어, 다른 13 변환자가 전부 받는
    `items: [...]` 리터럴을 혼자 거부했다("받은 봉투: str"). 하필 문형을 곱셈으로 바꾸는
    유일한 고차 변환자가 항상 앞에 생산자를 요구하던 셈이다.
    """
    prev = params.get("_prev_result")
    # 스필 참조 봉투면 본문으로 (M5 자동 스필 — 소비자는 투명하게 읽는다)
    from common.spill import resolve_ref_str
    prev, _ref_err = resolve_ref_str(prev)
    if _ref_err:
        return None, {"error": _ref_err}
    obj = prev
    if isinstance(prev, str):
        s = prev.strip()
        obj = None
        if s.startswith("{") or s.startswith("["):
            try:
                obj = json.loads(s)
            except Exception:
                obj = prev          # JSON 아닌 문자열 — 아래에서 통화 없음으로 진단된다
        elif s:
            obj = prev
    if obj is None:                  # 파이프 입력 없음 → params 에서 통화 수용
        if params.get("items") is not None:
            # ★B19-2 (2026-08-22 상상훈련 19회차): `items: "$r.items"` 는 변수 치환이
            # 통화를 **JSON 문자열**로 넣는다. 옛 코드는 그 문자열을 그대로 items 자리에
            # 담아 "items 를 찾지 못했습니다 — 받은 봉투: ['items']" 라는 자기모순 거절이
            # 났다(같은 문장이 take 에선 통과 — 읽는 쪽이 갈렸다). 정본 =
            # common.currency.coerce_items_payload — data-ops·ai-ops 도 같은 눈을 쓴다.
            from common.currency import coerce_items_payload
            _rows = coerce_items_payload(params["items"])
            obj = {"items": _rows if _rows is not None else params["items"]}
        elif params.get("table") is not None:
            obj = {"table": params["table"]}

    if isinstance(obj, dict):
        from common.currency import derive_items
        obj = derive_items(obj)
        rows = obj.get("items")
        return (rows if isinstance(rows, list) else None), obj
    if isinstance(obj, list):
        return obj, obj
    return None, obj


def _execute_table_reduce(params: dict, project_path: str, agent_id: str = None) -> Any:
    """[table:reduce]{init, step, as} — 진짜 fold, 단 **식 한 줄**만(설계 §2.3 판정).
    step 식은 compute 와 같은 화이트리스트(common.safe_expr): 열 이름·acc·i·col("열")·산술·비교·조건식.
    객체 아닌 행은 누적 전에 위치와 함께 거절한다. 빈 목록은 init을 보존한다.
    그 이상(dict 상태·분기)은 명시 거절 + [self:script] 안내. 결과 스칼라는 value/message 와 items 1행으로."""
    from common.safe_expr import compile_expr, eval_expr
    expr = params.get("step") or params.get("expr")
    if not expr or not isinstance(expr, str):
        return {"success": False, "items": [], "error": 'reduce: step(한 줄 식)이 필요합니다. 예: [table:reduce]{init: 0, step: "acc + 보증금", as: "총보증금"}'}
    try:
        code, names, cols = compile_expr(expr)
    except (SyntaxError, ValueError) as e:
        return {"success": False, "items": [], "error": f"reduce: step 식 오류 — {e}"}
    rows, env = _each_input_rows(params)
    if rows is None:
        shape = currency_shape_note(env)
        return {"success": False, "items": [], "error": f"reduce: 입력에서 items 통화를 찾지 못했습니다. 받은 봉투: {shape} — 파이프(>>) 뒤에 놓거나, 단독으로 쓰려면 items 에 목록(또는 $변수)을 주세요."}
    invalid = [i for i, row in enumerate(rows) if not isinstance(row, dict)]
    if invalid:
        return {"success": False, "items": [],
                "error": f"reduce: 입력은 객체 행이어야 합니다(0 기반 행 위치: {invalid}). 행을 제외한 합계를 만들지 않았습니다.",
                "invalid_row_indices": invalid, "rows_done": 0}
    dict_rows = rows
    need = [n for n in names if n not in ("acc", "i")] + cols
    missing = [k for k in need if dict_rows and not any(k in r for r in dict_rows)]
    if missing:
        avail = sorted({k for r in dict_rows[:5] for k in r.keys()})[:16]
        return {"success": False, "items": [], "error": f"reduce: 식이 참조한 열 {missing} 이 행에 없습니다 — 실제 열: {avail}"}
    acc = params.get("init", 0)
    as_name = str(params.get("as") or "value")
    for i, row in enumerate(dict_rows):
        try:
            acc = eval_expr(code, row, {"acc": acc, "i": i})
        except Exception as e:
            return {"success": False, "items": [], "error": f"reduce: {i + 1}번째 행에서 식 계산 실패 — {type(e).__name__}: {e}",
                    "partial": acc, "rows_done": i}
    return {"success": True, "value": acc, "message": str(acc), "items": [{as_name: acc}], "count": 1,
            "reduced_rows": len(dict_rows)}
