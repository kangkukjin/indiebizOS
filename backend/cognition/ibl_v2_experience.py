"""Keep successful v2 programs intact across memory selection boundaries."""
import json
from ibl_edition import explicit_source, source_edition


def closed_call(tc):
    request = tc.get("input") or {}
    source = request.get("code", "")
    if source_edition(source, request.get("edition")) != 2:
        return tc
    result = tc.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return None
    if (request.get("inputs") or not isinstance(result, dict) or
            result.get("success") is not True or result.get("executed") is not True or
            result.get("source_complete") is not True):
        return None
    # Inputs and original source still live in the execution trace. We never
    # embed personal input values into a new reusable procedure automatically.
    code = explicit_source(source, 2)
    from ibl_v2_learning import check_source
    if check_source(code):
        return None
    return {**tc, "input": {**request, "code": code}}


def select_program(ids, calls):
    selected = [calls[i - 1] for i in ids]
    if not any(source_edition(code) == 2 for code in selected):
        return None
    if len(selected) != 1:
        return (None, "판본 2 프로그램은 반환·범위가 닫힌 한 실행 단위로 선택하세요. 판본 혼합·호출 연결은 자동 생성하지 않습니다.")
    from ibl_v2_learning import check_source
    why = check_source(selected[0])
    return (None, why) if why else (selected[0], f"판본 2 원문 호출 {ids[0]}")
