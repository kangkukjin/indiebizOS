"""Conservative bridges for declared legacy handler vocabulary.

Legacy functions expose their selected return value; execution envelopes stay
in evidence. Unproven return and parameter types remain Unknown.
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

    pack(value)  # Validate keys, nonfinite numbers and supported value shapes first.

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



def forwarding_contract(steps, params, receiver):
    """Recognize only a direct input → explicitly contracted legacy leaf return.

    Dynamic calls, nested control, criteria and extra steps remain unknown.
    Internal spill/evidence files are execution bookkeeping, not world writes.
    No function name or task domain participates in this proof.
    """
    if not isinstance(steps, list) or len(steps) != 2 or not receiver:
        return {}
    emit, call = steps
    if (set(emit) - {"_var_emit", "name", "path", "_free"}
            or not emit.get("_var_emit") or emit.get("name") != receiver or emit.get("path")
            or set(call) - {"_node", "action", "target", "params", "_assign_name"}
            or call.get("target") or call.get("_assign_name") != "return"):
        return {}
    from ibl_registry import load_nodes_installed
    from ibl_v2_adapters import validate_contract
    config = (load_nodes_installed().get("nodes", {}).get(call.get("_node"), {})
              .get("actions", {}).get(call.get("action"), {}))
    leaf = config.get("legacy_callable_contract")
    if not leaf:
        return {}
    try:
        validate_contract(leaf)
    except (ValueError, TypeError):
        return {}
    # Until resource substitution is represented here, prove pure wrappers only.
    if leaf["effects"] != ["pure"]:
        return {}
    arguments = call.get("params") or {}
    if set(arguments) - set(leaf["params"]) or leaf.get("pipe_input") in arguments:
        return {}
    if set(leaf.get("required", [])) - set(arguments) - {leaf.get("pipe_input")}:
        return {}
    inferred = {p: "Unknown" for p in params}
    inferred[receiver] = leaf["params"][leaf["pipe_input"]]

    def infer_argument(value, spec):
        if isinstance(value, str) and value.startswith("$") and value[1:] in inferred:
            inferred[value[1:]] = spec
        elif isinstance(value, dict) and isinstance(spec, dict):
            for key in value.keys() & spec.keys():
                infer_argument(value[key], spec[key])
    for key, value in arguments.items():
        infer_argument(value, leaf["params"][key])
    return {"params": inferred, "effects": leaf["effects"], "result": leaf["result"]}


def decode_function_result(raw):
    """Unwrap only runner-tagged function returns, retaining boundary failures."""
    from common.currency import coerce_json_param, fn_result_payload
    from ibl_v2_adapters import Adapted, decode_envelope
    raw = coerce_json_param(raw)
    selected, value = fn_result_payload(raw, typed=True)
    adapter = {"protocol": "legacy-envelope", "value_path": "",
               "attachments": ["execution_ref", "execution_ref_error"]}
    if selected:
        # Validate status/completeness on the execution envelope, never on the
        # business value (whose error/success/final_result keys are just data).
        raw = {**raw, "_return_value": value}
        adapter["value_path"] = "/_return_value"
    value, evidence = decode_envelope(raw, adapter)
    evidence["compatibility"] = "legacy-function-value/1"
    return Adapted(value, evidence)


def function_adapters(project_path, agent_id):
    from member_runtime import is_member
    if is_member():
        from ibl_member_library import adapters
        return adapters(project_path, agent_id)
    from ibl_v2_adapters import Adapter
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
                    "result": "Unknown", "effects": ["unknown"],
                    "compatibility": "legacy-function-value/1", "implementation_fingerprint": digest([snapshot, implementation]),
                    "adapter": {"protocol": "legacy-envelope", "value_path": "/final_result"}}
        contract.update(forwarding_contract(steps, contract["params"], receiver))
        if receiver in params:
            contract["pipe_input"] = receiver
        def run(runtime, args, *, name=name, contract=contract, snapshot=snapshot, target_node=None):
            if target_node:
                raise Fault("TARGET_NODE", "함수 호출에는 노드 지정을 쓸 수 없습니다.", kind="compile")
            if legacy_snapshot(name, legacy_functions()) != snapshot or legacy_runtime_snapshot() != implementation:
                raise Fault("DEFINITION_CHANGED", "컴파일 이후 기존 관용구가 바뀌었습니다. 다시 검사하세요.", kind="protocol")
            from ibl_edition import source_context
            with source_context(1):
                raw = execute_ibl({"_node": "fn", "action": name, "params": plain_arguments(args)},
                                  project_path, agent_id=agent_id)
            return decode_function_result(raw)
        result[f"fn:{name}"] = Adapter(contract, run)
    return result
