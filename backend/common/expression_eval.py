"""Shared pure tree evaluator; hosts supply budgets and evidence hooks."""
from dataclasses import dataclass, field, replace
import copy
from common.expression_ir import Fault, UNIT
from common.value_semantics import integer_value, TextView
from common.expression_ops import (Builtin, Closure, binary, boolean, number,
                                   scalar_text, pure_call, check_arity, free_names)


@dataclass(frozen=True)
class Binding:
    value: object
    evidence: frozenset = frozenset()
    # Interpreter-owned provenance, never accepted from business JSON. Unknown
    # transforms leave parts empty and conservatively retain whole-value roots.
    parts: dict | None = field(default=None, compare=False, repr=False)
    control: frozenset = frozenset()
    origins: tuple = ()
    shape: frozenset = frozenset()
    failure: object = field(default=None, compare=False, repr=False)
    certificates: tuple = field(default=(), compare=False, repr=False)

    @property
    def shape_evidence(self):
        return self.control | self.shape | (self.evidence if self.parts is None else frozenset())

    def with_shape(self, roots):
        return replace(self, shape=self.shape | frozenset(roots))

    def with_roots(self, roots):
        return replace(self, evidence=frozenset(roots))

    def controlled(self, roots):
        roots = frozenset(roots)
        return replace(self, evidence=self.evidence | roots, control=self.control | roots)

    def select(self, key):
        from common.expression_ir import ResultValue
        if isinstance(self.value, (list, tuple)) and isinstance(key, int) and key < 0:
            key += len(self.value)
        value = self.value.value if isinstance(self.value, ResultValue) and key == 'value' else self.value[key]
        selected = (self.parts or {}).get(key, Binding(value, self.evidence, origins=tuple(
            (eid, (*path, key)) for eid, path in self.origins))).controlled(self.control)
        certs = tuple({**c, 'scope': c['scope'][1:]} for c in self.certificates
                      if c.get('scope') and c['scope'][0] == key)
        return replace(selected, certificates=selected.certificates + certs) if certs else selected

    @classmethod
    def record(cls, parts):
        return cls({k: v.value for k, v in parts.items()},
                   frozenset(e for v in parts.values() for e in v.evidence), parts)

    @classmethod
    def sequence(cls, values):
        return cls([v.value for v in values],
                   frozenset(e for v in values for e in v.evidence), dict(enumerate(values)))


class ExpressionEvaluator:
    def expression_row(self):
        self.expression_tick()

    @staticmethod
    def parents(bindings):
        return frozenset(e for b in bindings for e in b.evidence)

    def expression(self, node, env):
        d, kind = node.data, node.kind
        sub = lambda n: self.eval(n, env)
        if kind == "literal":
            return Binding(copy.deepcopy(d["value"]))
        if kind == "ref":
            if d["name"] not in env:
                raise Fault("UNBOUND", f"정의되지 않은 값: ${d['name']}", node)
            return env[d["name"]]
        if kind == "compat":
            value = sub(d["value"])
            from common.value_semantics import numeric_value
            observed = numeric_value(value.value) if d["mode"] == "number" else None
            result = bool(value.value) if d["mode"] == "bool" else observed if observed is not None else value.value
            return Binding(result, value.evidence)
        if kind == "compat_col":
            key = sub(d["key"])
            return Binding(self.row.get(key.value), key.evidence)
        if kind == "compat_call":
            from common.expression_legacy import compatibility_call
            args = [sub(a) for a in d["args"]]
            return Binding(compatibility_call(d["name"], [a.value for a in args], self.expression_tick), self.parents(args))
        if kind == "compat_bool":
            bindings = []
            for value in d["values"]:
                result = sub(value)
                bindings.append(result)
                if bool(result.value) == (d["op"] == "or"):
                    break
            return Binding(result.value, self.parents(bindings))
        if kind == "conditional":
            condition = sub(d["condition"])
            result = sub(d["yes"] if boolean(condition.value) else d["no"])
            return result.controlled(condition.evidence)
        if kind == "comparison_chain":
            bindings = [sub(d["values"][0])]
            for op, value in zip(d["operators"], d["values"][1:]):
                right = sub(value)
                result = binary(op, bindings[-1].value, right.value)
                bindings.append(right)
                if not result:
                    return Binding(False, self.parents(bindings))
            return Binding(True, self.parents(bindings))
        if kind == "list":
            # Source-order, fail-fast evaluation through the ordinary eval /
            # invoke path: nested calls keep budgets, evidence and receipts.
            # Do not hoist children out of their branch or auto-parallelize.
            values = [sub(v) for v in d["values"]]
            result = [b.value for b in values]
            return Binding(tuple(result), self.parents(values), dict(enumerate(values))) if d.get("legacy_tuple") else Binding.sequence(values)
        if kind == "record":
            if "entries" in d:
                out, bindings, shape = {}, [], set()
                for key, value in d["entries"]:
                    binding = sub(value)
                    bindings.append(binding)
                    if key is None:
                        if not isinstance(binding.value, dict):
                            raise Fault("RECORD_REQUIRED", "펼침에는 Record가 필요합니다.", value)
                        shape.update(binding.shape_evidence)
                        out = {k: v.controlled(binding.shape_evidence) for k, v in out.items()}
                        for field, item in binding.value.items():
                            self.expression_tick()
                            out[field] = binding.select(field)
                    else:
                        out[key] = binding
                return Binding.record(out).with_shape(shape).with_roots(self.parents(bindings))
            values = {k: sub(v) for k, v in d["fields"].items()}
            return Binding.record(values)
        if kind == "slice":
            base = sub(d["base"])
            bounds = [sub(d[k]) if d[k] is not None else Binding(None) for k in ("lower", "upper", "stride")]
            if not isinstance(base.value, (list, str)):
                raise Fault("SLICE_TYPE", "슬라이싱에는 List 또는 Text가 필요합니다.", node)
            # 정수 판정은 Number 의 정수값 관점 하나(integer_value — take 의 n 과 같은 판정, 67회차): 4/2·round(x, 0)
            # 처럼 값이 정수인 Number 는 받고, 소수 부분·Bool·문자열은 거절한다(79회차 F79-3).
            edges = [None if b.value is None else integer_value(b.value) for b in bounds]
            bad = [b.value for b, e in zip(bounds, edges) if b.value is not None and e is None]
            if bad:
                raise Fault("INTEGER_REQUIRED", "슬라이스 경계는 정수 또는 null입니다.", node,
                            details={"bounds": [_index_repr(v) for v in bad],
                                     "types": [_value_type(v) for v in bad]})
            if edges[2] == 0:
                raise Fault("SLICE_STEP", "슬라이스 간격은 0일 수 없습니다.", node)
            view = TextView(base.value) if isinstance(base.value, str) else None
            result = view.select(slice(*edges)) if view else base.value[slice(*edges)]
            selected = range(*slice(*edges).indices(len(view.normalized))) if view else result
            for _ in selected:
                self.expression_tick()
            if not view:
                indices = range(*slice(*edges).indices(len(base.value)))
                return Binding.sequence([base.select(i) for i in indices]).controlled(self.parents(bounds) | base.shape_evidence)
            return Binding(result, self.parents([base, *bounds]))
        if kind in ("field", "index"):
            base = sub(d["base"])
            view = TextView(base.value) if isinstance(base.value, str) else None
            key = Binding(d["key"]) if kind == "field" else sub(d["key"])
            if isinstance(base.value, dict) and isinstance(key.value, str):
                if key.value not in base.value:
                    raise Fault("MISSING_FIELD", f"필드가 없습니다: {key.value}", node,
                                details={"missing_fields": [key.value], "available_fields": list(base.value)[:20]})
            elif kind == "index" and isinstance(base.value, (str, list, tuple)):
                position = integer_value(key.value)
                length = len(view.normalized) if view else len(base.value)
                if position is None or not -length <= position < length:
                    # 어느 값의 몇 번째를 몇 개짜리에서 찾았는지 — 위치만으론 빈 결과인지 오타인지 모른다(77회차 T10·F72-2).
                    # 정수가 아님과 범위 밖을 가른다: 문구·세부가 둘 중 무엇인지 말해야 고칠 방향이 선다(79회차 F79-3).
                    target = d["base"].data.get("name") if d["base"].kind == "ref" else None
                    details = {"index": _index_repr(key.value), "index_type": _value_type(key.value),
                               "length": length, **({"variable": target} if target else {})}
                    if position is None:
                        raise Fault("INDEX", f"인덱스는 정수여야 합니다(받은 값 {details['index']}, {details['index_type']}) — "
                                             "round(x) 또는 // 로 정수를 만드세요.", node, details=details)
                    span = f"허용 {-length}..{length - 1}" if length else "빈 값"
                    raise Fault("INDEX", f"인덱스 {position} 가 범위를 벗어났습니다(길이 {length}, {span}).",
                                node, details=details)
                key = Binding(position, key.evidence)
            else:
                raise Fault("FIELD_TYPE", "이 값에는 해당 필드/인덱스 접근을 할 수 없습니다.", node,
                            details={"field": key.value, "actual_type": type(base.value).__name__})
            if d["base"].kind == "ref" and d["base"].data["name"] == "error" and key.value == "partial":
                self.event(node, "handled_partial", base.evidence)
            return Binding(view.select(key.value), self.parents([base, key])) if view else base.select(key.value).controlled(key.evidence)
        if kind == "unary":
            value = sub(d["value"])
            out = not boolean(value.value) if d["op"] in ("not", "!") else value.value if d.get("legacy") else number(value.value)
            if d["op"] == "-":
                out = -out
            elif d["op"] == "+":
                out = +out
            return Binding(out, value.evidence)
        if kind == "binary":
            a, op = sub(d["left"]), d["op"]
            if op in ("and", "&&", "or", "||"):
                value = boolean(a.value)
                if (op in ("and", "&&") and not value) or (op in ("or", "||") and value):
                    return a
                b = sub(d["right"])
                return Binding(boolean(b.value), self.parents([a, b]))
            b = sub(d["right"])
            if d.get("legacy") and op == "*":
                sequence, count = (a.value, b.value) if isinstance(a.value, (str, list, tuple)) else (b.value, a.value)
                if isinstance(sequence, (str, list, tuple)) and isinstance(count, int):
                    for _ in range(len(sequence) * max(0, count)):
                        self.expression_tick()
            return Binding(binary(op, a.value, b.value, legacy=d.get("legacy", False)), self.parents([a, b]))
        if kind == "lambda":
            captures = {name: env[name] for name in free_names(node) if name in env}
            return Binding(Closure(tuple(d["params"]), d["body"], captures))
        if kind == "builtin":
            return Binding(Builtin(d["name"]))
        if kind == "pure_call":
            # Existing ref/builtin/lambda calls retain argument-first evaluation.
            if d["fn"].kind in ("ref", "builtin", "lambda"):
                args = [sub(a) for a in d["args"]]
                fn = sub(d["fn"])
            else:
                fn = sub(d["fn"])
                args = [sub(a) for a in d["args"]]
            apply = getattr(self, 'apply_component', None)
            result = apply(node, fn, args) if apply else self.callback(fn.value, args)
            return result.controlled(fn.evidence)
        if kind == "format":
            parts = [sub(p) if not isinstance(p, str) else Binding(p) for p in d["parts"]]
            return Binding("".join(scalar_text(p.value) for p in parts), self.parents(parts))
        return NotImplemented

    def callback(self, fn, args):
        if isinstance(fn, Builtin):
            self.check()
            check_arity(fn.name, len(args))
            if fn.name == "reduce":
                rows = args[0].value
                if not isinstance(rows, list):
                    raise Fault("LIST_REQUIRED", "reduce에는 List가 필요합니다.")
                acc = args[1]
                for i, row in enumerate(rows):
                    self.expression_row()
                    acc = self.callback(args[2].value, [acc, args[0].select(i)])
                return acc.controlled(args[0].shape_evidence | args[2].evidence)
            if fn.name == 'get' and isinstance(args[0].value, dict) and isinstance(args[1].value, str):
                key = args[1].value
                selected = args[0].select(key) if key in args[0].value else args[2] if len(args) > 2 else Binding(None)
                return selected.controlled(args[1].evidence | (args[0].control if key in args[0].value else args[0].shape_evidence))
            if fn.name == 'propagate' and args[0].failure is not None:
                from common.expression_ops import propagate_failure
                propagate_failure(args[0].failure)
            if fn.name == 'error_of':
                from common.expression_ir import ResultValue
                first = args[0].value
                if isinstance(first, ResultValue) and not first.ok:
                    return Binding(first.error, args[0].evidence, failure=first.failure)
            if fn.name in ('unwrap', 'propagate'):
                from common.expression_ir import ResultValue
                if isinstance(args[0].value, ResultValue) and args[0].value.ok:
                    return args[0].select('value')
            if fn.name == "evidence":
                return Binding(self.evidence(args[0].evidence), self.parents(args))
            if fn.name in ('map', 'filter'):
                applied = []
                def apply(f, row):
                    binding = self.callback(f, [args[0].select(len(applied))])
                    applied.append(binding)
                    return binding.value
                # Value validation, errors and iteration budgets stay in the
                # one value library; only its successful result gains sidecars.
                pure_call(fn.name, [a.value for a in args], tick=self.expression_tick, callback=apply)
                if fn.name == 'map':
                    return Binding.sequence(applied).controlled(args[0].shape_evidence | args[1].evidence)
                selected = [args[0].select(i) for i, test in enumerate(applied) if test.value]
                return Binding.sequence(selected).controlled(self.parents(applied) | args[0].shape_evidence | args[1].evidence)
            return Binding(pure_call(fn.name, [a.value for a in args], tick=self.expression_tick,
                                     callback=lambda f, row: self.callback(f, [Binding(row, self.parents(args))]).value), self.parents(args))
        if not isinstance(fn, Closure) or len(args) != len(fn.params):
            raise Fault("CALLABLE", "콜백 또는 인자 수가 잘못되었습니다.")
        env = {**fn.env, **dict(zip(fn.params, args))}
        return self.eval(fn.body, env)


class ValueEvaluator(ExpressionEvaluator):
    """Bounded value-only host for compatibility expressions; never invokes tools."""
    def __init__(self, row=None, limit=100000):
        self.row = row or {}
        self.remaining = limit

    def check(self):
        self.remaining -= 1
        if self.remaining < 0:
            raise Fault("BUDGET", "식 실행 예산을 초과했습니다.", kind="budget")

    expression_tick = check

    def event(self, *args, **kwargs):
        return None

    def evidence(self, roots):
        raise Fault("EVIDENCE_CONTEXT", "기존 행 식에는 실행 근거 조회 컨텍스트가 없습니다.")

    def eval(self, node, env):
        self.check()
        result = self.expression(node, env)
        if result is NotImplemented:
            raise Fault("PURE_EXPRESSION", "순수 값 식만 사용할 수 있습니다.", node)
        return result


def _value_type(value):
    """진단용 IBL 값 타입 이름 — 파이썬 표현(Decimal·float)을 드러내지 않는다."""
    if isinstance(value, bool):
        return "Bool"
    if isinstance(value, (int, float)) or type(value).__name__ == "Decimal":
        return "Number"
    return {str: "Text", list: "List", tuple: "List", dict: "Record", type(None): "Null"}.get(type(value), type(value).__name__)


def _index_repr(value):
    """진단 세부에 실을 인덱스 값 — JSON 으로 나를 수 있는 스칼라만 원형, 나머지는 타입 이름."""
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if type(value).__name__ == "Decimal":
        whole = integer_value(value)
        return whole if whole is not None else str(value)
    return _value_type(value)
