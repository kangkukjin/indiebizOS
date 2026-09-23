"""Conservative bridges for declared legacy handler vocabulary.

This does not infer a native v2 return contract. The complete legacy envelope
is a Record and parameter values remain Unknown until the existing handler
validates them. Preflight explicitly reports this weaker boundary.
"""
from ibl_v2_ir import Fault


def plain_arguments(value):
    """An old JSON handler must never receive an interpreter-only object."""
    from ibl_v2_ir import pack
    wire = pack(value)
    def check(item):
        if item[0] in {"unit", "result", "decimal", "integer"}:
            raise Fault("LEGACY_VALUE", "이 값은 기존 JSON 도구 경계를 넘을 수 없습니다. 명시적으로 변환하세요.", kind="protocol")
        if item[0] == "record":
            for _, child in item[1]:
                check(child)
        elif item[0] == "list":
            for child in item[1]:
                check(child)
    check(wire)
    return value


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
        for row in conn.execute("SELECT alias, ibl_code FROM ibl_examples WHERE COALESCE(alias,'') != '' ORDER BY updated_at"):
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
    return assets


def function_adapters(project_path, agent_id):
    from ibl_v2_adapters import Adapter, Adapted, decode_envelope
    from ibl_v2_ir import digest
    from ibl_engine import execute_ibl
    from workflow_contract import call_signature, _signature_of
    assets = legacy_functions()
    snapshot = digest(assets)
    result = {}
    for name, asset in assets.items():
        try:
            wf = asset.get("workflow", {})
            params = (call_signature(asset["code"]) if asset["kind"] == "idiom" else
                      _signature_of(wf.get("steps") or wf.get("do") or wf.get("pipeline")))
            defaults = wf.get("params_default") or {}
            if any(not p.isidentifier() or p.startswith("_") for p in params):
                continue
        except (ValueError, TypeError):
            continue
        contract = {"version": 1, "params": {p: "Unknown" for p in [*params, *defaults]},
                    "required": [p for p in params if p not in defaults],
                    "result": "Record", "effects": ["unknown"],
                    "compatibility": "legacy-function/1", "implementation_fingerprint": snapshot,
                    "adapter": {"protocol": "legacy-envelope", "value_path": ""}}
        def run(runtime, args, *, name=name, contract=contract):
            if digest(legacy_functions()) != snapshot:
                raise Fault("DEFINITION_CHANGED", "컴파일 이후 기존 관용구가 바뀌었습니다. 다시 검사하세요.", kind="protocol")
            raw = execute_ibl({"_node": "fn", "action": name, "params": plain_arguments(args)},
                              project_path, agent_id=agent_id)
            value, evidence = decode_envelope(raw, contract["adapter"])
            evidence["compatibility"] = "legacy-function/1"
            return Adapted(value, evidence)
        result[f"fn:{name}"] = Adapter(contract, run)
    return result
