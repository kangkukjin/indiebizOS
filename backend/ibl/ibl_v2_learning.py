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
            IBLUsageDB().update_success_by_code(code, event["success"] and result.get("source_complete", False))
