"""
workflow_binding.py — 파이프 이음매의 변수·통화 바인딩 (2026-08-22 분리)

workflow_engine.py 가 1500줄 규칙을 넘어, 형제 모듈 workflow_fallback.py 와 같은 방식으로
**이음매 헬퍼**를 떼어냈다. 실행 제어(순차·분기·중단)는 본체가 갖고, 여기 있는 것은
step 과 step 사이에서 값이 어떻게 옮겨 앉는가 하나다:

  · $var / $var.field  → 저장된 step 결과에서 값 꺼내기 (_extract_result_field·_v4_var_payload)
  · $items / $items.필드 → 직전 통화를 param 에 통째로 바인딩 (_bind_items_params)
  · 직전 결과 자동 주입 (_inject_prev_result·_auto_inject_prev·_has_prev_ref)
  · 통화 정규화·표시 (_to_prev_currency·_step_label·_to_string)

호출자(workflow_parallel·workflow_fallback·ibl_control_blocks·ibl_executors·테스트)는
지금까지처럼 `from workflow_engine import ...` 로 계속 집어간다 — 본체가 재수출한다.
"""

import re
import json
from typing import Any, Dict, Tuple


# $var 바인딩 참조 패턴 — 파서(_resolve_variables)가 $var 를 {{_step_N_result}} 로,
# $var.field.path 를 {{_step_N_result.field.path}} 로 치환한다 (G1, 2026-08-16).
_STEP_RESULT_RE = re.compile(r"\{\{_step_(\d+)_result((?:\.\w+)*)\}\}")


def _extract_result_field(raw: str, path: str) -> str:
    """저장된 step 결과 문자열에서 .field.path 를 추출해 스칼라 문자열로.

    실패는 조용한 빈 문자열이 아니라 ValueError — 없는 필드가 침묵히 "" 로 치환되면
    하류가 빈 param 으로 "성공"하는 침묵 실패 부류가 된다(P 시리즈 원칙)."""
    obj: Any = raw
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                obj = json.loads(s)
            except (json.JSONDecodeError, ValueError):
                raise ValueError(
                    f"$변수 필드 추출 실패: 결과가 JSON 이 아니라 '{path}' 경로를 풀 수 없습니다.")
        else:
            raise ValueError(
                f"$변수 필드 추출 실패: 결과가 구조화 데이터가 아니라 '{path}' 경로를 풀 수 없습니다.")
    for key in path.lstrip(".").split("."):
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        elif isinstance(obj, list) and key.isdigit() and int(key) < len(obj):
            obj = obj[int(key)]
        else:
            # 필드 힌트의 절단도 신고한다 (F18-1 부류 — 침묵 클램프 금지)
            if isinstance(obj, dict):
                _names = list(obj.keys())
                avail = (_names[:12] + [f"…외 {len(_names) - 12}개"]) if len(_names) > 12 else _names
            elif isinstance(obj, list):
                avail = f"목록(길이 {len(obj)})"
            else:
                avail = type(obj).__name__
            raise ValueError(
                f"$변수 필드 추출 실패: '{key}' 필드가 없습니다 (경로 {path}, 사용 가능: {avail}).")
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)
    return "" if obj is None else str(obj)


def _v4_var_payload(raw: str) -> str:
    """bare `$var` 치환의 기본값 — v4 추출 계약 합류 (2026-08-20 상상훈련 17회차 F17-3 판정).

    옛 동작: 결과 봉투 JSON 전체를 문자열화 → write content 에 success 같은 배관 키까지
    박혔다(파이프 싱크의 v4 추출과 비대칭). 새 규약: message(산문 정본)/items(통화) 우선,
    폴백=봉투 원형. 명시 경로($var.field.path)는 불변 — 정밀 추출은 경로가 정본.
    규칙은 write v4(system_essentials)와 같은 게이트를 쓴다: 오분류는 항상 안전 방향
    (봉투=구조 보존)으로 떨어진다."""
    s = (raw or "").strip()
    if not s.startswith("{"):
        return raw
    try:
        obj = json.loads(s)
    except Exception:
        return raw
    if not isinstance(obj, dict):
        return raw
    msg = obj.get("message")
    has_msg = isinstance(msg, str) and bool(msg.strip())
    items = obj.get("items")
    items_nonempty = isinstance(items, list) and bool(items)
    other_payload = any(isinstance(v, (dict, list)) and v
                        for k, v in obj.items() if k not in ("items", "message"))
    if has_msg and not other_payload:
        doc_shaped = ("\n" in msg.strip()) or (len(msg) >= 200)
        if doc_shaped or not items_nonempty:
            return msg
    if items_nonempty and not other_payload:
        return json.dumps(items, ensure_ascii=False)
    return raw


def _inject_step_results(obj: Any, step_results: Dict[int, str]) -> Any:
    """{{_step_N_result[.path]}} 참조를 저장된 step 별 결과로 치환 (재귀 — branches/체인 포함).

    변수 바인딩($var)의 실제 구현(D4, 2026-08-05): 예전엔 $var 가 전부 {{_prev_result}} 로
    뭉개졌고, 문장 경계(_seq_boundary)가 prev_result 를 비워 문서화된 예제가 빈 문자열을
    치환받았다. 아직 실행되지 않았거나 예외로 결과가 없는 인덱스는 빈 문자열로 치환한다.
    .path 가 붙으면 결과(JSON)에서 그 필드를 추출한다 — 실패는 ValueError(정직 실패).
    bare 참조는 v4 추출(_v4_var_payload)을 태운다 (F17-3).
    """
    if isinstance(obj, str):
        def _sub(m):
            base = step_results.get(int(m.group(1)), "")
            p = m.group(2)
            if p:
                return _extract_result_field(base, p)
            return _v4_var_payload(base)
        return _STEP_RESULT_RE.sub(_sub, obj)
    if isinstance(obj, dict):
        # 블록은 건드리지 않는다 (M6): 몸은 안쪽 파이프의 인덱스 공간 — 바깥 치환은 실행기가 _vars/_var_values 로.
        if any(obj.get(k) for k in ("_condition", "_case", "_try", "_repeat", "_assign", "_goal")):
            return obj
        return {k: _inject_step_results(v, step_results) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_inject_step_results(v, step_results) for v in obj]
    return obj


# $items 집합 바인딩 행 수 상한 — 초과는 침묵 절단 대신 정직 거절(take 로 줄이라고 안내).
ITEMS_BIND_CAP = 500

# `$items` / `${items}` / `$items.열` — 집합 바인딩 예약어 (표기는 common.ibl_vars 규약)
_ITEMS_REF = re.compile(r'^\$(?:\{\s*items(?:\.(\w+))?\s*\}|items(?:\.(\w+))?)$')


def _bind_items_params(tool_input: dict, prev_result: str):
    """★$items 집합 바인딩 (2026-08-16 상상훈련 G1-③ 판정).

    step 파라미터 *값*이 정확히 "$items"(전체 행) 또는 "$items.필드"(각 행에서 그 필드만)
    이면, 이전 step 결과의 items 리스트를 **실행 시점에 값으로** 바인딩한다.

    - 텍스트 치환이 아니다 — 데이터가 문장 텍스트를 통과하면 이스케이프·페이로드가
      깨진다(옛 shell-IBL 은퇴 사유와 동류). $it(each, 행 단위)의 짝인 집합 단위 규약.
    - 행동 액션(show_map 등)이 **핸들러 수정 없이** 파이프 하류에 서는 길:
        [sense:restaurant]{query:"청주 맛집"} >> [table:take]{n:3} >> [limbs:show_map]{markers: "$items"}
      (verb 마다 _prev_result 소비를 붙이면 F6 비대칭이 재생산된다 — 규약은 언어에 한 번.)
    - 상한 ITEMS_BIND_CAP 초과는 침묵 절단 대신 정직 거절: 앞에 take 를 끼우라고 안내.
    - ★파서의 $var 할당과 공존: `$items = ...` 로 직접 할당하면 파서 치환이 먼저라
      여기 도달하지 않는다 — $items 는 예약어로 쓰지 않기를 권장(가이드 명기).

    반환: (tool_input, error_str|None) — 참조가 없으면 원본 그대로, 바인딩 실패는 정직 에러.
    """
    params = tool_input.get("params")
    if not isinstance(params, dict):
        return tool_input, None
    refs = {k: m for k, v in params.items()
            if isinstance(v, str) and (m := _ITEMS_REF.match(v.strip()))}
    if not refs:
        return tool_input, None

    # 이전 결과에서 items 통화 추출 (prev_result 는 _to_prev_currency 가 이미 items 파생을 마친 JSON)
    items = None
    s = (prev_result or "").strip()
    if s:
        try:
            obj = json.loads(s)
        except Exception:
            obj = None
        # 스필 참조 봉투면 본문으로 (M5)
        from common.spill import resolve_ref
        obj, _ref_err = resolve_ref(obj)
        if _ref_err:
            return tool_input, f"$items 바인딩 실패: {_ref_err}"
        if isinstance(obj, list):
            items = obj
        elif isinstance(obj, dict) and isinstance(obj.get("items"), list):
            items = obj["items"]
    if items is None:
        return tool_input, ("$items 바인딩 실패: 이전 step 결과에 items 통화가 없습니다. "
                            "앞 액션이 통화를 내는 생산자/변환자인지 확인하세요.")
    if len(items) > ITEMS_BIND_CAP:
        return tool_input, (f"$items 바인딩 거절: 행 {len(items)}개 — 상한 {ITEMS_BIND_CAP}. "
                            f"앞에 [table:take]{{n: ...}} 또는 filter 로 줄여 주세요(침묵 절단 금지).")

    out = dict(tool_input)
    out["params"] = dict(params)
    for key, m in refs.items():
        field = m.group(1) or m.group(2)   # 괄호형 `${items.열}` / 맨몸 `$items.열`
        if field:
            missing = [1 for r in items if not (isinstance(r, dict) and field in r)]
            if items and len(missing) == len(items):
                return tool_input, (f"$items.{field} 바인딩 실패: '{field}' 필드가 어느 행에도 없습니다. "
                                    f"실제 필드: {sorted(items[0].keys()) if isinstance(items[0], dict) else '비-dict 행'}")
            out["params"][key] = [r.get(field) for r in items if isinstance(r, dict)]
        else:
            out["params"][key] = items
    return out, None


def _inject_prev_result(tool_input: dict, prev_result: str) -> dict:
    """{{_prev_result}} 템플릿을 이전 결과로 치환"""
    injected = {}
    for key, val in tool_input.items():
        if isinstance(val, str):
            injected[key] = val.replace("{{_prev_result}}", prev_result)
        elif isinstance(val, dict):
            injected[key] = _inject_prev_result(val, prev_result)
        else:
            injected[key] = val
    return injected


def _has_prev_ref(tool_input: dict) -> bool:
    """tool_input 어디에든 {{_prev_result}} 참조가 남아있는지 확인"""
    for key, val in tool_input.items():
        if isinstance(val, str) and "{{_prev_result}}" in val:
            return True
        elif isinstance(val, dict) and _has_prev_ref(val):
            return True
    return False


def _resolve_spill_for_injection(prev: Any) -> Any:
    """스필 참조를 **주입 이음매 하나에서** 본문으로 되돌린다 (B27-2, 27회차).

    교재가 스필을 이렇게 약속한다 — *"step 봉투엔 참조만 실리지만 **뒤 step 은 그 참조를
    투명하게 해소해 원래 데이터를 그대로 본다**(파이프 흐름 불변 · 가벼워지는 건 results[]·
    모델 컨텍스트뿐)"*. 그런데 해소기가 **입구가 아니라 소비처마다** 흩어져 있었다:
      · workflow_binding `$items` 바인딩 · ibl_exec_each · ibl_exec_output `_sink_content`
      · data-ops `_get_items`
    네 곳을 두고도 구멍이 남는다. 실측(2026-08-23):
        [self:body]{days: 2, limit: 20} >> [self:write]{path: …, spill: true} >> [table:groupby]{by: "영역"}
        → "groupby: 입력에서 items 통화를 찾지 못했습니다"
    `_op_groupby` 는 `_rows_for_field` 로 들어가는데 해소기는 형제 입구인 `_get_items` 에만
    있었다 — **한 파일 안에서도 입구가 둘**이었다. 게다가 `_prev_result` 를 읽는 7개 패키지 중
    해소기를 가진 것은 둘뿐이라(ai-ops·visualization·media_producer·blog·android 는 없음),
    자동 스필(`_spill_if_large`)이 큰 결과를 참조로 바꾸는 순간 — 즉 **데이터가 클수록** —
    그 다섯은 0행을 보게 된다.

    25회차가 같은 모양의 결함에 내린 판정을 그대로 적용한다: **해소기는 하나여야 한다.**
    `_prev_result` 가 핸들러에 닿는 자리는 `_auto_inject_prev` 하나뿐이므로 여기서 푼다 —
    그러면 7개 패키지 전부와 앞으로 생길 패키지가 계약을 공짜로 상속한다.
    소비처의 기존 해소기는 지우지 않는다: 파이프가 아닌 입구(리터럴 씨앗·params 직접 통화)는
    이 이음매를 지나지 않으므로 중복이 아니라 **다른 입구의 담당**이다(resolve_ref 는 멱등).

    ★만료·부재는 여기서 삼키지 않고 참조를 **그대로 흘려보낸다** — 소비처의 기존 정직 오류가
    그대로 신고한다(이 수리가 새로 만드는 침묵 경로 0).
    """
    if not isinstance(prev, str):
        return prev
    s = prev.strip()
    if not (s.startswith("{") and '"ref"' in s):
        return prev                      # 빠른 경로 — 스필 봉투가 아닌 절대다수는 무비용
    try:
        obj = json.loads(s)
    except Exception:
        return prev
    try:
        from common.spill import is_ref, resolve_ref
        if not is_ref(obj):
            return prev
        resolved, err = resolve_ref(obj)
    except Exception:
        return prev
    if err or resolved is obj:
        return prev
    return _to_string(resolved)


def _auto_inject_prev(tool_input: dict, prev_result: str) -> dict:
    """
    파이프라인 자동 데이터 전달.

    prev_result가 있고, step에 {{_prev_result}} 명시 참조가 없으면
    params._prev_result로 자동 주입.

    이를 통해 [sense:web_search]{query: "A"} >> [engines:newspaper]{query: "B"} 같은 파이프라인에서
    step 2가 step 1의 결과를 자동으로 받을 수 있다.
    """
    if not prev_result:
        return tool_input

    prev_result = _resolve_spill_for_injection(prev_result)   # 스필 해소는 입구 하나에서 (B27-2)

    # 이미 {{_prev_result}} 템플릿 치환이 끝난 후이므로,
    # 원본에 참조가 있었다면 이미 치환됨 → 자동 주입 불필요
    # 참조가 없었던 경우에만 자동 주입
    # (치환 전 원본을 검사하는 것이 이상적이나, 현재 구조에서는
    #  치환 후에 호출하므로 params에 _prev_result가 이미 있는지 확인)
    params = tool_input.get("params", {})
    if isinstance(params, dict) and "_prev_result" not in params:
        tool_input = dict(tool_input)
        tool_input["params"] = dict(params)
        tool_input["params"]["_prev_result"] = prev_result

    return tool_input


def _to_prev_currency(result: Any) -> str:
    """다음 step 주입용 문자열 — **파이프 이음매에서만** 단일 통화(items)를 파생한다.

    감사 D13(2026-08-05): currency.py 문서는 파생 관문을 _route_handler 로 적었지만 실제
    호출처는 렌더러 경계(api_ibl)와 body_ask 뿐이라, table/blocks 만 내는 생산자가
    `>> [table:sort]` 파이프 안에서 items 를 못 찾고 깨졌다. 관문을 _route_handler 로 옮기면
    에이전트 최종 tool-result 에도 파생본이 실려 토큰이 중복된다(api_ibl 주석의 의도된 회피).
    → 진짜 갭은 파이프 이음매: prev_result 로 다음 step 에 물릴 때만 파생한다.
    results[]/step_results(모델·호출자에게 보이는 쪽)는 원형 유지 = 토큰 중복 0.

    JSON 문자열 결과(대다수 핸들러)도 파싱→파생→재직렬화로 커버. 파싱 불가면 원형 그대로.
    """
    from common.currency import derive_items
    r = result
    if isinstance(r, str):
        s = r.strip()
        if not (s.startswith("{") and s.endswith("}")):
            return _to_string(result)
        try:
            r = json.loads(s)
        except Exception:
            return _to_string(result)
    if isinstance(r, dict):
        return _to_string(derive_items(r))
    return _to_string(result)


def _step_label(step: Any) -> Tuple[str, str]:
    """봉투 results[] 의 (node, action) 라벨 — 블록 step 은 if/case/goal + "block" (옛 "?").
    긴 문장이 "어느 step 에서 왜" 죽었는지 읽으려면 블록도 이름이 있어야 한다(2026-08-22 M2)."""
    if not isinstance(step, dict):
        return "?", "?"
    if step.get("_condition"):
        return "if", "block"
    if step.get("_case"):
        return "case", "block"
    if step.get("_goal"):
        return "goal", "block"
    if step.get("_try"):
        return "try", "block"
    if step.get("_repeat"):
        return "repeat", "block"
    if step.get("_assign"):
        return "assign", f"${step.get('name')}"
    return step.get("_node", step.get("node", "?")), step.get("action", "?")


def _to_string(result: Any) -> str:
    """결과를 문자열로 변환 (다음 step 의 _prev_result 로 주입)."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # 포워드된 결과 봉투 벗기기 — @hub/@노드 로 원격 실행된 bare-string 읽기는
        # {"result": "<본문>", "_forwarded_to": ...} 로 감싸져 온다. 다음 step 은 전송 봉투가
        # 아니라 *본문*을 원하므로 내부 본문만 넘긴다(크로스노드 이음매).
        # ★단 통화(items/table)가 있으면 벗기지 않는다 — 변환자(table:sort 등)가 통화를 소비해야
        #   하는데, text 같은 요약 문자열로 벗기면 통화가 사라진다(file_find@hub >> sort 회귀).
        if result.get("_forwarded_to") and "items" not in result and "table" not in result:
            for _k in ("result", "message", "markdown", "text", "content"):
                _v = result.get(_k)
                if isinstance(_v, str):
                    return _v
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, (list, tuple)):
        return json.dumps(result, ensure_ascii=False)
    return str(result)
