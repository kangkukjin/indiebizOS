"""Structural types shared by edition 2 preflight and boundary guards."""
from dataclasses import dataclass
from decimal import Decimal
from ibl_v2_ir import Unit, ResultValue, Fault
from ibl_v2_expr import Builtin, Closure


@dataclass(frozen=True)
class Type:
    kind: str
    fields: tuple = ()
    item: object = None
    open: bool = True

    def __str__(self):
        if self.kind == "Union":
            return " | ".join(str(t) for t in self.item)
        if self.kind == "Record" and self.fields:
            return "{" + ", ".join(f"{k}: {v}" for k, v in self.fields) + "}"
        return f"{self.kind}<{self.item}>" if self.item else self.kind


UNKNOWN, UNIT_T, BOOL = Type("Unknown"), Type("Unit"), Type("Bool")
NUMBER, TEXT, NULL = Type("Number"), Type("Text"), Type("Null")


def alternatives(typ):
    """Leaf alternatives, including older nested union representations."""
    if typ.kind == "Union":
        for member in typ.item:
            yield from alternatives(member)
    else:
        yield typ


def join(left, right):
    if left == right:
        return left
    if left.kind == right.kind == "List":
        return Type("List", item=join(left.item, right.item))
    if left.kind == right.kind == "Record":
        a, b = dict(left.fields), dict(right.fields)
        return Type("Record", tuple((k, join(a[k], b[k])) for k in sorted(a.keys() & b.keys())), open=left.open or right.open)
    if "Unknown" in (left.kind, right.kind):
        return UNKNOWN
    members = set(alternatives(left)) | set(alternatives(right))
    return Type("Union", item=tuple(sorted(members, key=str)))


def infer(value):
    if isinstance(value, Unit):
        return UNIT_T
    if value is None:
        return NULL
    if type(value) is bool:
        return BOOL
    if isinstance(value, (int, float, Decimal)):
        return NUMBER
    if isinstance(value, str):
        return TEXT
    if isinstance(value, list):
        item = infer(value[0]) if value else UNKNOWN
        for v in value[1:]:
            item = join(item, infer(v))
        return Type("List", item=item)
    if isinstance(value, dict):
        return Type("Record", tuple((k, infer(v)) for k, v in value.items()), open=False)
    if isinstance(value, (Builtin, Closure)):
        return Type("Callable")
    if isinstance(value, ResultValue):
        return Type("Result", item=infer(value.value) if value.ok else UNKNOWN)
    return UNKNOWN


def declared(spec):
    if isinstance(spec, dict) and set(spec) == {"$list"}:
        return Type("List", item=declared(spec["$list"]))
    if isinstance(spec, dict):
        return Type("Record", tuple((k, declared(v)) for k, v in spec.items()))
    if not isinstance(spec, str):
        raise ValueError("타입 선언은 문자열 또는 Record입니다.")
    if spec.endswith("?"):
        return join(declared(spec[:-1]), NULL)
    for kind in ("List", "Result"):
        if spec.startswith(kind + "<") and spec.endswith(">"):
            return Type(kind, item=declared(spec[len(kind) + 1:-1]))
    if "|" in spec:
        values = [declared(s.strip()) for s in spec.split("|")]
        result = values[0]
        for value in values[1:]:
            result = join(result, value)
        return result
    if spec not in {"Unknown", "Unit", "Bool", "Number", "Text", "Null", "List", "Record", "Callable", "Result"}:
        raise ValueError(f"알 수 없는 타입: {spec}")
    return Type(spec, item=UNKNOWN if spec == "List" else None)


def compatible(actual, expected):
    if "Unknown" in (actual.kind, expected.kind):
        return True
    if actual.kind == "Union":
        return all(compatible(t, expected) for t in actual.item)
    if expected.kind == "Union":
        return any(compatible(actual, t) for t in expected.item)
    if actual.kind != expected.kind:
        return False
    if expected.kind in ("List", "Result"):
        return compatible(actual.item or UNKNOWN, expected.item or UNKNOWN)
    if expected.kind == "Record":
        fields = dict(actual.fields)
        return all(k in fields and compatible(fields[k], v) for k, v in expected.fields)
    return True


def guard(value, spec, label):
    expected = declared(spec)
    if not compatible(infer(value), expected):
        raise Fault("TYPE_CONTRACT", f"{label}: {expected}가 필요하지만 {infer(value)}입니다.")
    return value
