"""Compiler-backed entry checks for edition 2 reusable memory."""
from ibl_edition import source_edition
from ibl_v2_ir import Fault
from ibl_v2_parser import parse


def check_source(source, function_body=False, *, registry=None, library=None, owned_vocabulary=False):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_store import definitions, definition_name
    try:
        source_edition(source, 2)
        if function_body:
            definition_name(source)
        if registry is None:
            registry = _owned_registry() if owned_vocabulary else load_registry()
        plan = compile_program(source, registry,
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
    from capability_history import record_function_call
    from member_runtime import is_member
    if is_member():
        return
    entries = plan.dependencies.get("source_map", [])[1:]
    events = {e["id"]: e for e in result.get("evidence", [])}
    for event in events.values():
        if event.get("kind") != "function_result":
            continue
        ref = event.get('function_ref')
        if ref is not None and ref not in plan.dependencies.get('function_refs', []):
            continue
        if ref is None:
            entry = next((s for s in entries if s["start"] <= event["definition_start"] < s["end"]), None)
            ref = (entry or {}).get('function_ref')
        if ref:
            # Interface-only plans have no lower source coordinates. Attribute
            # the runtime's exact pinned identity rather than reopening a body.
            event['function_ref'] = ref
            run_id = (result.get('task_ref') or {}).get('task_id') or (result.get('resume') or {}).get('run_id')
            if run_id:
                pending, seen = [event['id']], set()
                while pending:
                    eid = pending.pop()
                    if eid in seen:
                        continue
                    seen.add(eid)
                    pending.extend(events.get(eid, {}).get('parents', []))
                complete = not any(events.get(eid, {}).get('incomplete') for eid in seen)
                record_function_call(ref, run_id, event['id'], success=event['success'],
                                     dependency_revision=plan.fingerprint, source_complete=complete,
                                     observed={'keys': event.get('returns_keys', []),
                                               'kind': event.get('returns_kind')})


def _owned_registry():
    """Compile imported examples without waking packages or granting execution."""
    import json
    from ibl_registry import load_nodes_owned
    from vocabulary_state import inventory
    from ibl_v2_adapters import Adapter, load_registry, validate_contract
    from ibl_v2_contracts import declared_contract, handler_contract
    registry = load_registry()
    schemas = {}
    for package in inventory()["packages"].values():
        path = package["path"] / "tool.json"
        if not path.is_file():
            continue
        schema = json.loads(path.read_text())
        entries = schema if isinstance(schema, list) else schema.get("tools", [schema])
        for entry in entries:
            schemas[entry.get("name")] = (entry.get("input_schema") or {}).get("properties", {})

    def inspection_only(*args, **kwargs):
        raise Fault("INSPECTION_ONLY", "보유 어휘 검사용 계약은 실행할 수 없습니다.", kind="permission")

    for node, group in load_nodes_owned().get("nodes", {}).items():
        for action, config in group.get("actions", {}).items():
            key = f"{node}:{action}"
            if key in registry:
                continue
            contract = declared_contract(config) or handler_contract(
                node, action, config, schemas.get(config.get("tool")))
            if contract:
                registry[key] = Adapter(validate_contract(contract), inspection_only)
    return registry


def call_sites(source):
    return [node for node in walk_nodes(parse(source)) if node.kind == 'call']


def call_parameters(node):
    from common.expression_ir import record_fields
    from ibl_v2_analysis import constant_value
    return {key: constant_value(value) for key, value in record_fields(node.data['params']).items()}

from common.expression_ir import Node

def walk_nodes(value):
    """Visit syntax nodes in source order without evaluating expressions."""
    if isinstance(value, Node):
        yield value
        yield from walk_nodes(value.data)
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk_nodes(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from walk_nodes(child)
