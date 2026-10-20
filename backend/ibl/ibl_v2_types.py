"""Structural types shared by edition 2 preflight and boundary guards."""
from common.foreign_ref import ForeignRef
from dataclasses import dataclass
from functools import cached_property, lru_cache
import hashlib
from decimal import Decimal
from ibl_v2_ir import Unit, ResultValue, Fault
from ibl_v2_expr import Builtin, Closure


@dataclass(frozen=True, eq=False, repr=False)
class Type:
    kind: str
    fields: tuple = ()
    item: object = None
    open: bool = True
    # Optional refinement of an existing List, not a new value/wire type.
    # None means unknown length/order; () is a known empty list.
    positions: tuple | None = None
    # Observed (not declared) field names of an open Record: fixture/usage
    # traces from data/ibl_return_shapes.json. Access outside them is a
    # compile warning, never an error; join drops the marker.
    observed: bool = False
    # Optional refinement of Text/Bool: the value is known at compile time (literal,
    # a variable bound to one, a default, a specialized argument, a static
    # f-string). Not a new type — display, fingerprints and compatibility are
    # unchanged, and join drops it. Consumers that need a statically known
    # identity (declared write resources) read it via static_text (70회차 B70-2).
    literal: object = None

    @cached_property
    def _key(self):
        # A List shares its children with both item and positions. Expanding
        # repr/hash recursively turns a small DAG into an exponential tree.
        def ref(value):
            if isinstance(value, Type):
                return value._key
            if isinstance(value, tuple):
                return tuple(ref(v) for v in value)
            return value
        value = (self.kind, ref(self.fields), ref(self.item), self.open,
                 ref(self.positions), self.observed, self.literal)
        return hashlib.sha256(repr(value).encode()).digest()

    def __hash__(self):
        return hash(self._key)

    def __eq__(self, other):
        if not isinstance(other, Type):
            return NotImplemented
        # Fingerprints are a fast rejection/order key, never equality proof.
        pending, seen = [(self, other)], set()
        while pending:
            left, right = pending.pop()
            if left is right:
                continue
            pair = (id(left), id(right))
            if pair in seen:
                continue
            seen.add(pair)
            if isinstance(left, Type) and isinstance(right, Type):
                if left._key != right._key:
                    return False
                pending.extend(zip(
                    (left.kind, left.fields, left.item, left.open, left.positions, left.observed, left.literal),
                    (right.kind, right.fields, right.item, right.open, right.positions, right.observed, right.literal)))
            elif isinstance(left, tuple) and isinstance(right, tuple):
                if len(left) != len(right):
                    return False
                pending.extend(zip(left, right))
            elif left != right:
                return False
        return True

    def __str__(self):
        # Diagnostics need a bounded view; the complete refinements stay on
        # the type and are still checked. Never use this display for ordering.
        budget = [2048, 256]
        def show(typ, depth=0):
            if budget[0] <= 0 or budget[1] <= 0 or depth > 32:
                return "…"
            budget[1] -= 1
            def text(value):
                part = value[:max(0, budget[0])]
                budget[0] -= len(part)
                return part + ("…" if len(part) < len(value) else "")
            def parts(values, separator):
                out = []
                for value in values:
                    if out:
                        out.append(text(separator))
                    if budget[0] <= 0 or budget[1] <= 0:
                        out.append("…")
                        break
                    out.append(value())
                return "".join(out)
            if typ.kind == "Union":
                return parts((lambda t=t: show(t, depth + 1) for t in typ.item), " | ")
            if typ.kind == "Record" and typ.observed:
                return text("Record⟨관측: " + "·".join(k for k, _ in typ.fields) + "⟩")
            if typ.kind == "Record" and typ.fields:
                return text("{") + parts(
                    (lambda k=k, v=v: text(k + ": ") + show(v, depth + 1) for k, v in typ.fields),
                    ", ") + text("}")
            if isinstance(typ.item, Type):
                return text(typ.kind + "<") + show(typ.item, depth + 1) + text(">")
            return text(typ.kind)
        return show(self)

    def __repr__(self):
        return f"Type({self!s})"


UNKNOWN, UNIT_T, BOOL = Type("Unknown"), Type("Unit"), Type("Bool")
NUMBER, TEXT, NULL = Type("Number"), Type("Text"), Type("Null")
# Internal bottom: a refinement proved that no value can reach this path.
# This is neither Unknown nor a runtime/declarable value type.
NEVER = Type("Never")


def rows_type(typ):
    """행 목록이 필요한 자리에서 레코드 봉투({items:[…]})는 그 행 목록으로 읽는다(값 쪽은 rows_value)."""
    if typ.kind == "Record":
        items = dict(typ.fields).get("items")
        if items is not None and items.kind == "List":
            return items
    return typ


def rows_value(value):
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        return value["items"]
    return value


def alternatives(typ):
    """Leaf alternatives, including older nested union representations."""
    if typ.kind == "Union":
        for member in typ.item:
            yield from alternatives(member)
    else:
        yield typ


def static_text(typ):
    """The compile-time Text value, or None when it depends on execution."""
    if typ is not None and typ.kind == "Text" and isinstance(typ.literal, str):
        return typ.literal
    return None


@lru_cache(maxsize=8192)
def plain(typ):
    """The same type without compile-time literal values, at every depth."""
    if not isinstance(typ, Type):
        return typ
    item = tuple(plain(t) for t in typ.item) if isinstance(typ.item, tuple) else plain(typ.item)
    positions = None if typ.positions is None else tuple(plain(t) for t in typ.positions)
    return Type(typ.kind, tuple((k, plain(v)) for k, v in typ.fields), item, typ.open, positions, typ.observed)


@lru_cache(maxsize=8192)
def join(left, right):
    if left == NEVER:
        return right
    if right == NEVER:
        return left
    if left == right:
        return left
    if left.kind == right.kind == "Record" and not left.open and not right.open:
        a, b = dict(left.fields), dict(right.fields)
        discriminated = any(a[k].kind == b[k].kind == "Bool"
                            and a[k].literal is not None and b[k].literal is not None
                            and a[k].literal != b[k].literal for k in a.keys() & b.keys())
        if discriminated:
            return Type("Union", item=tuple(sorted({left, right}, key=_order_key)))
    if left.kind == right.kind and left.kind not in {"Record", "List", "Union"}:
        # Paths that meet with different known values only know the type; the
        # shape (field order, positions) is the one they had without values.
        left, right = plain(left), plain(right)
        if left == right:
            return left
    if left.kind == right.kind == "List":
        # An empty branch contributes no element, not an unknown element.
        if left.positions == () and right.positions != ():
            return Type("List", item=right.item)
        if right.positions == () and left.positions != ():
            return Type("List", item=left.item)
        positions = None
        if (left.positions is not None and right.positions is not None
                and len(left.positions) == len(right.positions)):
            positions = tuple(join(a, b) for a, b in zip(left.positions, right.positions))
        return Type("List", item=join(left.item, right.item), positions=positions)
    if left.kind == right.kind == "Record":
        a, b = dict(left.fields), dict(right.fields)
        keys = a if tuple(a) == tuple(b) else sorted(a.keys() & b.keys())
        return Type("Record", tuple((k, join(a[k], b[k])) for k in keys), open=left.open or right.open)
    if "Unknown" in (left.kind, right.kind):
        return UNKNOWN
    members = set(alternatives(left)) | set(alternatives(right))
    return Type("Union", item=tuple(sorted(members, key=_order_key)))


def _order_key(typ):
    return typ.kind, typ._key


def ordered_list(types):
    """Keep the ordered slots as well as the common element upper bound."""
    positions = tuple(types)
    item = positions[0] if positions else UNKNOWN
    for typ in positions[1:]:
        item = join(item, typ)
    return Type("List", item=item, positions=positions)


def concat_lists(left, right):
    """Concatenation appends positions; control-flow join combines alternatives."""
    if left.positions is not None and right.positions is not None:
        return ordered_list(left.positions + right.positions)
    return Type("List", item=join(left.item, right.item))


def infer(value):
    if isinstance(value, ForeignRef):
        return Type("ForeignRef")
    if isinstance(value, Unit):
        return UNIT_T
    if value is None:
        return NULL
    if type(value) is bool:
        return Type("Bool", literal=value)
    if isinstance(value, (int, float, Decimal)):
        return NUMBER
    if isinstance(value, str):
        return TEXT
    if isinstance(value, list):
        return ordered_list(infer(v) for v in value)
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
        # `$closed: true` — 이 Record 는 선언한 칸이 전부다(선언 밖 이름 접근은 검사에서 MISSING_FIELD).
        # 기본은 열린 Record(옛 봉투는 선언 밖 칸을 싣는다). 항상 같은 칸을 돌려주는 도구만 닫는다 —
        # 실행 중에야 드러나는 없는 칸은 이미 일으킨 부작용을 남긴 채 프로그램을 끝낸다(긴문장 26회차 L26-1).
        closed = spec.get("$closed") is True
        return Type("Record", tuple((k, declared(v)) for k, v in spec.items() if k != "$closed"), open=not closed)
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
    if spec not in {"Unknown", "Unit", "Bool", "Number", "Text", "Null", "List", "Record", "Callable", "Result", "ForeignRef"}:
        raise ValueError(f"알 수 없는 타입: {spec}")
    return Type(spec, item=UNKNOWN if spec == "List" else None)


def compatible(actual, expected):
    if actual == NEVER:
        return True
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
        if expected.observed:
            return True  # 관측 필드는 요구 사항이 아니다
        fields = dict(actual.fields)
        return all(k in fields and compatible(fields[k], v) for k, v in expected.fields)
    return True


def guard(value, spec, label):
    """Validate only the depth constrained by the declared contract."""
    expected = declared(spec)
    # Unknown has no value constraint. Bare containers constrain the outer
    # kind, so inferring every child just to discard its type is unnecessary.
    # Typed fields/elements and mismatches retain the complete check below.
    if expected.kind == 'Unknown':
        return value
    if expected.kind == 'Record' and isinstance(value, dict) and not expected.fields:
        return value
    if (expected.kind == 'List' and isinstance(value, list)
            and (expected.item is None or expected.item.kind == 'Unknown')):
        return value
    actual = infer(value)
    if not compatible(actual, expected):
        # 정적 검사(TYPE)와 같은 처방 — 값으로만 타입이 정해지는 입력은 실행에서 처음 드러난다.
        hint = " 레코드 봉투의 행 목록은 .items로 꺼내 전달하세요." if expected.kind == "List" and actual.kind == "Record" else ""
        raise Fault("TYPE_CONTRACT", f"{label}: {expected}가 필요하지만 {actual}입니다.{hint}")
    return value
