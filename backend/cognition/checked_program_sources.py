"""검사 통과분 손잡이에서 현행 원문을 복원한다."""


def checked_program_sources(tool_calls) -> dict:
    """이 턴의 검사 호출이 내준 `$checked:<id>` 손잡이 → 그 검사의 프로그램 원문.

    검사 통과분은 원문을 다시 적지 않고 손잡이로 실행한다. 도구 호출 기록에는 손잡이만 남으므로,
    실행한 프로그램을 배우는 쪽(경험 증류)은 같은 턴의 검사 호출에서 원문을 되찾는다."""
    import re
    handle_re = re.compile(r"\$checked:[0-9a-f]{64}")
    out = {}
    for tc in tool_calls or []:
        inputs = tc.get("input") if isinstance(tc, dict) else None
        if not isinstance(inputs, dict) or not inputs.get("check") or not isinstance(inputs.get("code"), str):
            continue
        result = tc.get("result")
        text = result if isinstance(result, str) else str(result)
        found = handle_re.search(text or "")
        if found and not inputs["code"].strip().startswith("$checked:"):
            out[found[0]] = inputs["code"]
    return out
