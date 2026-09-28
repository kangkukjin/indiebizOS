"""Data-selected value checks shared by current IBL inspection and execution."""
from contextvars import ContextVar
from ibl_callable_contract import UNRESOLVED

_depth = ContextVar("ibl_code_check_depth", default=0)


def value_problems(contract, values, registry=None, definitions=None):
    known = {k: v for k, v in values.items() if v is not UNRESOLVED}
    errors = []
    validator = contract.get("value_validator")
    op = known.get("op", "create")
    if validator and op in ("create", "watch", "update"):
        from calendar_rules import normalize_schedule_config
        if validator == "trigger":
            from trigger_engine import resolve_trigger_config
            if op != "update" or "cron" in known or "config" in known:
                result = resolve_trigger_config(known, known.get("type", "schedule"))
                if result.get("error"):
                    errors.append(result["error"])
        elif validator in ("schedule", "calendar"):
            fields = {k: known[k] for k in ("date", "time", "repeat", "weekdays", "month", "day", "interval_hours") if k in known}
            delayed = known.get("minutes", 0) or known.get("seconds", 0)
            if fields and not delayed and op != "update":
                fields.setdefault("repeat", "none")
                # schedule resolves a time-only one-shot to today's date.
                result = normalize_schedule_config(fields, require_date=validator != "schedule")
                if result.get("error"):
                    errors.append(result["error"])
    # Strings containing programs are explicitly declared in the vocabulary.
    for name in contract.get("code_params", []):
        code = known.get(name)
        if not isinstance(code, str) or not code.strip():
            continue
        if validator == "calendar" and not any(token in code for token in ("[", "#!ibl", "return", "$")):
            continue
        if _depth.get() >= 4:
            errors.append(f"{name}: 중첩 문장 검사 깊이 4를 초과했습니다.")
            continue
        token = _depth.set(_depth.get() + 1)
        try:
            from ibl_edition import source_edition
            edition = source_edition(code, known.get("edition") if code.lstrip().startswith("#!ibl") else known.get("edition", 2))
            if edition == 2:
                from ibl_v2_compile import compile_program
                from ibl_v2_adapters import load_registry
                inputs = known.get("inputs", {})
                plan = compile_program(code, registry if registry is not None else load_registry(),
                                       inputs if isinstance(inputs, dict) else {}, definitions or {})
                errors.extend(f"{name}: {issue['message']} ({issue['code']})" for issue in plan.issues[:5])
            else:
                from workflow_engine import preflight_sentence
                result = preflight_sentence(code, known.get("inputs"))
                if not result.get("runnable"):
                    errors.append(f"{name}: {result.get('problem')}")
        except Exception as exc:
            errors.append(f"{name}: 문장 검사 실패: {exc}")
        finally:
            _depth.reset(token)
    return errors
