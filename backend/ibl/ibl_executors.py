"""
ibl_executors.py - IBL 엔진 실행 모듈

노드 실행(info/store/exec/output), 출력 핸들러(gui/file/open/clipboard/download),
Goal 프로세스 관리, 제어 흐름(condition/case) 함수를 담당합니다.

ibl_engine.py에서 분리된 모듈로, 순환 의존을 피하기 위해
execute_ibl 등은 함수 내부에서 지연 임포트합니다.
"""

import os
import re
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 통화 진단의 정본 — 2026-08-22 에 여기서 common/currency 로 이사했다(소비자가 셋이 되며
# ibl 층 안쪽에 두면 패키지 핸들러가 ibl 내부를 찔러야 했다). 옛 import 경로 보존용 재수출.
from common.currency import currency_shape_note  # noqa: F401


_nodes_cache: Optional[Dict] = None


def _load_nodes() -> Dict:
    """nodes: 섹션 로드 (캐싱)"""
    global _nodes_cache
    if _nodes_cache is not None:
        return _nodes_cache
    from ibl_registry import load_nodes_installed
    data = load_nodes_installed()
    _nodes_cache = data.get("nodes", {})
    return _nodes_cache


# (2026-08-05 감사 D11) 옛 노드타입 디스패치(_execute_node/_execute_info_node/
# _execute_store_node/_execute_exec_node)는 삭제 — 트리거 노드명 info/store/exec/output 이
# 레지스트리에 존재하지 않아 도달 불가였고, 도달해도 config type 부재로 오류만 반환했다.

# ============================================================
# Phase 13: 출력 노드 함수들
# ============================================================

# ── 이사(2026-08-23, 1500줄 규칙): 출력·목표·each·소스 평가는 형제 모듈에 산다.
#    공개 이름은 여기서 재수출 — 호출자·시험(`ex._x` monkeypatch 포함)은 무변경.
from ibl_exec_output import (  # noqa: F401
    _output_gui, extract_path_from_prev, _output_open, _output_clipboard, _output_download,
)
from ibl_exec_goal import (  # noqa: F401
    _goal_list, _goal_status, _goal_kill, _goal_delete,
    _log_attempt, _get_attempts, _summarize_attempts, _execute_goal_block,
)
from ibl_exec_each import (  # noqa: F401
    _EACH_DEFAULT_LIMIT, _EACH_SCALAR_FIELD, _EACH_MAX_SUBSTEPS,
    _each_escape, _each_substitute, _each_foreign_vars, _stamp_depth,
    _each_input_rows, _execute_table_each,
)
from ibl_exec_sense import (  # noqa: F401
    _FIELD_MISSING, _get_sense_value, _get_sense_value_checked, _field_path_hints,
    _parse_source_ref, _extract_dotted_field, _extract_dotted_field_checked,
    _find_top_level_comparison_op,
)


def _nest(step: Any, tool_input: dict) -> Any:
    """중첩 실행할 step 에 깊이를 +1 해서 실어 보낸다 (2026-08-15 고차 문장).

    문장을 값으로 받는 자리(if/case/[table:each])가 공통으로 쓰는 한 줄.
    step 이 dict 가 아니면(문자열 IBL 코드 등) 그대로 돌려준다 — 호출자가 파싱한다.
    """
    if not isinstance(step, dict):
        return step
    out = {**step, "_depth": (tool_input.get("_depth") or 0) + 1}
    # 블록 속 블록이 바깥 문장의 $변수를 계속 읽게 — 변수 값 봉투 계승 (2026-08-22 M2)
    if tool_input.get("_var_values") and (out.get("_condition") or out.get("_case")
                                          or out.get("_try") or out.get("_repeat") or out.get("_assign")):
        out["_var_values"] = {**tool_input["_var_values"], **(out.get("_var_values") or {})}
    return out


def _meta_safe(v: Any) -> Any:
    """관측 메타 값의 JSON-안전화 — 원시형은 그대로, 그 외는 짧은 문자열로."""
    return v if isinstance(v, (str, int, float, bool)) or v is None else str(v)[:200]


def _attach_branch_meta(result: Any, matched: str, matched_value: Any,
                        tool_input: dict = None) -> Any:
    """조건 블록([if:]/[case:]) 분기 결과에 관측 메타를 병기한다 (★P2, 2026-08-20).

    matched=탄 분기의 라벨(조건식·패턴·"else"·"default"), matched_value=좌변 실측값.
    종전엔 분기 결과만 반환해 어느 분기를 탔는지·좌변이 얼마였는지 원리적으로 진단
    불가였다(트리거 안 오분기가 특히). 분기 결과가 곧 파이프 통화이므로 dict 일 때만
    setdefault 로 병기(기존 키 불침범) — 문자열·리스트 결과를 감싸면 하류 통화 계약이
    깨지니 그 경우는 로그로만 남긴다.
    """
    mv = _meta_safe(matched_value)
    # ★F19-1 (2026-08-22 상상훈련 19회차): 분기 몸이 스칼라를 내면(예 [self:time]) 옛 코드는
    # 메타를 로그로만 흘려, 같은 블록이 결과 모양에 따라 진단 가능/불가로 갈렸다
    # ("case 는 안 내고 if 는 낸다"로 보이던 것의 실체 = dict/비-dict 비대칭).
    # 통화(payload)는 불침범한 채, 관측 메타는 **봉투 쪽 side-channel**(step dict)로 낸다 —
    # 파이프는 results[] step 기록에, 단독 실행은 상위에서 결과를 감싸 실어 보낸다.
    if isinstance(tool_input, dict):
        tool_input["_branch_meta"] = {"matched": matched, "matched_value": mv}
    if isinstance(result, dict):
        result.setdefault("matched", matched)
        result.setdefault("matched_value", mv)
    else:
        print(f"[IBL_COND] matched={matched} value={mv} (비-dict 분기 결과 — 봉투로만 신고)")
    return result


def _prev_of(tool_input: dict) -> Any:
    """블록이 파이프 속에 있을 때 받은 직전 통화(_prev_result) — 없으면 None."""
    p = tool_input.get("params")
    return p.get("_prev_result") if isinstance(p, dict) else None


def _vars_with_items(tool_input: dict) -> Dict[str, Any]:
    """블록의 변수 봉투 + 파이프 입력을 `$items` 로 (M6 블록-인-파이프): `[A] >> [if: count($items) > 0]{…}`.
    $items 는 집합 참조 예약어(G1-③)라 변수 이름과 충돌하지 않는다. 입력에 items 통화가 있으면 그 목록을,
    아니면 입력 원형을 싣는다."""
    vals = dict(tool_input.get("_var_values") or {})
    prev = _prev_of(tool_input)
    if prev is not None and "items" not in vals:
        obj = prev
        if isinstance(prev, str):
            s = prev.strip()
            if s[:1] in "{[":
                try:
                    obj = json.loads(s)
                except Exception:
                    obj = prev
        if isinstance(obj, dict) and isinstance(obj.get("items"), list):
            vals["items"] = json.dumps(obj["items"], ensure_ascii=False)
        else:
            vals["items"] = prev if isinstance(prev, str) else json.dumps(prev, ensure_ascii=False)
    return vals


def _subst_var_refs(obj: Any, values: Dict[str, Any]) -> Any:
    """블록 몸 텍스트의 `$이름`/`$이름.경로` 를 현재 값으로 — 파서 _resolve_variables 와 같은 규약
    (bare=v4 추출, 경로=_extract_result_field, 부재=ValueError). 구조 키(condition·expr·source)는 값
    바인딩 자리라 건드리지 않고, `$items` 는 엔진의 집합 바인딩 예약어라 제외한다 (M6).
    ★문장 속 참조가 목록을 JSON 으로 넣으면 그 step 에 `_list_in_text` 표식(G31-1) — 파이프의
      주입기(_inject_step_results)와 같은 표식이라 안쪽 파이프의 엔진이 같은 문장으로 번역한다."""
    from workflow_engine import _v4_var_payload, _extract_result_field, _mark_list_in_text, _is_json_list
    names = [k for k in (values or {}) if k != "items"]
    if not names:
        return obj
    import re as _re
    from common.ibl_vars import sub_refs, refs_pattern
    _sole_re = _re.compile(refs_pattern(names))

    def _sub_text(o: str, sink, pkey):
        sole = _sole_re.fullmatch(o.strip()) is not None

        def _one(name, path):
            raw = values[name]
            raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            val = _extract_result_field(raw, path) if path else _v4_var_payload(raw)
            if sink is not None and not sole:
                lst = _is_json_list(val)
                if lst is not None:
                    sink.append((pkey, f"${name}{path}", len(lst)))
            return val
        return sub_refs(o, names, _one)

    def _walk(o, key=None, sink=None, pkey=None):
        if isinstance(o, str):
            if key in ("condition", "expr", "source"):
                return o
            return _sub_text(o, sink, pkey)
        if isinstance(o, dict):
            # 중첩 블록은 건드리지 않는다 — 그 블록의 실행기가 *자기 실행 시점*의 (더 새로운) 값으로 치환한다
            if any(o.get(k) for k in ("_condition", "_case", "_try", "_repeat", "_assign", "_goal")):
                return o
            if isinstance(o.get("params"), dict):
                my_sink = []
                new = {}
                for k, v in o.items():
                    if k == "params":
                        new[k] = {pk: _walk(pv, pk, my_sink, pk) for pk, pv in v.items()}
                    else:
                        new[k] = _walk(v, k)
                for pk, ref, rows in my_sink:
                    _mark_list_in_text(new, pk, ref, rows)
                return new
            return {k: _walk(v, k, sink, pkey) for k, v in o.items()}
        if isinstance(o, list):
            return [_walk(v, None, sink, pkey) for v in o]
        return o
    return _walk(obj)


def _stamp_var_values(steps: Any, values: Dict[str, Any]) -> None:
    """몸(파이프) 안의 블록 step 에 바깥 변수 값을 내려보낸다 — 안쪽 값이 우선(M6)."""
    if not values:
        return
    if isinstance(steps, dict):
        steps = [steps]
    if not isinstance(steps, list):
        return
    for st in steps:
        if not isinstance(st, dict):
            continue
        if any(st.get(k) for k in ("_condition", "_case", "_try", "_repeat", "_assign")):
            st["_var_values"] = {**values, **(st.get("_var_values") or {})}
        for key in ("branches", "body", "catch", "finally", "default", "action", "_branch_steps"):
            v = st.get(key)
            if isinstance(v, (list, dict)):
                _stamp_var_values(v, values)


def _run_branch(action: Any, tool_input: dict, project_path: str, agent_id: str) -> Any:
    """if/case 분기 몸 실행 — 단일 액션(dict)과 **파이프(steps 리스트)** 둘 다.

    ★2026-08-16 상상훈련 9회차: 파서는 분기 몸의 파이프를 steps 리스트로 담는데
    실행기가 dict 만 가정해 `'list' object has no attribute 'get'` 으로 죽었다 —
    문법이 허용하는 모양(블록 속 파이프)을 실행기가 전부 받아야 한다.
    """
    prev = _prev_of(tool_input)
    # ★B49-2(49회차): 분기 몸의 할당은 되쓸 슬롯이 없어 경계에서 전량 떨어진다.
    #   치환 전 원본에서 이름을 걷는다(치환이 모양을 바꾸기 전에).
    from ibl_honesty import note_vars_dropped as _note_vars_dropped
    _body_src = action
    try:
        action = _subst_var_refs(copy.deepcopy(action), tool_input.get("_var_values") or {})
    except ValueError as e:
        return {"success": False, "error": f"분기 몸의 $변수 치환 실패: {e}"}
    if isinstance(action, list):
        from workflow_engine import execute_pipeline
        steps = [_nest(s, tool_input) for s in action]
        _stamp_var_values(steps, tool_input.get("_var_values") or {})
        return _note_vars_dropped(
            execute_pipeline(steps, project_path, agent_id=agent_id,
                             context=({"_prev_result": prev} if prev else None)),
            _body_src)
    from ibl_engine import execute_ibl
    from workflow_engine import _auto_inject_prev
    st = _nest(action, tool_input)
    if prev and isinstance(st, dict) and not st.get("_assign"):
        st = _auto_inject_prev(st, prev)
    return _note_vars_dropped(execute_ibl(st, project_path, agent_id), _body_src)


def _execute_condition(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """
    if/else 조건문 실행

    각 분기의 조건을 평가하고, 매칭되는 분기의 action을 실행한다.
    """
    branches = tool_input.get("branches", [])
    # ★2026-08-15: 조건 평가 실패를 삼키지 않는다. 옛 코드는 `except: continue` 로 다음
    # 분기에 넘어가 "모든 조건 불일치"라는 *정상 메시지*로 끝났다 — 조건이 거짓이어서
    # 안 걸린 건지 평가가 터진 건지 호출자가 구별할 수 없었다(침묵 실패 계열).
    cond_errors = []

    for branch in branches:
        condition = branch.get("condition")
        action = branch.get("action")

        if condition is None:
            # else 분기
            # ★B10 (2026-08-17 상상훈련 11회차): 앞선 조건 평가가 실패했다면(cond_errors)
            # else 실행은 "그 조건이 거짓이었다"는 단정이 된다 — B8(읽기 실패=조용한 거짓)이
            # 한 층 위에서 재발한 모양. 판정 불능 상태에선 else 를 보류하고 정직 실패로.
            if cond_errors:
                return {
                    "success": False,
                    "error": f"조건 평가 실패 {len(cond_errors)}건 — 판정 불능이라 else 분기를 보류했습니다"
                             "(else 실행=조건 거짓의 단정).",
                    "condition_errors": cond_errors,
                }
            if action:
                return _attach_branch_meta(
                    _run_branch(action, tool_input, project_path, agent_id),
                    matched="else", matched_value=None, tool_input=tool_input)
            return {"message": "else 분기 실행 (action 없음)", "matched": "else"}

        # 조건 평가: 소스 참조 실행 + $변수(앞 문장 결과, _var_values) 술어
        try:
            sense_result, left_value = _evaluate_condition_and_value(
                condition, project_path, agent_id, _vars_with_items(tool_input))
        except Exception as e:
            cond_errors.append({"condition": condition, "error": str(e)})
            continue  # 이 분기는 판정 불능 — 다음 분기로 가되 위에 기록해 둔다

        if sense_result:
            if action:
                return _attach_branch_meta(
                    _run_branch(action, tool_input, project_path, agent_id),
                    matched=condition, matched_value=left_value, tool_input=tool_input)
            return {"message": f"조건 충족: {condition}",
                    "matched": condition, "matched_value": _meta_safe(left_value)}

    if cond_errors:
        # 어느 분기도 안 걸렸는데 평가 실패가 있었다면 그건 성공이 아니다.
        return {
            "success": False,
            "error": f"조건 평가 실패 {len(cond_errors)}건 — 어느 분기도 실행하지 못했습니다.",
            "condition_errors": cond_errors,
        }
    return {"message": "모든 조건 불일치, 실행할 분기 없음"}


def _execute_case(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """
    case문 실행

    source에서 sense 값을 가져온 후 분기를 선택하여 action 실행.
    """
    from goal_evaluator import select_case_branch

    source = tool_input.get("source", "")
    branches = tool_input.get("branches", [])
    default = tool_input.get("default")

    # source에서 sense 값 가져오기 — ★B10-case (2026-08-17 상상훈련 11회차 판정):
    # "값을 읽지 못함"(오타 경로·실행 실패=판정 불능)과 "필드는 실존하되 값이 null"
    # (정당한 부재 — 예: 데스크탑의 battery)을 구별한다. 전자에 default 를 실행하면
    # "어느 패턴과도 불일치"라는 단정이 된다(B10 else 위장의 case 짝). 후자는 default 가
    # 부재의 의미를 받는 정당한 용법이라 보존.
    # ★B33-1 (2026-08-23 상상훈련 33회차): 좌변 해석기를 if 와 **하나로** 통일한다.
    #   옛 코드는 `$` 접두만 평가기에 보내고 나머지는 소스 참조라고 단정했다 — 그래서
    #   교재가 "조건 언어(if/case 공통)"라 가르치는 술어 함수가 case 에서만 죽었다
    #   (실측: `[case: count($items)]` → "판정 불능", 같은 자리 `[if: count($items) > 0]` 은 통과).
    #   ★특례를 더하지 않고 **판별을 없앤다** — atom_value 는 리터럴·$변수·술어함수·소스참조
    #     네 갈래를 이미 모두 알고, 소스 참조는 resolve_source 콜백으로 처리하므로 옛 동작은
    #     그대로 보존된다. if 쪽 _evaluate_condition_and_value 와 같은 배선이다.
    from ibl_predicates import Evaluator, PredicateError

    def _resolve(src: str):
        return _get_sense_value_checked(src, project_path, agent_id)

    try:
        sense_value = Evaluator(_resolve, _vars_with_items(tool_input)).atom_value(source.strip())
        read_error = None
    except PredicateError as e:
        sense_value, read_error = None, str(e)

    if read_error is not None:
        return {
            "success": False,
            "error": f"case source '{source}' 판정 불능 — {read_error} "
                     "default 실행을 보류했습니다(default 실행=값 불일치의 단정).",
        }

    if sense_value is not None:
        action = select_case_branch(sense_value, branches, default)
    else:
        action = default

    # ★P2 (2026-08-20): 어느 분기를 탔는지 라벨 복원 — select_case_branch 는 action 만
    # 돌려줘 결과만으론 오분기 진단이 원리적으로 불가했다. default 포함 라벨 + 좌변
    # 실측값을 관측 메타로 병기한다.
    matched = "default"
    if action is not None:
        for b in branches:
            if b.get("action") is action:
                matched = str(b.get("pattern") or b.get("range") or "?")
                break

    if action:
        return _attach_branch_meta(
            _run_branch(action, tool_input, project_path, agent_id),
            matched=matched, matched_value=sense_value, tool_input=tool_input)

    return {"message": f"case문 실행 완료 (source={source}, value={sense_value})",
            "matched": matched, "matched_value": _meta_safe(sense_value)}



def _evaluate_condition_and_value(condition: str, project_path: str, agent_id: str,
                                  var_values: Optional[Dict[str, Any]] = None) -> tuple:
    """
    조건식 평가 — (판정 bool, 첫 좌변 실측값) 반환.

    ★P2 (2026-08-20): 좌변값을 함께 반환하는 이유 — 조건 블록 결과에 matched_value 를
    병기하려면 실측값이 필요한데, 별도 재조회는 소스 액션을 두 번 실행(부작용·비용)한다.

    ★2026-08-22 프로그램급 IBL M2: 문법은 ibl_predicates 로 옮겼다 — 소스 참조
    `node:action{…}[.field] <op> 값` 은 그대로이고, 그 위에 `$변수[.경로]` 좌변(실행 없이
    이미 가진 값)·count/empty/exists·matches(정규식)·and/or/not·괄호·AI 술어
    (`[table:brief]{…} == "yes"`)가 얹혔다. 판정 불능은 ValueError(PredicateError)로 올라
    _execute_condition 의 cond_errors 정직 채널을 탄다(B8 — 거짓으로 접지 않음).
    var_values = {변수명: 앞 문장 결과(문자열)} — 파이프 엔진이 _var_values 로 실어 준다.
    """
    from ibl_predicates import evaluate

    def _resolve(src: str):
        # 소스 참조 실행 — 검침판(판정 불능 사유 동반, F13-4)
        return _get_sense_value_checked(src, project_path, agent_id)

    return evaluate(condition, _resolve, var_values)


def _evaluate_sense_condition(condition: str, project_path: str, agent_id: str) -> bool:
    """불리언만 필요한 호출자용 호환 셈 (ibl_engine 재수출 계약 유지)."""
    return _evaluate_condition_and_value(condition, project_path, agent_id)[0]


# try/catch/finally · repeat · [table:reduce] 실행기(프로그램급 IBL M3~M5)는 형제 모듈
# ibl_control_blocks.py 에 산다(1500줄 규칙) — 여기서 import 하지 않는다(단방향: 그쪽이 이쪽을 쓴다).
