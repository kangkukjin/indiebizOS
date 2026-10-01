"""용례 채널의 소비 경계 투영 — 저장·기록된 원문을 고치지 않고 읽는 쪽에서 실제 문장으로 푼다.

옛 판본의 단일 호출 용례를 현재 판본 문장으로, 검사 통과분 참조(`$checked:<id>`)를 그 검사 호출의 원문으로."""
import time
from typing import Optional

_LEGACY_SINGLE_CALL = None
_current_form_cache: dict = {}
_registry_cache = {"at": 0.0, "value": None}


def current_form_of_legacy_call(code: str) -> Optional[str]:
    """판본 1 의 *단일 호출* 용례를 현재 판본 문장으로 옮긴다 — 현재 검사기가 통과시킨 것만.

    판본 1 원문은 작성 답안에서 빠져 회상에 제목만 실렸다(코퍼스 3,743건 중 2,360건). ep4214 는 딱 맞는
    용례 둘(`[sense:video]` info·summarize)이 떴는데 코드가 없어 describe 라운드를 따로 썼다.
    호출 하나짜리(`[node:action]{…}`, 변수·중첩 없음)는 문법이 두 판본에서 같으므로 `return` 을 붙여
    현재 컴파일러에 넣어 보고, 진단이 없을 때만 본문으로 보인다. 저장 원문은 고치지 않는다 —
    소비 경계에서의 투영이다. 여러 문장·파이프·변수가 있는 옛 원문은 그대로 숨긴다."""
    global _LEGACY_SINGLE_CALL
    if not isinstance(code, str):
        return None
    source = code.strip()
    if _LEGACY_SINGLE_CALL is None:
        import re
        _LEGACY_SINGLE_CALL = re.compile(r"\[[a-z_]+:[a-z_]+\]\{[^{}\[\]$]*\}")
    if len(source) > 1200 or not _LEGACY_SINGLE_CALL.fullmatch(source):
        return None
    if source in _current_form_cache:
        return _current_form_cache[source]
    current = "#!ibl edition=2\nreturn " + source
    try:
        from ibl_v2_adapters import load_registry
        from ibl_v2_compile import compile_program
        from ibl_v2_store import definitions
        now = time.monotonic()
        if _registry_cache["value"] is None or now - _registry_cache["at"] > 600:
            _registry_cache.update(at=now, value=load_registry())
        plan = compile_program(current, _registry_cache["value"], {}, definitions())
        result = None if plan.issues else current
    except Exception:
        return None          # 검사 기반이 없으면 투영하지 않는다(캐시도 하지 않는다)
    if len(_current_form_cache) < 4096:
        _current_form_cache[source] = result
    return result


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
