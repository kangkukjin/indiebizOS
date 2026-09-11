"""모델/MCP 전송 상한. 표시 투영과 별개이며 원문 참조 없이 JSON을 절단하지 않는다."""
import json
from itertools import chain

from ibl_envelope import diet_envelope, display_delivery_budget, summarize_result
from ibl_honesty import HONESTY_KEYS, completion_evidence

PER_ACTION_CHARS = 16_000


def _parse(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def provider_tool_result(raw: str, per_action: int = PER_ACTION_CHARS) -> str:
    """공급자별 공통 규칙. 액션 수는 본문 정규식이 아닌 실행 봉투에서 읽는다."""
    parsed = _parse(raw)
    actions = parsed.get("_action_count", 1) if isinstance(parsed, dict) else 1
    actions = max(1, actions) if type(actions) is int else 1
    budget = display_delivery_budget(raw, per_action * actions)
    return fit_tool_result(raw, budget)


def _condense_items(obj, cap):
    if isinstance(obj, str):
        parsed = _parse(obj) if obj.lstrip().startswith(("{", "[")) else None
        return json.dumps(_condense_items(parsed, cap), ensure_ascii=False) if parsed is not None else obj
    if isinstance(obj, list):
        return [_condense_items(item, cap) for item in obj]
    if not isinstance(obj, dict):
        return obj
    out = {key: _condense_items(value, cap) for key, value in obj.items() if key != "items"}
    if "items" in obj:
        out["items"] = _condense_items(obj["items"][:cap], cap) if isinstance(obj["items"], list) else obj["items"]
    if isinstance(obj.get("items"), list) and len(obj["items"]) > cap:
        out["_omitted_items"] = len(obj["items"]) - cap
    return out


def _diagnostic(value):
    """전송용 작은 진단. 상세 생략은 ref와 _transport_omitted에서 명시한다."""
    if isinstance(value, str):
        return value if len(value) <= 200 else value[:200] + f"…(전체 {len(value)}자, ref 참조)"
    if isinstance(value, list):
        return [_diagnostic(item) for item in value[:2]]
    if isinstance(value, dict):
        return {key: _diagnostic(item) for key, item in list(value.items())[:20]}
    return value


def fit_tool_result(raw: str, budget: int) -> str:
    """한도 이내는 바이트 보존. 초과는 원문 저장→단계 요약→행 축소→참조 봉투.

    result_ref는 최초 실행 원문을 가리킨다. 전송 사본의 spill ref가 이를 덮지 않는다.
    산문도 저장하므로 재실행 없이 회수할 수 있다. 앱·IBL 변수는 이 함수를 거치지 않는다.
    """
    if len(raw) <= budget:
        return raw
    from common.spill import spill_write
    saved = spill_write(raw, tag="model_result")
    saved["_trimmed"] = "전달 한도로 본문 표시를 생략했습니다. ref.path의 원문을 읽으세요(재실행 불필요)."
    parsed = _parse(raw)
    dumps = lambda value: json.dumps(value, ensure_ascii=False)

    if isinstance(parsed, dict):
        slim = diet_envelope(parsed)
        # 기존 참조를 원형 그대로 남기기 위해 전송 참조는 별도 이름을 쓴다.
        for candidate in chain([slim], (_condense_items(slim, cap) for cap in (10, 5, 3, 1))):
            candidate = {**candidate, "transport_ref": saved["ref"], "_trimmed": saved["_trimmed"]}
            text = dumps(candidate)
            if len(text) <= budget:
                return text

        omitted = {}
        # 실패/부분 성공의 의미와 재개·원문 참조를 먼저 보존한다. 거대 오류도 실패로 보인다.
        issues = completion_evidence(parsed)
        if issues:
            parsed = {**parsed, "completion_issues": issues}
        keys = ("success", "error", "warning", "reason", "step", "steps_completed", "steps_total",
                "completion_issues",
                "resume", "result_ref", "source_ref", *HONESTY_KEYS)
        for key in dict.fromkeys(keys):
            if key not in parsed:
                continue
            value = parsed[key]
            preview = value if key in {"resume", "result_ref", "source_ref"} else _diagnostic(value)
            if preview != value:
                omitted[key] = {"chars": len(dumps(value)), "in_ref": True}
            if len(dumps({**saved, key: preview, "_transport_omitted": omitted})) <= budget - 1500:
                saved[key] = preview
            else:
                omitted[key] = {"chars": len(dumps(value)), "in_ref": True}
        if "final_result" in parsed:
            summary = summarize_result(parsed["final_result"])
            if len(dumps({**saved, "final_result_summary": summary})) <= budget - 800:
                saved["final_result_summary"] = summary
        if omitted:
            saved["_transport_omitted"] = omitted
    else:
        saved["preview"] = raw[:min(1000, max(0, budget - len(dumps(saved)) - 100))]
    text = dumps(saved)
    if len(text) > budget:
        raise ValueError(f"전송 한도 {budget}자로는 상태·원문 참조를 전달할 수 없습니다. 호스트 한도를 늘리세요.")
    return text
