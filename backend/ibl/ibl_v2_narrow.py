"""Conservative path refinements shared by branches and row predicates."""
from dataclasses import replace

from ibl_v2_types import Type, UNKNOWN, NULL, alternatives, join


def path(node):
    if node.kind == "ref":
        return (node.data["name"],)
    if node.kind == "field":
        base = path(node.data["base"])
        return (*base, node.data["key"]) if base else None
    return None


def combine(types):
    result = types[0]
    for typ in types[1:]:
        result = join(result, typ)
    return result


def refine(typ, keys, test):
    candidates = []
    for member in alternatives(typ):
        if not keys:
            value = test(member)
        elif member.kind == "Record":
            fields = dict(member.fields)
            key = keys[0]
            value = refine(fields.get(key, UNKNOWN), keys[1:], test)
            if value is not None:
                fields[key] = value
                value = replace(member, fields=tuple(fields.items()))
        else:
            value = member
        if value is not None:
            candidates.append(value)
    return combine(candidates) if candidates else None


def narrow(env, condition, truth=True):
    """Return a new environment; never change a sibling branch or caller."""
    d = condition.data
    if condition.kind == "unary" and d["op"] in ("not", "!"):
        return narrow(env, d["value"], not truth)
    if condition.kind == "binary" and d["op"] in ("and", "&&", "or", "||"):
        conjunction = d["op"] in ("and", "&&")
        if truth == conjunction:
            return narrow(narrow(env, d["left"], truth), d["right"], truth)
        a = narrow(env, d["left"], truth)
        b = narrow(narrow(env, d["left"], not truth), d["right"], truth)
        return {k: join(a[k], b[k]) for k in env}
    target, literal = condition, truth
    equal = True
    if condition.kind == "binary" and d["op"] in ("==", "!="):
        target, value = d["left"], d["right"]
        if target.kind == "literal":
            target, value = value, target
        if value.kind != "literal" or (value.data["value"] is not None and type(value.data["value"]) is not bool):
            return env.copy()
        literal = value.data["value"]
        equal = truth == (d["op"] == "==")
    keys = path(target)
    if not keys or keys[0] not in env:
        return env.copy()

    def test(typ):
        if literal is None:
            if typ.kind == "Unknown":
                return NULL if equal else typ
            return typ if (typ.kind == "Null") == equal else None
        if typ.kind == "Bool":
            selected = literal if equal else not literal
            return Type("Bool", literal=selected) if typ.literal is None or typ.literal == selected else None
        return typ

    result = env.copy()
    refined = refine(env[keys[0]], keys[1:], test)
    # An impossible branch is still checked with its original types.
    if refined is not None:
        result[keys[0]] = refined
    return result
