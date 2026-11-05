"""Normalize observed execution failures without repeating effects."""
import json


def ibl_error_render_repair_key(name, payload):
    """Recognize error-object formatting repairs in the final projection only.

    The acquisition program, input values, branch conditions and tool arguments
    remain exact. A successful rendering does not resolve a different source
    failure. Never normalize formatting used to choose or invoke an operation.
    """
    if not str(name).endswith("execute_ibl") or not payload.get("code"):
        return None
    from ibl_v2_parser import parse
    from ibl_v2_ir import Node, pack, Fault
    from model_result_view import resolve_input_refs
    from supervision_store import digest

    def exact(value):
        if isinstance(value, Node):
            return [value.kind, exact(value.data)]
        if isinstance(value, dict):
            return {k: exact(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [exact(v) for v in value]
        return pack(value)

    def builtin(value, names):
        return (isinstance(value, Node) and value.kind == "pure_call"
                and value.data["fn"].kind == "builtin"
                and value.data["fn"].data["name"] in names
                and len(value.data["args"]) == 1)

    found = False

    def projection(value):
        nonlocal found
        if not isinstance(value, Node):
            return exact(value)
        base = value
        if value.kind == "slice":
            lower, upper = value.data["lower"], value.data["upper"]
            if (lower is not None and lower.kind == "literal" and lower.data["value"] == 0
                    and upper is not None and upper.kind == "literal"
                    and type(upper.data["value"]) is int and upper.data["value"] > 0
                    and value.data["stride"] is None):
                base = value.data["base"]
        if builtin(base, {"text", "json"}) and builtin(base.data["args"][0], {"error_of"}):
            found = True
            return ["error_render", exact(base.data["args"][0])]
        if value.kind == "record":
            return ["record", {k: projection(v) for k, v in value.data["fields"].items()}]
        if value.kind == "conditional":
            return ["conditional", exact(value.data["condition"]),
                    projection(value.data["yes"]), projection(value.data["no"])]
        if value.kind == "pipe" and value.data["op"] == ">>":
            call = value.data["right"]
            if (call.kind == "call" and call.data["node"] == "table"
                    and call.data["action"] == "each" and call.data.get("body") is not None
                    and call.data["params"].data.get("fields") == {}):
                statements = call.data["body"].data["statements"]
                if len(statements) == 1 and statements[0].kind == "return":
                    return ["project_each", exact(value.data["left"]),
                            projection(statements[0].data["value"])]
        return exact(value)

    try:
        statements = parse(payload["code"]).data["statements"]
        if not statements or statements[-1].kind != "return":
            return None
        inputs, _ = resolve_input_refs(payload.get("inputs", {}))
        result = projection(statements[-1].data["value"])
        if found:
            return digest(json.dumps(["error_render", exact(statements[:-1]), result, pack(inputs)],
                                     sort_keys=True, ensure_ascii=False))
    except (Fault, ValueError, TypeError, KeyError, OSError, RecursionError):
        pass
    return None


def ibl_shape_repair_key(name, payload):
    """Match straight-line projection repairs, retaining calls, inputs and order.

    Binding a call before projecting its result is equivalent to projecting it
    in the binding. Evidence IDs may differ while their immutable values agree.
    Control flow, changed source arguments and unresolved inputs never match.
    """
    if not str(name).endswith("execute_ibl") or not payload.get("code"):
        return None
    from ibl_v2_parser import parse
    from ibl_v2_ir import Node, pack, Fault
    from model_result_view import resolve_input_refs
    from supervision_store import digest

    bindings, calls = {}, []

    def canonical(value, projections=True):
        if isinstance(value, Node):
            if value.kind == "ref" and value.data["name"] in bindings:
                return canonical(bindings[value.data["name"]], projections)
            # Only the row-envelope projection is a shape repair. Different
            # business fields (left/right, gross/net, etc.) remain distinct.
            if value.kind == "field" and projections and value.data["key"] == "items":
                return canonical(value.data["base"], projections)
            return [value.kind, {k: canonical(v, projections and value.kind != "call")
                                 for k, v in value.data.items()}]
        if isinstance(value, dict):
            return {k: canonical(v, projections) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [canonical(v, projections) for v in value]
        return pack(value)

    def visit(value):
        if isinstance(value, Node):
            if value.kind not in {"field", "ref", "literal", "record", "list", "pipe", "parallel", "call"}:
                raise ValueError("not a straight-line projection repair")
            if value.kind == "call":
                if value.data.get("body") is not None:
                    raise ValueError("control body")
                # Arguments are exact, including callbacks and their projections.
                calls.append(canonical(value))
                return
            if value.kind == "pipe":
                if value.data.get("op") != ">>":
                    raise ValueError("conditional execution")
                visit(value.data["left"])
                visit(value.data["right"])
                calls.append(["pipe_input", canonical(value.data["left"]), canonical(value.data["right"])])
                return
            if value.kind == "parallel":
                # Combining already acquired values is safe; do not flatten
                # concurrent calls into a misleading sequential fingerprint.
                def has_call(v):
                    if isinstance(v, Node):
                        return v.kind == "call" or has_call(v.data)
                    if isinstance(v, dict):
                        return any(has_call(x) for x in v.values())
                    if isinstance(v, (list, tuple)):
                        return any(has_call(x) for x in v)
                    return False
                if has_call(value):
                    raise ValueError("parallel calls")
            visit(value.data)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    try:
        program = parse(payload["code"])
        inputs, _ = resolve_input_refs(payload.get("inputs", {}))
        result = None
        expressions = []
        for statement in program.data["statements"]:
            if statement.kind == "bind":
                key = statement.data["name"]
                if key in bindings or key in inputs:
                    return None
                value = statement.data["value"]
                visit(value)
                bindings[key] = value
                result = canonical(value)
            else:
                value = statement.data["value"] if statement.kind == "return" else statement
                visit(value)
                result = canonical(value)
                expressions.append(result)
                if statement.kind == "return":
                    break
        # A bound final value and an explicit return have the same completion.
        if not expressions or expressions[-1] != result:
            expressions.append(result)
        key = [calls, expressions, pack(inputs)]
        return digest(json.dumps(key, sort_keys=True, ensure_ascii=False))
    except (Fault, ValueError, TypeError, KeyError, OSError, RecursionError):
        return None


def missing_read_observation(name, payload, result):
    """순수 파일 조회의 ENOENT만 탐색 결과로 취급한다. 쓰기·권한·네트워크 실패는 제외."""
    if (not str(name or "").endswith("execute_ibl") or not isinstance(payload, dict)
            or not isinstance(payload.get("code"), str)):
        return False
    from ibl_v2_parser import parse
    from common.expression_ir import Node

    def reads_only(node):
        if not isinstance(node, Node):
            return False
        if node.kind == 'parallel':
            return reads_only(node.data['left']) and reads_only(node.data['right'])
        if node.kind in ('return', 'expr'):
            return reads_only(node.data['value'])
        if node.kind != 'call' or (node.data['node'], node.data['action']) != ('self', 'read'):
            return False
        from ibl_v2_learning import walk_nodes
        return not any(n.kind in ('call', 'invoke') for n in walk_nodes(node.data['params']))

    try:
        program = parse(payload['code']).data['statements']
        if not program or not all(reads_only(n) for n in program):
            return False
    except Exception:
        return False

    def errors(value):
        if isinstance(value, str):
            try:
                return errors(json.loads(value))
            except (ValueError, TypeError):
                from common.currency import is_plain_failure
                return [value] if is_plain_failure(value) else []
        if isinstance(value, list):
            return [e for item in value for e in errors(item)]
        if isinstance(value, dict):
            found = [str(value["error"])] if value.get("error") else []
            for key in ("results", "result", "branches"):
                if key in value:
                    found.extend(errors(value[key]))
            return found
        return []

    failures = errors(result)
    return bool(failures) and all("[Errno 2]" in e and "No such file or directory" in e
                                  and "[Errno 13]" not in e for e in failures)
