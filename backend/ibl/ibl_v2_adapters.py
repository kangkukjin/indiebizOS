"""Declared vocabulary adapters. Action names never drive language semantics.

Catalog contracts select an adapter protocol. Existing leaf routing still owns
permissions, actor context, file protection, receipts and package dispatch.
"""
from dataclasses import dataclass
from pathlib import Path
import copy
import json
from ibl_v2_ir import Fault, UNIT, digest
from ibl_v2_types import guard, declared
from ibl_v2_expr import boolean


@dataclass(frozen=True)
class Adapter:
    contract: dict
    run: object
    authorize: object = None
    dependency: object = None


@dataclass(frozen=True)
class Adapted:
    value: object
    evidence: dict


def validate_contract(contract):
    if not isinstance(contract, dict) or contract.get("version") != 1:
        raise ValueError("callable_contract.version은 1이어야 합니다.")
    if not isinstance(contract.get("params"), dict):
        raise ValueError("callable_contract.params가 필요합니다.")
    for spec in contract["params"].values():
        declared(spec)
    declared(contract["result"])
    effects = contract.get("effects")
    if not isinstance(effects, list) or not effects or not set(effects) <= {"pure", "read_external", "write_external", "model", "unknown"}:
        raise ValueError("올바른 effects가 필요합니다.")
    if "pure" in effects and len(effects) != 1:
        raise ValueError("pure는 다른 효과와 함께 선언할 수 없습니다.")
    if contract.get("pipe_input") and contract["pipe_input"] not in contract["params"]:
        raise ValueError("pipe_input은 선언된 인자여야 합니다.")
    if not set(contract.get("required", contract["params"])) <= contract["params"].keys():
        raise ValueError("required는 params에 포함되어야 합니다.")
    writes = contract.get("write_resources", {})
    if not isinstance(writes, dict) or any(v not in contract["params"] for v in writes.values()):
        raise ValueError("write_resources는 자원 종류→선언 인자 이름입니다.")
    adapter = contract.get("adapter", {})
    if adapter.get("protocol") not in {"core-table/2", "legacy-envelope", "ibl-script/2", "document-value/1"}:
        raise ValueError("지원하지 않는 어댑터 프로토콜입니다.")
    from ibl_callable_contract import validate_extensions
    validate_extensions(contract)
    return contract


def table_operation(operation, runtime, args):
    from ibl_v2_runtime import Binding
    from common.value_semantics import sort_records
    rows = args["items"]
    if operation == "filter":
        return [row for row in rows if boolean(runtime.callback(args["where"], [Binding(row)]).value)]
    if operation == "select":
        columns = args["columns"]
        if isinstance(columns, list):
            for row in rows:
                if not isinstance(row, dict) or any(k not in row for k in columns):
                    raise Fault("MISSING_FIELD", "select의 열이 입력 행에 없습니다.")
            return [{k: row[k] for k in columns} for row in rows]
        return [guard(runtime.callback(columns, [Binding(row)]).value, "Record", "select 콜백") for row in rows]
    if operation == "take":
        if type(args["n"]) is not int or args["n"] < 0:
            raise Fault("TAKE_COUNT", "take.n은 0 이상의 정수입니다.")
        return rows[:args["n"]]
    if operation == "sort":
        return sort_records(rows, args["by"], descending=args.get("descending", False))
    if operation == "compute":
        return [{**row, **guard(runtime.callback(args["set"], [Binding(row)]).value, "Record", "compute.set")}
                for row in rows]
    raise Fault("ADAPTER", f"지원하지 않는 표 어댑터: {operation}", kind="protocol")


def pointer(value, path):
    if not path:
        return value
    for key in path.removeprefix("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or key not in value:
            raise Fault("ADAPTER_SHAPE", f"선언된 반환 경로가 없습니다: {path}")
        value = value[key]
    return value


def decode_envelope(raw, adapter):
    from ibl_honesty import completion_evidence, truncation_evidence, markers_of
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            prefix = adapter.get("text_success_prefix")
            if prefix and raw.startswith(prefix):
                raw = {"success": True, "message": raw}
            elif any(raw.startswith(p) for p in adapter.get("text_error_prefixes", [])):
                raise Fault("TOOL", raw) from exc
            else:
                raise Fault("ADAPTER_SHAPE", f"선언된 JSON 실행 봉투가 아닙니다: {raw[:1000]}") from exc
    if not isinstance(raw, dict):
        raise Fault("ADAPTER_SHAPE", "선언된 Record 실행 봉투가 아닙니다.")
    # Only this explicitly declared legacy envelope has error/status meaning.
    if raw.get("success") is False or raw.get("error"):
        kind = "permission" if raw.get("blocked") or raw.get("denied") or raw.get("permission_denied") or raw.get("error_type") == "permission" else "runtime"
        if raw.get("error_type") in {"capability", "result_unknown"}:
            kind = "protocol"
        raise Fault("TOOL", str(raw.get("error") or raw.get("message") or "도구 실행 실패"), kind=kind)
    if adapter.get("protocol") == "document-value/1":
        from ibl_document_value import document_value
        raw = {**raw, "value": document_value(raw)}
        if (raw.get("metadata") or {}).get("truncated"):
            raw["truncated"] = True
    fields = adapter.get("value_fields")
    value = ({k: pointer(raw, p) for k, p in fields.items()} if fields is not None
             else pointer(raw, adapter.get("value_path", "")))
    incomplete = completion_evidence(raw)
    truncation = truncation_evidence(raw)
    markers = markers_of(raw)
    if incomplete or any(t.get("scope") != "selection" for t in truncation.get("truncations", [])) or raw.get("rows_dropped"):
        raise Fault("PARTIAL_SOURCE", "도구의 원천 결과가 불완전합니다.", kind="partial", partial=value,
                    details={"completion": incomplete, "truncation": truncation, "markers": markers})
    return value, {"markers": markers, "attachments": {k: raw[k] for k in adapter.get("attachments", []) if k in raw}}


def load_registry(project_path=".", agent_id=None):
    from ibl_registry import load_nodes_installed
    from ibl_engine import execute_ibl
    from thread_context import get_allowed_nodes
    from ibl_access import check_node_access
    catalog = copy.deepcopy(load_nodes_installed())
    from tool_loader import build_tool_package_map, package_path
    package_map = build_tool_package_map()
    package_roots = {name: package_path(name) for name in set(package_map.values())}
    schemas = {}
    for root in package_roots.values():
        schema = json.loads((root / "tool.json").read_text())
        for tool in schema.get("tools", [schema]):
            schemas[tool.get("name")] = set((tool.get("input_schema") or {}).get("properties", {}))
    allowed = get_allowed_nodes()
    result, file_hashes = {}, {}
    from ibl_v2_contracts import handler_contract
    from ibl_v2_compat import plain_arguments
    for node, config in catalog.get("nodes", {}).items():
        for action, action_config in config.get("actions", {}).items():
            contract = action_config.get("callable_contract") or handler_contract(node, action, action_config, schemas.get(action_config.get("tool")))
            if not contract or (allowed is not None and not check_node_access(node, allowed)):
                continue
            contract = copy.deepcopy(validate_contract(contract))
            contract["analysis"] = {"ai_call": action_config.get("ai_call") is True,
                                    "ai_inspect_param": action_config.get("ai_inspect_param")}
            adapter = contract["adapter"]
            key = f"{node}:{action}"
            # Capture contract and implementation identities now. A changed
            # catalog/package is refused, never silently rebound mid-program.
            implementation = action_config.get("tool", "")
            package_paths = []
            if implementation:
                package = package_map.get(implementation)
                if package:
                    package_paths = sorted(p for p in package_roots[package].rglob("*.py") if "__pycache__" not in p.parts)
            for p in package_paths:
                if str(p) not in file_hashes:
                    file_hashes[str(p)] = digest(p.read_text())
            files = {str(p): file_hashes[str(p)] for p in package_paths}
            contract["implementation_fingerprint"] = digest(files)
            def run(runtime, args, *, node=node, action=action, c=contract,
                    ac=action_config, files=files, allowed=allowed):
                if allowed is not None and not check_node_access(node, allowed):
                    raise Fault("NODE_ACCESS", f"허용되지 않은 노드: {node}", kind="permission")
                current = load_nodes_installed().get("nodes", {}).get(node, {}).get("actions", {}).get(action)
                if current != ac or any(not Path(p).is_file() or digest(Path(p).read_text()) != h for p, h in files.items()):
                    raise Fault("DEFINITION_CHANGED", "컴파일 이후 어휘 구현이 바뀌었습니다. 새 계획으로 검사하세요.", kind="protocol")
                protocol = c["adapter"]["protocol"]
                if protocol == "core-table/2":
                    from member_profile import gate
                    if gate(node, action, ac):
                        raise Fault("MEMBER_ACCESS", "회원의 어휘 권한이 없습니다.", kind="permission")
                    return table_operation(c["adapter"]["operation"], runtime, args)
                plain_arguments(args)
                params = {**args, **c["adapter"].get("fixed_params", {})}
                if protocol == "ibl-script/2":
                    params.setdefault("op", "run" if params.get("id") else "list")
                    params["_ibl_edition"] = 2
                raw = execute_ibl({"_node": node, "action": action, "params": params}, project_path, agent_id=agent_id)
                boundary = c["adapter"]
                if protocol == "ibl-script/2" and params["op"] != "run":
                    boundary = {**boundary, "value_path": ""}
                value, evidence = decode_envelope(raw, boundary)
                return Adapted(value, evidence)
            def authorize(node=node, action=action, ac=action_config):
                from member_profile import visible
                current_allowed = get_allowed_nodes()
                if (current_allowed is not None and not check_node_access(node, current_allowed)) or not visible(node, action, ac):
                    raise Fault("RECEIPT_ACCESS", "현재 권한으로 이 호출의 영수증을 사용할 수 없습니다.", kind="permission")
            from ibl_dependencies import script_snapshot
            result[key] = Adapter(contract, run, authorize,
                                  script_snapshot if adapter['protocol'] == 'ibl-script/2' else None)
    from ibl_v2_compat import function_adapters
    result.update(function_adapters(project_path, agent_id))
    return result
