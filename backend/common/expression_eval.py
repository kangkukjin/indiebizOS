"""Shared pure tree evaluator; hosts supply budgets and evidence hooks."""
from dataclasses import dataclass
import copy
from common.expression_ir import Fault, UNIT
from common.value_semantics import normalized_text
from common.expression_ops import (Builtin, Closure, binary, boolean, number,
                                   scalar_text, pure_call, check_arity, free_names)


@dataclass(frozen=True)
class Binding:
    value: object
    evidence: frozenset = frozenset()


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
            return Binding(result.value, self.parents([condition, result]))
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
            return Binding(tuple(result) if d.get("legacy_tuple") else result, self.parents(values))
        if kind == "record":
            if "entries" in d:
                out, bindings = {}, []
                for key, value in d["entries"]:
                    binding = sub(value)
                    bindings.append(binding)
                    if key is None:
                        if not isinstance(binding.value, dict):
                            raise Fault("RECORD_REQUIRED", "펼침에는 Record가 필요합니다.", value)
                        for field, item in binding.value.items():
                            self.expression_tick()
                            out[field] = item
                    else:
                        out[key] = binding.value
                return Binding(out, self.parents(bindings))
            values = {k: sub(v) for k, v in d["fields"].items()}
            return Binding({k: b.value for k, b in values.items()}, self.parents(values.values()))
        if kind == "slice":
            base = sub(d["base"])
            bounds = [sub(d[k]) if d[k] is not None else Binding(None) for k in ("lower", "upper", "stride")]
            if not isinstance(base.value, (list, str)):
                raise Fault("SLICE_TYPE", "슬라이싱에는 List 또는 Text가 필요합니다.", node)
            if any(b.value is not None and type(b.value) is not int for b in bounds):
                raise Fault("INTEGER_REQUIRED", "슬라이스 경계는 정수 또는 null입니다.", node)
            if bounds[2].value == 0:
                raise Fault("SLICE_STEP", "슬라이스 간격은 0일 수 없습니다.", node)
            source = normalized_text(base.value) if isinstance(base.value, str) else base.value
            result = source[slice(*(b.value for b in bounds))]
            for _ in result:
                self.expression_tick()
            return Binding(result, self.parents([base, *bounds]))
        if kind in ("field", "index"):
            base = sub(d["base"])
            if isinstance(base.value, str):
                base = Binding(normalized_text(base.value), base.evidence)
            key = Binding(d["key"]) if kind == "field" else sub(d["key"])
            if isinstance(base.value, dict) and isinstance(key.value, str):
                if key.value not in base.value:
                    raise Fault("MISSING_FIELD", f"필드가 없습니다: {key.value}", node)
            elif kind == "index" and isinstance(base.value, (str, list, tuple)):
                if type(key.value) is not int or not -len(base.value) <= key.value < len(base.value):
                    raise Fault("INDEX", "인덱스가 범위를 벗어났거나 정수가 아닙니다.", node)
            else:
                raise Fault("FIELD_TYPE", "이 값에는 해당 필드/인덱스 접근을 할 수 없습니다.", node)
            if d["base"].kind == "ref" and d["base"].data["name"] == "error" and key.value == "partial":
                self.event(node, "handled_partial", base.evidence)
            return Binding(base.value[key.value], self.parents([base, key]))
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
            return Binding(Closure(tuple(d["params"]), d["body"], captures), self.parents(captures.values()))
        if kind == "builtin":
            return Binding(Builtin(d["name"]))
        if kind == "pure_call":
            args = [sub(a) for a in d["args"]]
            fn = sub(d["fn"])
            return self.callback(fn.value, args)
        if kind == "format":
            parts = [sub(p) if not isinstance(p, str) else Binding(p) for p in d["parts"]]
            return Binding(normalized_text("".join(scalar_text(p.value) for p in parts)), self.parents(parts))
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
                for row in rows:
                    self.expression_row()
                    acc = self.callback(args[2].value, [acc, Binding(row, args[0].evidence)])
                return acc
            if fn.name == "evidence":
                return Binding(self.evidence(args[0].evidence), self.parents(args))
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
