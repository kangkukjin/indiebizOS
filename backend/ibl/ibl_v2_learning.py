"""Compiler-backed entry checks for edition 2 reusable memory."""
from ibl_edition import source_edition
from ibl_v2_ir import Fault
from ibl_v2_parser import parse


def check_source(source, function_body=False, *, registry=None, library=None):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_store import definitions, definition_name
    try:
        source_edition(source, 2)
        if function_body:
            definition_name(source)
        plan = compile_program(source, load_registry() if registry is None else registry,
                               definitions=definitions() if library is None else library)
        return "; ".join(i["message"] for i in plan.issues) or None
    except (Fault, ValueError) as exc:
        return str(exc)


def signature(source):
    statements = parse(source).data["statements"]
    if len(statements) == 1 and statements[0].kind == "def":
        return [name for name, default in statements[0].data["params"].items() if default is None]
    # A reusable complete v2 program must close every input. The compiler owns
    # that decision, so there is no second regex free-variable implementation.
    why = check_source(source)
    if why:
        raise ValueError(why)
    return []


def record_functions(plan, result):
    """Attribute actual native library calls to their exact stored source."""
    from ibl_usage_db import IBLUsageDB
    from member_runtime import is_member
    if is_member():
        return
    entries = plan.dependencies.get("source_map", [])[1:]
    for event in result.get("evidence", []):
        if event.get("kind") != "function_result":
            continue
        entry = next((s for s in entries if s["start"] <= event["definition_start"] < s["end"]), None)
        if entry:
            code = plan.source[entry["start"]:entry["end"]]
            # 함수의 성적은 그 함수가 값을 돌려줬는가다(2026-09-26). 종전엔 프로그램 봉투의
            # source_complete 와 AND 했는데, 09-25 언어 개정(91448265)으로 catch 한 외부 실패도
            # source_complete:false 가 되면서 "자료 하나 빠지면 한계를 적고 완료" 하도록 설계된
            # 보고서 관용구가 설계대로 동작한 턴마다 fail_count 를 먹었다(AI동향준비읽기·검색묶음추리기·
            # 웹앱검사하기 실측). 원천 불완전은 봉투가 따로 말한다 — 성적과 섞지 않는다.
            IBLUsageDB().update_success_by_code(code, bool(event["success"]))
