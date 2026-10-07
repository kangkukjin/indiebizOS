"""Data-selected value checks shared by current IBL inspection and execution."""
from contextvars import ContextVar
from ibl_callable_contract import UNRESOLVED

_depth = ContextVar("ibl_code_check_depth", default=0)


# 선언 `value_validator` → 등록 런타임과 **같은** 판정 함수가 읽는 인자. 이 인자 가운데 하나라도 실행 전에
# 값을 모르면(변수·호출) 판정하지 않는다 — 모르는 값으로 거짓 빨강을 만들지 않는다.
# 관문 scripts/iblbuild_schedule_rules.py 가 이 표와 어휘의 value_validator 선언, 런타임 입구가 같은 함수를
# 부르는지를 대조한다(75회차 후속 B75-4 밭 이관).
VALIDATOR_READS = {
    "trigger": ("op", "type", "cron", "config"),
    "schedule": ("at", "date", "time", "start_time", "minutes", "seconds", "repeat",
                 "weekdays", "month", "day", "interval_hours"),
    "calendar": ("op", "date", "time", "start_time", "repeat", "weekdays", "month", "day", "interval_hours"),
}


def _validator_problem(validator, values):
    reads = VALIDATOR_READS.get(validator)
    if reads is None:
        return f"알 수 없는 value_validator: {validator}"
    if any(values.get(k) is UNRESOLVED for k in reads):
        return None
    known = {k: values[k] for k in reads if k in values}
    op = known.get("op", "create")
    if validator == "trigger":
        if op not in ("create", "watch", "update"):
            return None
        if op == "update" and "cron" not in known and "config" not in known:
            return None  # 규칙을 안 바꾸는 수정 — 저장된 규칙은 등록 때 이미 판정됐다
        from trigger_engine import resolve_trigger_config
        return resolve_trigger_config(known, known.get("type", "schedule")).get("error")
    if validator == "schedule":
        from calendar_rules import schedule_request
        # "이미 지난 시각"은 실행 순간의 사실이라 문장 계약이 아니다(check 는 시각에 따라 뒤집히지 않는다).
        return schedule_request(known, check_past=False).get("error")
    if op not in ("create", "add"):
        return None  # update 는 저장된 이벤트와 합쳐야 판정된다 — 런타임(update_event)이 말한다
    from calendar_rules import calendar_request
    executable = "event_action" in values or "do" in values
    return calendar_request(known, executable=executable, check_past=False).get("error")


def value_problems(contract, values, registry=None, definitions=None):
    known = {k: v for k, v in values.items() if v is not UNRESOLVED}
    errors = []
    for name, nested in contract.get('nested_contracts', {}).items():
        if name not in known:
            continue
        try:
            from ibl_callable_contract import checked_values
            checked_values(nested, known[name])
        except (ValueError, TypeError) as exc:
            errors.append(f'{name}: {exc}')
        except Exception as exc:
            from ibl_v2_ir import Fault
            if not isinstance(exc, Fault):
                raise
            errors.append(f'{name}: {exc}')
    validator = contract.get("value_validator")
    if validator:
        problem = _validator_problem(validator, values)
        if problem:
            errors.append(problem)
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
                # 안쪽 진단의 처방을 함께 싣는다 — 바깥 ARGUMENT_CONTRACT 의 범용 안내("인자 관계를 확인")가
                # 중첩 문장의 고칠 방향을 가리지 않게(72회차 후속).
                from ibl_v2_analysis import HINTS
                errors.extend(f"{name}: {issue['message']} ({issue['code']})"
                              + (f" — {HINTS[issue['code']]}" if issue['code'] in HINTS else "")
                              for issue in plan.issues[:5])
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
