"""JSON handler value projection. This module contains no language compatibility runtime.
"""
from ibl_v2_ir import Fault


def plain_arguments(value):
    """Project exact decimals only when their JSON numeric spelling round-trips.

    Interpreter-only values and numbers losing precision still require an explicit
    conversion. This returns a new tree; receipts retain the original typed args.
    """
    from decimal import Decimal
    from common.value_semantics import decimal_json_number
    from ibl_v2_ir import pack

    try:
        pack(value)  # Validate keys, nonfinite numbers and supported value shapes first.
    except Fault as error:
        # A callback in a JSON-only argument is a caller error, not a broken
        # wire protocol. Inspect only the rejected tree; successful calls pay
        # no extra traversal and native callback adapters never use this bridge.
        from ibl_v2_expr import Builtin, Closure

        def callable_path(item, path):
            if isinstance(item, (Builtin, Closure)):
                return path
            children = (item.items() if isinstance(item, dict) else
                        enumerate(item) if isinstance(item, (list, tuple)) else ())
            for key, child in children:
                suffix = f".{key}" if isinstance(item, dict) else f"[{key}]"
                found = callable_path(child, path + suffix)
                if found:
                    return found
            return None

        path = callable_path(value, '$args') if error.code == 'VALUE_PROTOCOL' else None
        if path:
            raise Fault('ARGUMENT_CONTRACT',
                        f'{path}: 이 도구 인자는 JSON 값만 받으며 콜백을 지원하지 않습니다. '
                        'describe로 인자 계약을 확인하고 함수를 적용한 결과 값을 전달하세요.',
                        details={'path': path, 'actual': 'Callable', 'expected': 'JSON value'}) from error
        raise

    def convert(item, path):
        if isinstance(item, Decimal):
            try:
                return decimal_json_number(item)
            except ValueError as error:
                raise Fault("LEGACY_VALUE", f"{path}: {error}", kind="protocol",
                            details={"path": path, "reason": "numeric_precision"}) from error
        if isinstance(item, dict):
            return {key: convert(child, f"{path}.{key}") for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(child, f"{path}[{i}]") for i, child in enumerate(item)]
        if pack(item)[0] in {"unit", "result", "integer"}:
            raise Fault("LEGACY_VALUE", f"{path}: 이 값은 기존 JSON 도구 경계를 넘을 수 없습니다. 명시적으로 변환하세요.",
                        kind="protocol", details={"path": path})
        return item

    return convert(value, "$args")
