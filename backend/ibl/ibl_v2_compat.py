"""Conservative bridges for declared legacy handler vocabulary.

This does not infer a native v2 return contract. The complete legacy envelope
is a Record and parameter values remain Unknown until the existing handler
validates them. Preflight explicitly reports this weaker boundary.
"""
from ibl_v2_ir import Fault


def plain_arguments(value):
    """Project exact decimals only when their JSON numeric spelling round-trips.

    Interpreter-only values and numbers losing precision still require an explicit
    conversion. This returns a new tree; receipts retain the original typed args.
    """
    import math
    from decimal import Decimal
    from ibl_v2_ir import pack

    pack(value)  # Validate keys, nonfinite numbers and supported value shapes first.

    def convert(item, path):
        if isinstance(item, Decimal):
            number = float(item)  # vj-ok: JSON numeric transport, not value comparison
            if item.is_finite() and math.isfinite(number) and Decimal(str(number)) == item:
                return number
            raise Fault("LEGACY_VALUE", f"{path}: JSON 숫자로 전달하면 정밀도를 잃습니다. text()로 명시적으로 변환하세요.",
                        kind="protocol", details={"path": path, "reason": "numeric_precision"})
        if isinstance(item, dict):
            return {key: convert(child, f"{path}.{key}") for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(child, f"{path}[{i}]") for i, child in enumerate(item)]
        if pack(item)[0] in {"unit", "result", "integer"}:
            raise Fault("LEGACY_VALUE", f"{path}: 이 값은 기존 JSON 도구 경계를 넘을 수 없습니다. 명시적으로 변환하세요.",
                        kind="protocol", details={"path": path})
        return item

    return convert(value, "$args")


def legacy_functions():
    """Read existing callable assets without rewriting bodies or histories."""
    from member_runtime import is_member
    if is_member():
        return {}
    from ibl_usage_db import IBLUsageDB
    from ibl_edition import source_edition
    from workflow_store import _get_workflows_path
    import yaml
    assets = {}
    with IBLUsageDB()._get_connection() as conn:
        for row in conn.execute("SELECT alias, ibl_code FROM ibl_examples WHERE COALESCE(alias,'') != '' ORDER BY updated_at, id"):
            if source_edition(row["ibl_code"]) == 1:
                assets[row["alias"]] = {"code": row["ibl_code"], "kind": "idiom"}
    for path in sorted(_get_workflows_path().glob("*.yaml")):
        if path.is_symlink():
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and data.get("edition", 1) == 1:
            assets[path.stem] = {"workflow": data, "kind": "workflow"}
    return dict(sorted(assets.items()))


def function_adapters(project_path, agent_id):
    from member_runtime import is_member
    if is_member():
        from ibl_member_library import adapters
        return adapters(project_path, agent_id)
    from ibl_v2_adapters import Adapter, Adapted, decode_envelope
    from ibl_v2_ir import digest
    from ibl_engine import execute_ibl
    from workflow_contract import (
        call_signature, _signature_of, normalize_steps_for_injection, pipe_input_param,
    )
    from ibl_parser import parse_function_body
    assets = legacy_functions()
    from ibl_dependencies import legacy_snapshot, legacy_runtime_snapshot
    implementation = legacy_runtime_snapshot()
    result = {}
    for name, asset in assets.items():
        snapshot = legacy_snapshot(name, assets)
        try:
            wf = asset.get("workflow", {})
            params = (call_signature(asset["code"]) if asset["kind"] == "idiom" else
                      _signature_of(wf.get("steps") or wf.get("do") or wf.get("pipeline")))
            defaults = wf.get("params_default") or {}
            body = asset.get("code") if asset["kind"] == "idiom" else (
                wf.get("steps") or wf.get("do") or wf.get("pipeline"))
            steps, error = ((parse_function_body(body), None) if asset["kind"] == "idiom"
                            else normalize_steps_for_injection(body))
            receiver = pipe_input_param(steps) if not error else None
            if any(not p.isidentifier() or p.startswith("_") for p in params):
                continue
        except (ValueError, TypeError):
            continue
        contract = {"version": 1, "params": {p: "Unknown" for p in [*params, *defaults]},
                    "required": [p for p in params if p not in defaults],
                    "result": "Record", "effects": ["unknown"],
                    "compatibility": "legacy-function/1", "implementation_fingerprint": digest([snapshot, implementation]),
                    "adapter": {"protocol": "legacy-envelope", "value_path": ""}}
        if receiver in params:
            contract["pipe_input"] = receiver
        def run(runtime, args, *, name=name, contract=contract, snapshot=snapshot):
            if legacy_snapshot(name, legacy_functions()) != snapshot or legacy_runtime_snapshot() != implementation:
                raise Fault("DEFINITION_CHANGED", "컴파일 이후 기존 관용구가 바뀌었습니다. 다시 검사하세요.", kind="protocol")
            from ibl_edition import source_context
            with source_context(1):
                raw = execute_ibl({"_node": "fn", "action": name, "params": plain_arguments(args)},
                                  project_path, agent_id=agent_id)
            value, evidence = decode_envelope(raw, contract["adapter"])
            evidence["compatibility"] = "legacy-function/1"
            return Adapted(value, evidence)
        result[f"fn:{name}"] = Adapter(contract, run)
    return result
