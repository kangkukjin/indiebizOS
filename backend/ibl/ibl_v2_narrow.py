"""Conservative path refinements shared by branches and row predicates."""
from dataclasses import replace

from ibl_v2_types import Type, UNKNOWN, NULL, NEVER, alternatives, join


def path(node):
    if node.kind == "ref":
        return (node.data["name"],)
    if node.kind == "field":
        base = path(node.data["base"])
        return (*base, node.data["key"]) if base else None
    if node.kind == 'pure_call' and node.data['fn'].kind == 'builtin' and node.data['fn'].data['name'] == 'get':
        args = node.data['args']
        if (len(args) in (2, 3) and args[1].kind == 'literal'
                and isinstance(args[1].data['value'], str)
                and (len(args) == 2 or args[2].kind == 'literal' and args[2].data['value'] is None)):
            base = path(args[0])
            return (*base, args[1].data['value']) if base else None
    return None


def combine(types):
    result = types[0]
    for typ in types[1:]:
        result = join(result, typ)
    return result


def refine(typ, keys, test):
    candidates = []
    for member in alternatives(typ):
        if member == NEVER:
            continue
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
    known = known_condition(condition, env)
    if known is not None and known != truth:
        return dict.fromkeys(env, NEVER)
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
    if condition.kind == "pure_call" and d["fn"].kind == "builtin" and d["fn"].data["name"] == "has":
        args = d["args"]
        if len(args) == 2:
            keys = path(args[0])
            if keys and keys[0] in env and truth:
                def can_have_field(typ):
                    return None if typ.kind == "Record" and not typ.open and not typ.fields else typ
                refined = refine(env[keys[0]], keys[1:], can_have_field)
                if refined is None:
                    return {**env, keys[0]: NEVER}
        if len(args) == 2 and args[1].kind == "literal" and isinstance(args[1].data["value"], str):
            keys, key = path(args[0]), args[1].data["value"]
            if keys and keys[0] in env:
                def present(typ):
                    if typ.kind == "Unknown":
                        return Type("Record", fields=((key, UNKNOWN),)) if truth else typ
                    if typ.kind != "Record":
                        return typ
                    fields = dict(typ.fields)
                    if truth:
                        if key not in fields and not typ.open:
                            return None
                        # Existence does not imply non-nullness.
                        fields.setdefault(key, UNKNOWN)
                        return replace(typ, fields=tuple(fields.items()))
                    return None if key in fields else typ
                refined = refine(env[keys[0]], keys[1:], present)
                return {**env, keys[0]: refined if refined is not None else NEVER}
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
    # Preserve the contradiction instead of restoring the pre-guard type.
    # Source validation still runs; only accesses to this impossible value
    # receive bottom, so unrelated mistakes are not hidden.
    result[keys[0]] = refined if refined is not None else NEVER
    return result


def known_condition(node, env):
    """Bounded scalar/shape proof; never evaluates callbacks or tool code.

    Numeric input values are not folded: cardinality and literal comparisons
    suffice to eliminate impossible optional-record paths without specializing
    arbitrary computation or hiding source errors.
    """
    from common.expression_ops import binary, pure_call
    from ibl_callable_contract import UNRESOLVED
    def value(n, depth=0):
        if depth > 32:
            return UNRESOLVED
        d = n.data
        if n.kind == 'literal':
            return d['value']
        if n.kind == 'ref':
            typ = env.get(d['name'], UNKNOWN)
            if typ.kind == 'Null':
                return None
            return typ.literal if typ.kind in ('Text','Bool') and typ.literal is not None else UNRESOLVED
        if n.kind == 'unary' and d['op'] in ('not','!'):
            part = value(d['value'], depth+1)
            return not part if type(part) is bool else UNRESOLVED
        if n.kind == 'binary':
            a, b = value(d['left'],depth+1), value(d['right'],depth+1)
            if d['op'] in ('and','&&') and (a is False or b is False):
                return False
            if d['op'] in ('or','||') and (a is True or b is True):
                return True
            if d['op'] == 'in' and isinstance(b, list) and not b:
                return False
            if a is UNRESOLVED or b is UNRESOLVED:
                return UNRESOLVED
            try:
                return binary(d['op'],a,b)
            except Exception:
                return UNRESOLVED
        if n.kind == 'pure_call' and d['fn'].kind == 'builtin':
            name = d['fn'].data['name']
            args = d['args']
            if len(args) == 1 and name == 'keys' and args[0].kind == 'ref':
                typ = env.get(args[0].data['name'], UNKNOWN)
                if typ.kind == 'Record' and not typ.open and len(typ.fields) <= 64:
                    return [k for k, _ in typ.fields]
            if len(args) == 1 and name == 'len' and args[0].kind == 'ref':
                typ = env.get(args[0].data['name'], UNKNOWN)
                if typ.kind == 'Record' and not typ.open:
                    return len(typ.fields)
                if typ.kind == 'List' and typ.positions is not None:
                    return len(typ.positions)
                if typ.kind == 'Text' and typ.literal is not None:
                    return pure_call('len',[typ.literal])
        return UNRESOLVED
    result=value(node)
    return result if type(result) is bool else None
