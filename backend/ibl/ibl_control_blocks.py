"""ibl_control_blocks.py — 프로그램급 IBL M3·M4·M5 실행기: try/catch/finally · repeat · reduce (2026-08-22).

ibl_executors 의 형제 모듈(1500줄 규칙으로 분리). 설계 정본: docs/IBL_PROGRAM_GRADE_DESIGN.md §2.2·§2.3·§2.4.
셋 다 "문장을 감싸는" 제어 구조라 문법이지 어휘가 아니다(반-어휘-증식 시험 §1-2).
실행은 execute_ibl/execute_pipeline 재귀(깊이 +1) — 공용 보조(_nest·_get_sense_value_checked·_each_input_rows)는
ibl_executors 에서 가져온다(ibl_executors 는 이 모듈을 import 하지 않는다 — 단방향).
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from common.currency import currency_shape_note
from ibl_executors import (_nest, _get_sense_value_checked, _each_input_rows,
                           _prev_of, _vars_with_items, _stamp_var_values, _subst_var_refs)

import copy as _copy
import time as _time

_REPEAT_EVERY_MAX_S = 60        # 회차 사이 휴지 상한 — 문장은 한 호출 안에서 끝나야 한다(판정 2026-08-22)
_REPEAT_WALL_MAX_S = 300        # 반복 전체 벽시계 상한 — [self:script]{wait} 240s 와 같은 급. 더 길면 goal/schedule
_REPEAT_MAX_ITER = 1000
_REPEAT_MAX_SUBSTEPS = 500


def _subst_tokens(obj: Any, mapping: Dict[str, Any]) -> Any:
    """문자열 속 `$이름[.경로]` 를 값으로 치환 — $error(try)·$i(repeat). 이름 경계 존중($items 불침범)."""
    if isinstance(obj, str):
        def _one(m):
            from common.ibl_vars import split_ref
            name, path = split_ref(m)
            path = path[1:]
            if name not in mapping:
                return m.group(0)
            val = mapping[name]
            if path:
                from ibl_predicates import walk_path, _MISSING
                v = walk_path(val, path)
                val = "" if v is _MISSING else v
            return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
        from common.ibl_vars import refs_pattern
        return re.sub(refs_pattern(mapping), _one, obj)
    if isinstance(obj, dict):
        return {k: _subst_tokens(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst_tokens(v, mapping) for v in obj]
    return obj


def _parse_duration_s(text: Any) -> float:
    if text is None or text == "":
        return 0.0
    if isinstance(text, (int, float)):
        return float(text)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*", str(text))
    if not m:
        raise ValueError(f"시간 표기 '{text}' 를 읽지 못했습니다 — 예: \"10s\", \"2m\"")
    n, unit = float(m.group(1)), (m.group(2) or "s")
    return n / 1000 if unit == "ms" else n if unit == "s" else n * 60 if unit == "m" else n * 3600


def _parse_final(v: Any) -> Any:
    if isinstance(v, str):
        s = v.strip()
        if s[:1] in "{[":
            try:
                return json.loads(s)
            except Exception:
                return v
    return v


def _run_body(body: Any, tool_input: dict, project_path: str, agent_id: str,
              context: Optional[dict] = None) -> Tuple[Any, bool, Dict[str, Any], Dict[int, str]]:
    """블록 몸 실행 — (결과, 실패 여부, 오류 정보, step 인덱스→결과 문자열).

    list(파이프)면 execute_pipeline 봉투의 final_result 를 결과로(통화가 바로 흐르게), dict 면 execute_ibl.
    """
    from workflow_engine import execute_pipeline, _is_error_result, _auto_inject_prev
    prev = _prev_of(tool_input)
    if context is None and prev:
        context = {"_prev_result": prev}
    try:
        body = _subst_var_refs(_copy.deepcopy(body), {k: v for k, v in (tool_input.get("_var_values") or {}).items()})
    except ValueError as e:
        return None, True, {"error": f"몸의 $변수 치환 실패: {e}", "step": 1, "summary": str(e)[:200]}, {}
    if isinstance(body, list):
        steps = [_nest(s, tool_input) for s in body]
        _stamp_var_values(steps, tool_input.get("_var_values") or {})
        try:
            env = execute_pipeline(steps, project_path, context=context, agent_id=agent_id)
        except Exception as e:
            return None, True, {"error": f"{type(e).__name__}: {e}", "step": 1, "summary": str(e)[:200]}, {}
        by_idx: Dict[int, str] = {}
        for r in (env.get("results") or []) if isinstance(env, dict) else []:
            if isinstance(r, dict) and isinstance(r.get("step"), int) and "result" in r:
                by_idx[r["step"] - 1] = r["result"]
        if isinstance(env, dict) and not env.get("success", True):
            last = (env.get("results") or [{}])[-1] if env.get("results") else {}
            info = {"error": env.get("error") or "실행 실패",
                    "step": (env.get("steps_completed") or 0) + 1,
                    "node": last.get("node"), "action": last.get("action")}
            info["summary"] = str(info["error"])[:200]
            return _parse_final(env.get("final_result")), True, info, by_idx
        return _parse_final(env.get("final_result") if isinstance(env, dict) else env), False, {}, by_idx
    from ibl_engine import execute_ibl
    try:
        st = _nest(body, tool_input)
        if prev and isinstance(st, dict) and not st.get("_assign"):
            st = _auto_inject_prev(st, prev)
        res = execute_ibl(st, project_path, agent_id)
    except Exception as e:
        return None, True, {"error": f"{type(e).__name__}: {e}", "step": 1, "summary": str(e)[:200],
                            "node": body.get("_node") if isinstance(body, dict) else None,
                            "action": body.get("action") if isinstance(body, dict) else None}, {}
    if _is_error_result(res):
        obj = _parse_final(res)
        msg = (obj.get("error") or obj.get("message")) if isinstance(obj, dict) else str(obj)
        info = {"error": str(msg), "step": 1, "summary": str(msg)[:200],
                "node": body.get("_node") if isinstance(body, dict) else None,
                "action": body.get("action") if isinstance(body, dict) else None}
        return obj, True, info, {0: res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str)}
    return _parse_final(res), False, {}, {0: res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str)}


def _execute_try(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """[try]{…} [catch]{…} [finally]{…} — 실패 규약(설계 §2.4):
    catch 도 실패하면 원 오류 + catch 오류 둘 다 봉투에(덮어쓰기 금지). finally 는 결과를 바꾸지 않는다.
    catch/finally 안의 `$error`(.error/.step/.node/.action/.summary) 는 try 의 실패 정보로 치환."""
    body, catch, fin = tool_input.get("body"), tool_input.get("catch"), tool_input.get("finally")
    result, failed, err, _ = _run_body(body, tool_input, project_path, agent_id)
    out: Any
    caught_meta = None
    if not failed:
        out = result
    elif catch is not None:
        c_body = _subst_tokens(_copy.deepcopy(catch), {"error": err})
        c_res, c_failed, c_err, _ = _run_body(c_body, tool_input, project_path, agent_id)
        if c_failed:
            out = {"success": False,
                   "error": f"try·catch 모두 실패 — try: {err.get('summary')} / catch: {c_err.get('summary')}",
                   "try_error": err, "catch_error": c_err}
        else:
            out = c_res
            caught_meta = err
    else:
        out = {"success": False, "error": f"try 실패(catch 없음): {err.get('summary')}", "try_error": err}
    if fin is not None:
        f_body = _subst_tokens(_copy.deepcopy(fin), {"error": err if failed else {"error": None, "summary": ""}})
        _, f_failed, f_err, _ = _run_body(f_body, tool_input, project_path, agent_id)
        if f_failed:
            if isinstance(out, dict):
                out["finally_error"] = f_err
            else:
                print(f"[IBL_TRY] finally 실패(결과 불변): {f_err.get('summary')}")
    if caught_meta is not None and isinstance(out, dict):
        out.setdefault("_caught", caught_meta)
    return out


def _execute_repeat(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """[repeat: N | until 조건 | while 조건, max, every, collect, as]{…} — 문장 안의 결정론 반복.

    until 은 몸통 실행 *뒤*(몸통이 할당한 $변수를 읽음), while 은 *앞*. max 도달=`halted:"max"` 정직 신고
    (성공도 실패도 아님 — 통화는 냄). 벽시계·휴지 상한 초과도 신고. 몸통 step 실패=기본 stop.
    통화: 마지막 회차 items, collect:true 면 전 회차 items 이어붙임."""
    from ibl_predicates import evaluate, PredicateError
    from common.currency import derive_items
    mode = tool_input.get("mode")
    cond = tool_input.get("condition")
    max_n = min(int(tool_input.get("max") or tool_input.get("count") or 1), _REPEAT_MAX_ITER)
    collect = bool(tool_input.get("collect"))
    var = tool_input.get("var") or "i"
    body = tool_input.get("body")
    body_vars = tool_input.get("body_vars") or {}
    outer_vars = _vars_with_items(tool_input)
    notes: List[str] = []
    try:
        every_s = _parse_duration_s(tool_input.get("every"))
    except ValueError as e:
        return {"success": False, "items": [], "error": f"repeat: {e}"}
    if every_s > _REPEAT_EVERY_MAX_S:
        notes.append(f"every {every_s:.0f}s → 상한 {_REPEAT_EVERY_MAX_S}s 로 줄임(문장 안 휴지 상한; 더 길면 [goal:]/[self:schedule])")
        every_s = _REPEAT_EVERY_MAX_S
    if int(tool_input.get("max") or tool_input.get("count") or 1) > _REPEAT_MAX_ITER:
        notes.append(f"max → 상한 {_REPEAT_MAX_ITER} 로 줄임")

    def _resolve(src: str):
        return _get_sense_value_checked(src, project_path, agent_id)

    deadline = _time.time() + _REPEAT_WALL_MAX_S
    iterations = 0
    halted: Optional[str] = None
    last: Any = None
    collected: List[Any] = []
    err_info: Dict[str, Any] = {}
    substeps = 0
    cur_vars = dict(outer_vars)
    body_len = len(body) if isinstance(body, list) else 1
    for i in range(max_n):
        if mode == "while":
            try:
                ok, _ = evaluate(cond, _resolve, cur_vars)
            except PredicateError as e:
                halted, err_info = "condition_error", {"error": str(e)}
                break
            if not ok:
                break
        if i > 0 and every_s:
            if _time.time() + every_s > deadline:
                halted = "wall"
                break
            _time.sleep(every_s)
        substeps += body_len
        if substeps > _REPEAT_MAX_SUBSTEPS:
            halted = "budget"
            break
        # 회차마다 *현재* 변수 값으로 몸을 치환한다(M6 — `$n = $n + 1` 이 돌고 while 이 몸 변수를 본다):
        # 텍스트 자리($x·$x.path)는 v4/경로 추출로, 안쪽 블록·식 할당은 _var_values 스탬프로.
        it_body = _subst_tokens(_copy.deepcopy(body), {var: i})
        it_input = {**tool_input, "_var_values": cur_vars}     # 몸 치환·스탬프는 _run_body 가 현재 값으로
        result, failed, err, by_idx = _run_body(it_body, it_input, project_path, agent_id)
        iterations += 1
        if failed:
            halted, err_info, last = "error", {**err, "iteration": i + 1}, result
            break
        last = result
        if collect:
            d = derive_items(result) if isinstance(result, dict) else result
            if isinstance(d, dict) and isinstance(d.get("items"), list):
                collected.extend(d["items"])
            elif isinstance(d, list):
                collected.extend(d)
            elif d is not None:
                collected.append(d)
        cur_vars = {**outer_vars, **{n: by_idx.get(int(ix), "") for n, ix in body_vars.items()}}
        if mode == "until":
            try:
                ok, _ = evaluate(cond, _resolve, cur_vars)
            except PredicateError as e:
                halted, err_info = "condition_error", {"error": str(e)}
                break
            if ok:
                break
        if _time.time() > deadline:
            halted = "wall"
            break
    else:
        if mode in ("until", "while"):
            halted = "max"

    out: Dict[str, Any] = {"iterations": iterations, "mode": mode}
    if collect:
        out["items"] = collected
        out["count"] = len(collected)
    else:
        d = derive_items(last) if isinstance(last, dict) else last
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            out["items"] = d["items"]
            out["count"] = len(d["items"])
            for k in ("message", "value"):
                if k in d and k not in out:
                    out[k] = d[k]
        elif last is not None:
            out["last"] = last
    if halted:
        out["halted"] = halted
    if halted in ("error", "condition_error"):
        out["success"] = False
        out["error"] = (f"repeat {iterations}회차에서 중단 — {err_info.get('error')}" if halted == "error"
                        else f"repeat 종료 조건 판정 불능 — {err_info.get('error')}")
        out["repeat_error"] = err_info
    else:
        out["success"] = True
        if halted == "max":
            notes.append(f"max={max_n} 도달 — 종료 조건 미충족(성공 아님·실패 아님, 통화는 냄)")
        elif halted == "wall":
            notes.append(f"벽시계 상한 {_REPEAT_WALL_MAX_S}s 도달로 중단 — 긴 대기는 [self:script]{{wait}}·[goal:]")
        elif halted == "budget":
            notes.append(f"하위 step 예산 {_REPEAT_MAX_SUBSTEPS} 초과로 중단")
    # 몸이 재할당한 바깥 변수의 최종값 — 바깥 파이프가 step_results 에 되쓴다(루프 뒤 `$n` 이 최신값).
    _upd = {n: cur_vars[n] for n in body_vars if n in (tool_input.get("_var_values") or {}) and n in cur_vars}
    if _upd:
        out["_var_updates"] = _upd
    if notes:
        out["note"] = " / ".join(notes)
    return out


def _scalar_of(v: Any) -> Any:
    """식 안에서 쓸 값 — 액션 결과 봉투면 value→result→message, 숫자 문자열은 수로."""
    from common.safe_expr import as_num
    if isinstance(v, dict):
        if isinstance(v.get("items"), list) and "value" not in v:
            return v["items"]
        for k in ("value", "result", "message"):
            if k in v and v[k] is not None:
                v = v[k]
                break
    if isinstance(v, str):
        n = as_num(v)
        return n if n is not None else v
    return v


def _execute_assign(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """`$이름 = 식` (M6): 한 줄 식(common.safe_expr)에 $변수 값을 바인딩해 평가. 결과는 스칼라 봉투
    {value, message} — 뒤 문장의 `$이름` 은 message(v4)로, 조건·식에서는 value 로 읽힌다.
    미할당 $변수·없는 경로·허용 밖 구문은 정직 에러(거짓·0 으로 접지 않음)."""
    from common.safe_expr import compile_expr, eval_expr, FUNCS
    from ibl_predicates import walk_path, _MISSING, _load_var
    expr = str(tool_input.get("expr") or "").strip()
    name = tool_input.get("name")
    vals = _vars_with_items(tool_input)
    scope: Dict[str, Any] = {}

    def _bind(m):
        from common.ibl_vars import split_ref
        vn, path = split_ref(m)
        path = path[1:]
        if vn not in vals:
            raise ValueError(f"변수 ${vn} 이(가) 앞에서 할당되지 않았습니다.")
        v = walk_path(_load_var(vals[vn]), path or None)
        if v is _MISSING:
            raise ValueError(f"${vn}.{path} 경로가 값에 없습니다.")
        key = f"_v{len(scope)}"
        scope[key] = _scalar_of(v)
        return key
    try:
        from common.ibl_vars import REF_RE
        py = REF_RE.sub(_bind, expr)
        code, names, _cols = compile_expr(py)
        unknown = [n for n in names if n not in scope and n not in FUNCS]
        if unknown:
            raise ValueError(f"알 수 없는 이름 {unknown} — 문자열이면 따옴표로, 변수면 $ 를 붙이세요.")
        value = eval_expr(code, {}, scope)
    except Exception as e:
        return {"success": False, "error": f"${name} = {expr}: {type(e).__name__ if not isinstance(e, ValueError) else '식 오류'} {e}",
                "assigned": name}
    if isinstance(value, float) and value.is_integer() and "/" not in expr:
        value = int(value)
    return {"success": True, "value": value, "message": str(value), "assigned": name}


def _execute_table_reduce(params: dict, project_path: str, agent_id: str = None) -> Any:
    """[table:reduce]{init, step, as} — 진짜 fold, 단 **식 한 줄**만(설계 §2.3 판정).
    step 식은 compute 와 같은 화이트리스트(common.safe_expr): 열 이름·acc·i·col("열")·산술·비교·조건식.
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
    dict_rows = [r for r in rows if isinstance(r, dict)]
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
