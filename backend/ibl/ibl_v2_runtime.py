"""Edition 2 interpreter over the checked core tree.

One shared budget, explicit Outcome boundaries and evidence sidecars. No source
is reparsed while mapping rows. External calls use only the plan's adapters.
"""
from contextlib import ExitStack
from common.foreign_ref import wire_protocol
from dataclasses import dataclass, field
import copy
import threading
import time
from execution_capacity import fanout as bounded_fanout, scope as execution_scope
from ibl_v2_ir import (Node, Fault, UNIT, Unit, ResultValue, digest, digest_packed, pack, projection, span,
                       parallel_branches)
from ibl_v2_expr import (Builtin, Closure, binary, boolean, number, scalar_text,
                         pure_call, check_arity, free_names)
from ibl_v2_types import guard


from common.expression_eval import Binding, ExpressionEvaluator

#: 취소 확인 간격(초). 확인 함수가 파일·프로세스를 보는 경로가 있어 걸음마다 부르지 않는다.
_CANCEL_CHECK_INTERVAL_S = 0.02

#: 진행 신고 최소 간격(초). 같은 액션·같은 부류의 신고는 이 간격 안에서 하나로 접는다 — 천 행짜리
#: each 가 천 번 티켓 파일을 다시 쓰지 않도록. 액션이 바뀌면 간격과 무관하게 바로 신고한다.
_PROGRESS_MIN_INTERVAL_S = 0.25

#: 미지정 입력(declared_inputs − inputs)의 값 자리 표식. 레코드(호출 인자)에서는 그 필드가 빠지고,
#: f-문자열 보간에서는 빈 문자열이 된다. 컴파일러가 그 두 자리 밖의 사용을 거절하므로 업무 값으로 새지 않는다.
OMITTED = object()


class Returned(BaseException):
    def __init__(self, binding):
        self.binding = binding


@dataclass
class Budget:
    REQUEST_LIMITS = {"steps": 10_000_000, "rows": 100_000}
    steps: int = 100000
    rows: int = 10000
    seconds: float | None = None
    depth: int = 64
    started: float = field(default_factory=time.monotonic)
    used_steps: int = 0
    used_rows: int = 0
    by_node: dict = field(default_factory=dict)
    lock: object = field(default_factory=threading.RLock)

    @classmethod
    def from_request(cls, value):
        if value is None:
            return cls()
        limits = cls.REQUEST_LIMITS
        if (not isinstance(value, dict) or set(value) - limits.keys()
                or any(type(v) is not int or not 1 <= v <= limits[k] for k, v in value.items())):
            raise Fault("BUDGET_ARGUMENT", f"budget은 steps(1~{limits['steps']}), rows(1~{limits['rows']}) 정수만 지정합니다.", kind="compile")
        return cls(**value)

    def tick(self, row=False, depth=0, node_id=None):
        with self.lock:
            self.used_steps += 1
            self.used_rows += int(row)
            if node_id is not None:
                self.by_node[node_id] = self.by_node.get(node_id, 0) + 1
            elapsed = time.monotonic() - self.started if self.seconds is not None else None
            if (self.used_steps <= self.steps and self.used_rows <= self.rows
                    and depth <= self.depth and (elapsed is None or elapsed <= self.seconds)):
                return
            measurements = {"steps": (self.used_steps, self.steps),
                            "rows": (self.used_rows, self.rows),
                            "seconds": (elapsed, self.seconds),
                            "depth": (depth, self.depth)}
            exceeded = {key: {"used": used, "limit": limit}
                        for key, (used, limit) in measurements.items()
                        if limit is not None and used > limit}
            if exceeded:
                hint = ("usage.steps_by_line에서 비싼 줄을 확인하고 요청 budget:{steps:...,rows:...}로 한도를 조정하세요"
                        f"(최대 steps {self.REQUEST_LIMITS['steps']}·rows {self.REQUEST_LIMITS['rows']}). "
                        "전건 검증 뒤 쓰는 과제는 검증·쓰기 순서를 유지하세요. 독립적으로 완료할 수 있는 작업만 "
                        "여러 실행으로 나누고, 전건 처리를 take로 조용히 잘라내지 마세요.")
                dimensions = ", ".join(f"{k} {v['used']:g}/{v['limit']:g}" for k, v in exceeded.items())
                raise Fault("BUDGET", f"공유 실행 예산을 초과했습니다: {dimensions}. {hint}",
                            kind="budget", details={"exceeded": exceeded, "hint": hint})


def returned_shape(value):
    """함수가 실제로 돌려준 값의 최상위 모양 — 관측 반환 필드의 재료(값 자체는 싣지 않는다, 2026-09-26)."""
    if isinstance(value, dict):
        return {"returns_kind": "record", "returns_keys": [k for k in value][:40]}
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return {"returns_kind": "list", "returns_keys": [k for k in value[0]][:40]}
    return {}


def _covered_seconds(spans):
    """겹치는 구간을 한 번만 센 길이 — 병렬 호출의 벽시계 시간."""
    total, edge = 0.0, None
    for start, end in sorted(spans):
        if edge is None or start > edge:
            total += end - start
            edge = end
        elif end > edge:
            total += end - edge
            edge = end
    return total


class Runtime(ExpressionEvaluator):
    def __init__(self, plan, inputs=None, *, cancel_check=None, budget=None,
                 recordings=None, replay=False, journal=None, reusable=None, reuse_run=None,
                 input_evidence=None, value_protocols=None, reuse_models=True, strict_composition=False, completion=None):
        from ibl_v2_completion import validate
        self.completion = validate(completion)
        self.execution_started = False
        self.last_out = None
        from uuid import uuid4
        self.completion_scope = uuid4().hex + ":"
        self.strict_composition = strict_composition
        self.component_outcomes = []
        self.value_protocols = set(value_protocols or ("ibl-value/1", "ibl-value/2"))
        self.resources = ExitStack()
        self.foreign_sessions = {}
        self.foreign_evidence = frozenset()
        self.foreign_lock = threading.RLock()
        self.journal = journal
        # 편집한 프로그램이 앞 실행(reuse_run)의 읽기·모델 영수증을 액션·인자·구현 지문으로 재사용한다.
        # 프로그램 지문은 키에 없다 — 함수 하나를 고쳐도 검증된 수집 결과가 살아남는 통로(2026-09-26).
        self.reusable, self.reuse_run, self.reused_calls = dict(reusable or {}), reuse_run, 0
        self.reuse_skipped, self.reuse_skipped_total = [], 0
        self.plan = plan
        self.inputs = copy.deepcopy(inputs or {})
        self.input_evidence = copy.deepcopy(input_evidence or {})
        self.reuse_writes = []
        self.cancel_check = cancel_check
        self._next_cancel_check = 0.0   # 첫 걸음에서는 바로 확인한다
        self.budget = budget or Budget()
        self.trace, self.recordings = [], []
        self.tool_time = {}   # node_id → [호출 수, 초, 액션, 구간들] — 걸음 수가 세지 않는 도구 시간을 줄별로 보인다
        self.model_usage = []
        self.reuse_models = reuse_models
        self.reused_model_calls = 0
        self.consumed_model_receipts = set()
        self.expression_events = {}
        self.source_map = {}
        self.replay, self.recorded = replay, list(recordings or [])
        self.lock = threading.RLock()
        self.local = threading.local()
        # 진행 신고(ibl_progress) — 표면 티켓 소유권·호출 번호·부류별 마지막 신고 (2026-10-26).
        self._progress_ticket = None
        self._progress_calls = 0
        self._progress_lock = threading.RLock()
        self._progress_active = set()
        self._progress_last = {}   # 부류("action"/"row") → (키, monotonic)
        self._progress_pending = None   # 접힌 좌표(step, 액션, 회차) — 다음 beat 앞에서 흘려 보낸다(100회차 L100-3)
        from execution_commit import current_scope, CommitScope
        self.commit_scope = current_scope() or CommitScope()
        self.owns_commit_scope = current_scope() is None

    def event(self, node, kind, parents=(), *, coalesce=False, **extra):
        with self.lock:
            key = (node.id, kind, tuple(sorted(parents)), tuple(extra.get('selected_parents', ())))
            if coalesce and key in self.expression_events:
                eid = self.expression_events[key]
                self.trace[eid - 1]['evaluations'] = self.trace[eid - 1].get('evaluations', 1) + 1
                dependencies = getattr(self.local, 'dependencies', None)
                if dependencies is not None:
                    dependencies.add(eid)
                return eid
            eid = len(self.trace) + 1
            if node.id not in self.source_map:
                self.source_map[node.id] = span(self.plan.source, node)
            self.trace.append({"id": eid, "node_id": node.id, "invocation_id": eid,
                               "kind": kind, "parents": sorted(parents),
                               **extra})
            if coalesce:
                self.expression_events[key] = eid
            dependencies = getattr(self.local, "dependencies", None)
            if dependencies is not None:
                dependencies.add(eid)
        return eid

    def evidence(self, roots):
        with self.lock:
            by_id = {e["id"]: e for e in self.trace}
            pending, found = list(roots), set()
            while pending:
                eid = pending.pop()
                if eid in found:
                    continue
                found.add(eid)
                pending.extend(by_id[eid]["parents"])
            events = [by_id[e] for e in sorted(found)]
        return {"events": copy.deepcopy(events), "fingerprint": digest(events),
                "source_map": {e["node_id"]: self.source_map[e["node_id"]] for e in events}}

    def check(self):
        cleanup = getattr(self.local, "cleanup", None)
        if cleanup is not None:
            cleanup[0] -= 1
            if cleanup[0] < 0 or time.monotonic() > cleanup[1]:
                raise Fault("CLEANUP_BUDGET", "정리 예산(100단계·1초)을 초과했습니다.", kind="budget")
            return
        if self.cancel_check:
            # 취소 확인은 걸음마다가 아니라 짧은 간격으로 한다. MCP 경로의 확인은 파일 두 번·프로세스 조회라
            # 30만 걸음짜리 문장이 3초 대신 35초 걸렸다(ep4211, 초당 9천 걸음). 순수 계산 구간의 취소 반응은
            # 최대 20ms 늦고, 액션 호출 직후에는 간격과 무관하게 바로 확인한다.
            now = time.monotonic()
            if now >= self._next_cancel_check:
                self._next_cancel_check = now + _CANCEL_CHECK_INTERVAL_S
                if self.cancel_check():
                    raise Fault("CANCELLED", "실행이 취소되었습니다.", kind="cancelled")
        self.budget.tick(depth=getattr(self.local, "depth", 0), node_id=getattr(self.local, "node_id", None))

    def frame(self, body, env):
        try:
            return self.eval(body, env)
        except Returned as returned:
            return returned.binding

    def eval(self, node, env, piped=None, *, control=()):
        if node is None:
            return Binding(UNIT)
        # Every evaluated child contributes on all three exits: value, return,
        # and failure. Per-syntax unions missed empty folds, interrupted loops,
        # failed conditions, and finally. Keep scopes local to each worker;
        # fanout explicitly joins their roots after all started work settles.
        previous = getattr(self.local, "dependencies", None)
        previous_node = getattr(self.local, "node_id", None)
        self.local.node_id = node.id
        if node.id not in self.source_map:
            self.source_map[node.id] = span(self.plan.source, node)
        previous_control = getattr(self.local, "control", frozenset())
        self.local.control = previous_control | frozenset(control)
        dependencies, roots = set(self.local.control), frozenset()
        self.local.dependencies = dependencies
        try:
            self.check()
            try:
                result = self._eval(node, env, piped)
            except Exception as exc:
                if isinstance(exc, Fault):
                    raise
                raise Fault("VALUE", str(exc), node) from exc
            eid = self.event(node, node.kind, result.evidence | dependencies, coalesce=True,
                             selected_parents=sorted(result.evidence | self.local.control))
            roots = frozenset({eid})
            return result.controlled(self.local.control).with_roots(roots)
        except Returned as returned:
            roots = returned.binding.evidence if node.kind == "sequence" else returned.binding.evidence | dependencies
            returned.binding = returned.binding.controlled(self.local.control).with_roots(roots)
            raise
        except Fault as exc:
            if exc.node is None:
                exc.node = node
            eid = self.event(node, "failure", set(exc.evidence) | dependencies, code=exc.code,
                             failure_kind=exc.kind, incomplete=exc.kind == "partial")
            roots = frozenset({eid})
            exc.evidence = [eid]
            raise
        finally:
            self.local.node_id = previous_node
            self.local.dependencies = previous
            self.local.control = previous_control
            if previous is not None:
                previous.update(roots)

    def _eval(self, node, env, piped):
        d, kind = node.data, node.kind
        sub = lambda n: self.eval(n, env)
        unspecified = self.plan.unspecified
        if unspecified:
            if kind == "ref" and d["name"] in unspecified and d["name"] not in env:
                return Binding(OMITTED)
            if kind == "format":
                parts = [sub(p) if not isinstance(p, str) else Binding(p) for p in d["parts"]]
                text = "".join("" if p.value is OMITTED else scalar_text(p.value) for p in parts)
                return Binding(text, self.parents(parts))
        if kind == "callable_ref":
            from common.expression_ops import CallableRef
            return Binding(CallableRef(d['node'], d['action'], d.get('symbol')))
        if kind == "named_call":
            fn = sub(d['fn'])
            args = sub(d['params'])
            return self.apply_component(node, fn, args, piped)
        if kind == "pure_call" and piped is not None:
            fn = sub(d["fn"])
            args = [piped, *[sub(a) for a in d["args"]]]
            result = self.apply_component(node, fn, args)
            return result.controlled(fn.evidence)
        value = self.expression(node, env)
        if value is not NotImplemented:
            if unspecified and kind == "record" and isinstance(value.value, dict) \
                    and any(v is OMITTED for v in value.value.values()):
                value = Binding({k: v for k, v in value.value.items() if v is not OMITTED}, value.evidence)
            return value
        if kind == "sequence":
            result, parents = Binding(UNIT), set()
            for statement in d["statements"]:
                try:
                    result = sub(statement)
                except Returned as returned:
                    selected = returned.binding.evidence | getattr(self.local, 'control', frozenset())
                    eid = self.event(node, 'selection', selected | parents, coalesce=True, selected_parents=sorted(selected))
                    returned.binding = returned.binding.with_roots({eid})
                    raise
                except Fault as exc:
                    exc.evidence = sorted(set(exc.evidence) | parents)
                    raise
                parents.update(result.evidence)
            selected = result.evidence | getattr(self.local, 'control', frozenset())
            eid = self.event(node, 'selection', selected | parents, coalesce=True, selected_parents=sorted(selected))
            return result.with_roots({eid})
        if kind == "bind":
            env[d["name"]] = sub(d["value"])
            return Binding(UNIT, env[d["name"]].evidence)
        if kind == "def":
            return Binding(UNIT)
        if kind == "assert":
            condition = sub(d["condition"])
            passed = boolean(condition.value)
            from ibl_v2_analysis import constant_value
            metadata = constant_value(d['details']) if d['details'] is not None else {}
            metadata = {k: v for k, v in metadata.items() if k in ('criterion_id', 'criterion_text', 'scope') and isinstance(v, str)} if isinstance(metadata, dict) else {}
            self.event(node, 'assertion', condition.evidence, passed=passed, **metadata,
                       predicate_hash=digest(self.plan.source[d['condition'].start:d['condition'].end]))
            if not passed:
                message = sub(d["message"]) if d["message"] is not None else Binding("조건을 충족하지 못했습니다.")
                details = sub(d["details"]) if d["details"] is not None else Binding({})
                if not isinstance(message.value, str) or not isinstance(details.value, dict):
                    raise Fault("ASSERT_CONTRACT", "assert의 메시지는 Text, 상세는 Record입니다.", node)
                raise Fault("ASSERTION_FAILED", message.value, node, details=details.value)
            return Binding(UNIT, condition.evidence)
        if kind == "return":
            raise Returned(sub(d["value"]))
        if kind == "pipe":
            return self.eval(d["right"], env, sub(d["left"]))
        if kind == "fallback":
            try:
                return sub(d["left"])
            except Fault as exc:
                if not exc.catchable:
                    raise
                eid = self.event(node, "recovered", exc.evidence, error=projection(exc.view(self.plan.source)))
                result = sub(d["right"])
                return result.with_roots(result.evidence | {eid})
        if kind == "parallel":
            nodes = list(parallel_branches(node))
            from ibl_v2_access import admit
            admit(self, node, [(n, env) for n in nodes])
            results = self.fanout(node, len(nodes), lambda i: self.frame(nodes[i], env.copy()), min(8, len(nodes)))
            return Binding.sequence(results)
        if kind == "call":
            args = sub(d["params"])
            if d["node"] == "table" and d["action"] == "each":
                return self.each(node, env, args, piped)
            if d["node"] == "fn" and "symbol" in d:
                from common.expression_ops import CallableRef
                return self.apply_component(node, Binding(CallableRef('fn', d['action'], d['symbol'])), args, piped)
            return self.invoke(node, args, piped)
        if kind == "if":
            condition = sub(d["value"])
            try:
                result = self.eval(d["body"] if boolean(condition.value) else d["otherwise"],
                                   env, control=condition.evidence)
                return result.controlled(condition.evidence)
            except Returned as returned:
                returned.binding = returned.binding.controlled(condition.evidence)
                raise
        if kind == "case":
            condition = sub(d["value"])
            parents = condition.evidence
            target = d["otherwise"]
            for expected, body in d["branches"]:
                value = sub(expected)
                parents |= value.evidence
                if binary("==", condition.value, value.value):
                    target = body
                    break
            try:
                result = self.eval(target, env, control=parents)
                return result.controlled(parents)
            except Returned as returned:
                returned.binding = returned.binding.controlled(parents)
                raise
        if kind == "try":
            return self.try_block(node, env)
        if kind == "repeat":
            mode = d["mode"]
            count = sub(d["value"]) if mode == "count" else None
            if count and (type(count.value) is not int or count.value < 0):
                raise Fault("REPEAT_COUNT", "repeat 횟수는 0 이상의 정수입니다.", node)
            i, parents = 0, set(count.evidence if count else ())
            before = env.copy()
            old_i = env.get("i")
            try:
                while count is None or i < count.value:
                    # The pre-test condition and body share this iteration's
                    # index, never an outer index or the previous iteration's.
                    env["i"] = Binding(i)
                    if mode == "while":
                        cond = sub(d["value"])
                        parents.update(cond.evidence)
                        if not boolean(cond.value):
                            break
                    self.budget.tick(row=True)
                    result = self.eval(d["body"], env, control=parents)
                    # The body root already links prior iterations through
                    # control; retaining every old root here grows quadratically.
                    parents = set(result.evidence)
                    i += 1
                    if mode == "until":
                        cond = sub(d["value"])
                        parents.update(cond.evidence)
                        if boolean(cond.value):
                            break
            finally:
                # The final while/until decision also controls which version
                # of a rebound value leaves the loop.
                for name, binding in env.items():
                    if name != "i" and binding is not before.get(name):
                        env[name] = binding.controlled(parents)
                if old_i is None:
                    env.pop("i", None)
                else:
                    env["i"] = old_i
            return Binding(UNIT, frozenset(parents))
        raise Fault("IR", f"지원하지 않는 구문: {kind}", node, kind="protocol")

    def apply_component(self, node, fn, args, piped=None):
        from common.expression_ops import CallableRef, callable_identity
        target = fn.value
        if isinstance(target, Builtin) and not isinstance(args, Binding):
            return self.callback(target, args)
        named = isinstance(args, Binding)
        if named and not isinstance(args.value, dict):
            raise Fault('ARGUMENT_STYLE', '명명 적용은 Record 인자를 받습니다.', node)
        route = getattr(self.local, 'route', ())
        # Definition/capture identity supplements source position and loop route.
        # It is an identity hash, never a capability or a serialized closure.
        identity = callable_identity(target, node_map=self.journal.node_map if self.journal else None)
        components = getattr(self.local, 'components', ())
        self.local.components = (*components, identity)
        self.local.route = (*route, ('apply', node.id, self.ordinal('apply:' + node.id)))
        try:
            if isinstance(target, CallableRef):
                if not named:
                    raise Fault('ARGUMENT_STYLE', '이 부품은 명명 인자 {...}로 적용하세요.', node)
                key = target.symbol or target.node + ':' + target.action
                metadata = dict(node.data.get('applications', {}).get(key, {}))
                metadata.update(node=target.node, action=target.action, symbol=target.symbol)
                virtual = Node('call', node.start, node.end, metadata)
                if target.symbol:
                    if target.symbol not in self.plan.functions:
                        raise Fault('DEFINITION_CHANGED', '함수 참조가 현재 계획에 없습니다.', node, kind='protocol')
                    result = self.call_function(virtual, args, piped)
                else:
                    if key not in self.plan.registry:
                        raise Fault('DEFINITION_CHANGED', '어휘 참조가 현재 사전에 없습니다.', node, kind='protocol')
                    result = self.invoke(virtual, args, piped)
            elif isinstance(target, Closure):
                if named:
                    args = self.inject(node, args, next(iter(target.params), None), piped)
                    if set(args.value) != set(target.params):
                        raise Fault('FUNCTION_ARGUMENTS', '람다 명명 인자가 계약과 다릅니다.', node)
                    args = [args.select(p) for p in target.params]
                result = self.apply_closure(target, args)
            else:
                if named:
                    raise Fault('ARGUMENT_STYLE', '내장 함수는 위치 인자 (...)로 적용하세요.', node)
                result = self.callback(target, args)
            return result.controlled(fn.evidence)
        finally:
            self.local.route = route
            self.local.components = components

    def callback(self, fn, args):
        # A value-only combinator cannot acquire effectful execution simply
        # because its callback was selected dynamically.
        previous = getattr(self.local, 'pure_required', False)
        self.local.pure_required = True
        try:
            return self.apply_closure(fn, args) if isinstance(fn, Closure) else super().callback(fn, args)
        finally:
            self.local.pure_required = previous

    def apply_closure(self, fn, args):
        depth = getattr(self.local, 'depth', 0)
        self.local.depth = depth + 1
        try:
            return super().callback(fn, args)
        finally:
            self.local.depth = depth

    def call_function(self, node, args, piped=None):
        d = node.data
        definition = self.plan.functions[d["symbol"]]
        params = definition.data["params"]
        args = self.inject(node, args, next(iter(params), None), piped)
        unknown = args.value.keys() - params.keys()
        missing = [k for k, default in params.items() if k not in args.value and default is None]
        if unknown or missing:
            raise Fault("FUNCTION_ARGUMENTS", "함수 인자가 계약과 다릅니다.", node,
                        details={"unknown": sorted(unknown), "missing": missing})
        local = {k: args.select(k) for k in args.value}
        for name, default in params.items():
            if name not in local:
                local[name] = self.eval(default, {})
        if definition.data.get('annotations'):
            from ibl_v2_requirements import runtime_annotations
            runtime_annotations(self, definition, local)
        entry = next((e for e in self.plan.dependencies.get('source_map', [])[1:]
                      if e['start'] <= definition.start < e['end']), {})
        function_ref = entry.get('function_ref')
        depth = getattr(self.local, "depth", 0)
        self.local.depth = depth + 1
        try:
            from ibl_v2_component_runtime import execute
            result = execute(self, d['symbol'], node, {k: v.value for k, v in local.items()},
                             lambda: self.frame(definition.data["body"], local))
            eid = self.event(node, "function_result", result.evidence | args.evidence,
                             selected_parents=sorted(result.evidence),
                             name=d["action"], definition_start=definition.start, success=True,
                             function_ref=function_ref,
                             **returned_shape(result.value))
            return result.with_roots({eid})
        except Fault as exc:
            eid = self.event(node, "function_result", exc.evidence,
                             name=d["action"], definition_start=definition.start, success=False,
                             function_ref=function_ref)
            exc.evidence = [eid]
            exc.frames.append({"function": d["action"], "call": span(self.plan.source, node),
                               "definition": span(self.plan.source, definition)})
            raise
        finally:
            self.local.depth = depth

    @staticmethod
    def parents(bindings):
        return frozenset(e for b in bindings for e in b.evidence)

    @staticmethod
    def inject(node, args, receiver, piped):
        if piped is None:
            return args
        if receiver is None or receiver in args.value:
            from ibl_v2_analysis import pipe_collision_message
            d = node.data
            callee = f"[{d['node']}:{d['action']}]" if d.get("node") and d.get("action") else ""
            raise Fault("PIPE_COLLISION", pipe_collision_message(callee, receiver), node)
        return Binding.record({**{k: args.select(k) for k in args.value}, receiver: piped})

    def expression_tick(self):
        # Pure work shares the step/time/cancellation budget. The row budget
        # remains the count of each/repeat work, not comparison internals.
        self.check()

    def expression_row(self):
        self.check()
        self.budget.tick(row=True)

    def each(self, node, env, args, piped):
        args = self.inject(node, args, "items", piped)
        options = args.value
        from ibl_v2_types import rows_value
        items = guard(rows_value(options["items"]), "List", "each.items")
        mode, collect = options.get("mode", "map"), options.get("on_error", "stop") == "collect"
        coverage = args.select("items").shape_evidence | args.control
        calls_at_entry = self._progress_calls
        def row(index):
            self.budget.tick(row=True)
            # 회차는 이 스레드의 현재값으로 둔다 — 행 안의 액션 좌표 신고가 자기 회차를 동봉한다(병렬 가지는 각자 스레드).
            detail = self._row_detail(index + 1, len(items), items[index])
            previous_detail = getattr(self.local, "row_detail", None)
            self.local.row_detail = detail
            self._report_row(detail, pure=(self._progress_calls == calls_at_entry))
            local = {**env, "it": args.select("items").select(index) if isinstance(options["items"], list) else Binding(items[index], args.evidence), "i": Binding(index)}
            try:
                result = self.frame(node.data["body"], local)
            finally:
                self.local.row_detail = previous_detail
            if mode == "flat_map":
                guard(result.value, "List", "flat_map 반환")
            return result
        if options.get("parallel", 1) > 1 and len(items) > 1:
            from ibl_v2_access import admit
            admit(self, node, [(node.data["body"], {**env, "it": Binding(item), "i": Binding(i)})
                               for i, item in enumerate(items)])
        results = self.fanout(node, len(items), row, options.get("parallel", 1), collect)
        if mode == "effect":
            value = UNIT
        elif mode == "flat_map":
            value = [v for result in results for v in result.value]
        else:
            value = [b.value for b in results]
        if mode == 'map':
            return Binding.sequence(results).controlled(coverage)
        if mode == 'flat_map':
            return Binding.sequence([result.select(i) for result in results for i in range(len(result.value))]).controlled(coverage)
        return Binding(value, self.parents(results) | args.evidence)

    def fanout(self, node, count, fn, workers, collect=False):
        results, errors, states = {}, {}, ["pending"] * count
        depth = getattr(self.local, "depth", 0)
        control = getattr(self.local, "control", frozenset())
        route = getattr(self.local, "route", ()) + ((node.id, self.ordinal("fanout:" + node.id)),)
        components = getattr(self.local, "components", ())
        pure_required = getattr(self.local, "pure_required", False)
        obligations = getattr(self.local, 'obligations', ())
        def run(i):
            previous = getattr(self.local, "parallel", False)
            previous_depth = getattr(self.local, "depth", 0)
            previous_route = getattr(self.local, "route", ())
            previous_counts = getattr(self.local, "counts", {})
            previous_components = getattr(self.local, "components", ())
            previous_pure = getattr(self.local, "pure_required", False)
            previous_obligations = getattr(self.local, 'obligations', ())
            self.local.obligations = obligations
            self.local.components, self.local.pure_required = components, pure_required
            previous_control = getattr(self.local, "control", frozenset())
            self.local.route, self.local.counts = route + (i,), {}
            self.local.parallel, self.local.depth = True, depth
            self.local.control = control
            try:
                self.check()
                return fn(i)
            finally:
                self.local.parallel, self.local.depth = previous, previous_depth
                self.local.route, self.local.counts = previous_route, previous_counts
                self.local.control = previous_control
                self.local.components, self.local.pure_required = previous_components, previous_pure
                self.local.obligations = previous_obligations
        def accept(i, future=None):
            try:
                result = future.result() if future else run(i)
                results[i] = Binding(ResultValue(True, result.value), result.evidence, {'value': result}) if collect else result
                states[i] = "ok"
                return True
            except Fault as exc:
                errors[i], states[i] = exc, "failed"
                if collect and exc.catchable:
                    eid = self.event(node, "collected_error", exc.evidence, index=i, incomplete=True)
                    results[i] = Binding(ResultValue(False, error=exc.view(self.plan.source), failure=exc), frozenset({eid}))
                    return True
                return False
        bounded_fanout(count, workers, run, accept, role="ibl_v2")
        fatal = [i for i, e in errors.items() if not collect or not e.catchable]
        if fatal:
            first = errors[min(fatal)]
            parents = self.parents(results.values()) | {e for error in errors.values() for e in error.evidence}
            eid = self.event(node, "coverage", parents, states=states,
                             successful_indices=sorted(results), incomplete=True)
            error = Fault(first.code, str(first), first.node,
                          kind=first.kind if not first.catchable else "partial",
                          partial=[results[i].value for i in sorted(results)],
                          details={**first.details, "coverage": states, "successful_indices": sorted(results),
                                   "errors": {str(i): self._fault_view(e) for i, e in errors.items()}})
            error.evidence = [eid]
            raise error
        return [results[i] for i in range(count)]

    def try_block(self, node, env):
        d = node.data
        primary, result, cleanup_result = None, Binding(UNIT), Binding(UNIT)
        try:
            try:
                result = self.eval(d["body"], env)
            except Fault as exc:
                if not exc.catchable or d["catch"] is None:
                    raise
                old = env.get("error")
                env["error"] = Binding(exc.view(self.plan.source), frozenset(exc.evidence), failure=exc)
                recovered = self.event(node, "recovered", exc.evidence, code=exc.code)
                try:
                    result = self.eval(d["catch"], env, control={recovered})
                    result = result.with_roots(result.evidence | {recovered})
                except Returned as returned:
                    returned.binding = returned.binding.with_roots(returned.binding.evidence | {recovered})
                    raise
                finally:
                    if old is None:
                        env.pop("error", None)
                    else:
                        env["error"] = old
        except (Fault, Returned) as exc:
            primary = exc
        if d["final"] and not (isinstance(primary, Fault) and primary.kind == "suspended"):
            previous_cleanup = getattr(self.local, "cleanup", None)
            if isinstance(primary, Fault) and primary.kind in ("cancelled", "budget"):
                self.local.cleanup = previous_cleanup or [100, time.monotonic() + 1]
            try:
                cleanup_result = self.eval(d["final"], env)
            except Fault as cleanup:
                if isinstance(primary, Fault) and not primary.catchable:
                    primary.details["cleanup_failure"] = projection(cleanup.view(self.plan.source))
                else:
                    primary = Fault("CLEANUP", "finally 정리에 실패했습니다.", node,
                                    kind=cleanup.kind,
                                    details={"cleanup": projection(cleanup.view(self.plan.source)),
                                             "cause": projection(primary.view(self.plan.source)) if isinstance(primary, Fault) else None})
            finally:
                self.local.cleanup = previous_cleanup
        if isinstance(primary, Returned):
            primary.binding = primary.binding.controlled(cleanup_result.evidence)
        if primary is not None:
            raise primary
        return result.controlled(cleanup_result.evidence)

    def ordinal(self, key):
        counts = getattr(self.local, "counts", None)
        if counts is None:
            counts = self.local.counts = {}
        value = counts.get(key, 0)
        counts[key] = value + 1
        return value

    def invoke(self, node, args, piped):
        key = f"{node.data['node']}:{node.data['action']}"
        spec = self.plan.registry[key]
        if spec.stateful and spec.stateful(args.value):
            # Serialize invocation AND receipt/evidence, so another branch cannot
            # observe the object mutation before its evidence has been committed.
            with self.foreign_lock:
                return self._timed_invoke(node, args, piped)
        return self._timed_invoke(node, args, piped)

    def _progress_due(self, kind, key):
        """같은 부류·같은 키의 신고는 _PROGRESS_MIN_INTERVAL_S 에 하나. 키가 바뀌면 즉시."""
        now = time.monotonic()
        with self.lock:
            last_key, last_at = self._progress_last.get(kind, (None, 0.0))
            if key == last_key and now - last_at < _PROGRESS_MIN_INTERVAL_S:
                return False
            self._progress_last[kind] = (key, now)
            return True

    def _report_action(self, key):
        """액션 호출 경계의 좌표 신고 — 채팅 표면·표면 티켓이 "지금 어느 낱말을 실행 중인가"를 본다.

        of 는 0(미지) — 함수·each 안의 호출은 정적으로 셀 수 없어 거짓 분모를 만들지 않는다.
        접기 키는 (액션, 회차) — 같은 액션이라도 행이 바뀌거나 each 를 벗어나면 즉시 신고한다(2026-10-27 99회차 수리 검토):
        액션 이름만으로 접으면 each 밖 첫 좌표가 삼켜져 티켓의 옛 행(detail)이 그 액션 내내 남는다(긴 모델 호출이면 분 단위 거짓).
        """
        # 번호 할당부터 버스/티켓 발행까지 한 순서로 보낸다. 실행 자체는 잠그지 않는다.
        with self._progress_lock:
            self._progress_calls += 1
            n = self._progress_calls
            self.local.progress_call_no = n
            detail = getattr(self.local, "row_detail", None)
            if not self._progress_due("action", (key, tuple(sorted(detail.items())) if detail else None)):
                # 접힌 최신 좌표는 다음 계산 beat 앞에서 보낸다.
                self._progress_pending = (n, key, detail)
                return n
            self._progress_pending = None
            try:
                from ibl_progress import report_step
                report_step(self._progress_ticket, n, 0, key, detail=detail)
            except Exception:
                pass
            return n

    def _flush_pending_coordinate(self):
        with self._progress_lock:
            pending, self._progress_pending = self._progress_pending, None
            if not pending:
                return
            n, key, detail = pending
            try:
                from ibl_progress import report_step
                report_step(self._progress_ticket, n, 0, key, detail=detail)
            except Exception:
                pass

    def _report_reused(self, key):
        """영수증 재사용으로 끝난 호출의 좌표 — "(재사용)" 표식(100회차 L100-3): 실행하지 않은 읽기가 "진행 중"으로 보이면 거짓이다."""
        n = getattr(self.local, "progress_call_no", None)
        with self._progress_lock:
            # 늦게 끝난 이전 가지의 영수증으로 최신 좌표/보류 좌표를 덮지 않는다.
            if n is None or n != self._progress_calls:
                return
            self._progress_pending = None
            try:
                from ibl_progress import report_step
                report_step(self._progress_ticket, n, 0, key, detail=getattr(self.local, "row_detail", None), reused=True)
            except Exception:
                pass

    def _row_detail(self, index, count, item):
        label = item if isinstance(item, (str, int, float)) else None
        detail = {"row": index, "rows": count}
        if label is not None:
            detail["row_label"] = str(label)[:40]
        return detail

    def _report_row(self, detail, pure=False):
        """[table:each] 회차 신고 — 좌표는 건드리지 않고 detail 만(규약 정본=ibl_progress).

        pure: 이 each 에 들어온 뒤 아직 액션 호출이 없다 — 좌표의 액션은 끝난(또는 재사용된) 것이므로 둘째 행부터 detail 에
        phase:"compute" 를 실어 표면이 "계산 중"으로 읽게 한다(100회차 L100-3, S7 순수 each 2500행 동안 "self:read 진행 중"이
        떠 있었다). 첫 행은 아직 모른다(행 안 액션이 ms 뒤 올 수 있다) — 표식 없이 둔다."""
        with self._progress_lock:
            # 다른 병렬 가지의 호출이 아직 실행 중이면 "액션 뒤 계산 중"이라고 할 수 없다.
            pure = pure and not self._progress_active
            if pure:
                self._flush_pending_coordinate()
            if not self._progress_due("row", (detail["row"], detail["rows"])):
                return
            try:
                from ibl_progress import beat
                beat({**detail, "phase": "compute"} if pure and detail.get("row", 1) > 1 else detail)
            except Exception:
                pass

    def _timed_invoke(self, node, args, piped):
        started = time.monotonic()
        previous = getattr(self.local, "progress_call_no", None)
        with self._progress_lock:
            call_no = self._report_action(f"{node.data['node']}:{node.data['action']}")
            self._progress_active.add(call_no)
        try:
            return self._invoke(node, args, piped)
        finally:
            with self._progress_lock:
                self._progress_active.discard(call_no)
                self.local.progress_call_no = previous
            with self.lock:
                ended = time.monotonic()
                cell = self.tool_time.setdefault(node.id, [0, 0.0, f"{node.data['node']}:{node.data['action']}", []])
                cell[0] += 1
                cell[1] += ended - started
                cell[3].append((started, ended))

    def _invoke(self, node, args, piped):
        key = f"{node.data['node']}:{node.data['action']}"
        spec = self.plan.registry[key]
        from ibl_callable_contract import normalize, selected, problems
        args = Binding(normalize(spec.contract, args.value), args.evidence)
        from ibl_callable_contract import pipe_receiver
        args = self.inject(node, args, pipe_receiver(spec.contract, args.value), piped)
        if spec.contract.get("adapter", {}).get("protocol") == "core-table/2" and "items" in args.value:
            from ibl_v2_types import rows_value
            args = Binding({**args.value, "items": rows_value(args.value["items"])}, args.evidence)
        if spec.dependency and 'dependency_snapshot' not in node.data:
            raise Fault('DEPENDENCY_CONTRACT', '동적 부품의 실행 자산은 먼저 명시 계약으로 검사해야 합니다.',
                        node, kind='protocol')
        dependency = node.data.get('dependency_snapshot')
        dependency_args = node.data.get('dependency_args', {})
        if node.data.get('dependency_bindings'):
            from common.value_semantics import values_equal
            choices = [b for b in node.data['dependency_bindings']
                       if all(k in args.value and values_equal(args.value[k], v) for k,v in b['args'].items())]
            if not choices:
                raise Fault('DEFINITION_CHANGED', '검사한 부품 인자·자산 선택과 다릅니다.', node, kind='protocol')
            choice = max(choices, key=lambda b: len(b['args']))
            dependency, dependency_args = choice['snapshot'], choice['args']
        deferred = isinstance(dependency, dict) and dependency.get('binding') == 'invocation'
        if deferred and not spec.invocation_dependency:
            raise Fault('DEPENDENCY_CONTRACT', '실행 시점 자산 바인딩에 지문 제공자가 없습니다.', node, kind='protocol')
        if spec.dependency and not deferred and spec.dependency(dependency_args) != dependency:
            raise Fault('DEFINITION_CHANGED', '참조한 실행 자산이 검사 이후 변경되었습니다.', node, kind='protocol')
        contract = selected(spec.contract, args.value)
        if spec.specialize and not node.data.get('target'):
            contract = spec.specialize(contract, args.value)
        if contract.get('completion'):
            from ibl_v2_component import normalize as component_contract
            from ibl_v2_component_runtime import execute
            definition = component_contract({'name': key, 'revision': digest([contract, dependency])},
                                            contract, producer='vocabulary')
            return execute(self, key, node, args.value,
                           lambda: self._invoke_contract(node, args, spec, contract, dependency), contract=definition)
        return self._invoke_contract(node, args, spec, contract, dependency)

    def _invoke_contract(self, node, args, spec, contract, dependency):
        key = f"{node.data['node']}:{node.data['action']}"
        from ibl_callable_contract import problems
        from ibl_value_checks import value_problems
        if getattr(self.local, 'pure_required', False) and set(contract['effects']) - {'pure'}:
            raise Fault('PURE_EXPRESSION', '순수 콜백 자리에서 효과 있는 부품을 호출할 수 없습니다.', node)
        failures = problems(contract, args.value) + value_problems(contract, args.value, self.plan.registry, self.plan.definitions)
        failures += [f"필수 인자 누락: {k}" for k in contract.get("required", contract["params"]) if k not in args.value]
        if failures:
            raise Fault('ARGUMENT_CONTRACT', '; '.join(failures), node)
        if not contract.get('open_params') and args.value.keys() - contract['params'].keys():
            raise Fault('UNKNOWN_ARGUMENT', '계약에 없는 명명 인자입니다.', node)
        for name, value in args.value.items():
            guard(value, contract['params'].get(name, 'Unknown'), f'{key}.{name}')
        from common.expression_ops import callable_identity
        request_value = callable_identity
        # 인자 전체는 여기서 한 번만 훑는다(긴문장 L18-1). 요청 해시·재사용 열쇠·차원별 지문이 저마다 인자를
        # 다시 포장·직렬화해 행 목록을 네 번 훑었고, 2천 행 표 변환 한 번이 0.3초였다(실제 표 처리는 그 2%).
        # 신원에는 인자의 지문만 싣는다 — 같은 인자면 같은 지문이므로 재사용·재개 판정의 뜻은 그대로다.
        request = {"action": key, "args": {"digest": digest_packed(request_value(args.value, node_map=self.journal.node_map if self.journal else None))},
                   "plan": self.plan.fingerprint}
        if getattr(self.local, "components", ()):
            request["components"] = digest(self.local.components)
        target_node = node.data.get("target")   # @별칭 — 어느 몸에서 실행하나(같은 인자라도 다른 몸의 영수증과 섞이지 않게 신원에 싣는다)
        run_extra = {"target_node": target_node} if target_node else {}
        if target_node:
            request["target_node"] = target_node
        invocation_dependency = spec.invocation_dependency(args.value) if spec.invocation_dependency else None
        if invocation_dependency is not None:
            request['invocation_dependency'] = invocation_dependency
        self.local.invocation_dependency = invocation_dependency
        model_identity = spec.model_identity() if spec.model_identity else None
        if model_identity is not None:
            request['model_identity'] = model_identity
        request_hash = digest(request)
        # The whole program may change, but the selected call contract and its
        # dependency snapshot must still describe the same value/effect boundary.
        reuse_identity = {"action": key, "args": request["args"],
                            "target_node": target_node,
                            "contract": contract,
                            "model_identity": model_identity,
                            "dependency": dependency,
                            "semantics": {k: self.plan.dependencies[k]
                                          for k in ("core", "edition", "semantics", "expressions")}}
        if invocation_dependency is not None:
            reuse_identity['invocation_dependency'] = invocation_dependency
        reuse_key = digest(reuse_identity)
        reuse_parts = {name: digest(value) for name, value in reuse_identity.items()}
        stateful = bool(spec.stateful and spec.stateful(args.value))
        parents = args.evidence | (self.foreign_evidence if stateful else frozenset())
        # 실행 시점에 실제로 넘어간 짧은 글자 인자 — 평가 원장이 계산된 경로·주소를 본다(ep4211:
        # `path:$out+"/report.md"` 는 코드 글자에 없어 재독이 '안 한 일'로 판정됐다). 이름을 고르지 않고
        # 길이로만 가른다: 긴 글자는 본문이지 대상이 아니다. 순수 부품도 완료 원천의 신원이 필요하다.
        targets = {name: value for name, value in list(args.value.items())[:24]
                   if isinstance(value, str) and value and len(value) <= 300}
        eid = self.event(node, "invoke", parents, action=key,
                         effects=contract["effects"], request_hash=request_hash,
                         **({"targets": dict(list(targets.items())[:8])} if targets else {}))
        from ibl_v2_component_runtime import observation_duties
        observation_obligations = observation_duties(self, key, args.value, eid)
        tool_evidence = {}
        external = contract["effects"] != ["pure"]
        read_only = (contract["effects"] == ["read_external"] or
                     (contract["effects"] == ["unknown"] and spec.reusable is not None
                      and spec.reusable(args.value)))
        model_only = contract['effects'] == ['model'] and model_identity is not None
        reusable_read = (read_only or model_only) and not contract.get('per_run', False)
        from ibl_run_journal import call_resources, resources_overlap, request_fingerprints, receipt_access_scope
        state_change = external and not read_only and contract['effects'] != ['model']
        footprint = call_resources(spec, contract, args.value, 'write' if state_change else 'read')
        if model_only:
            footprint = []  # All source values are arguments; no hidden external reads.
        from ibl_run_journal import resource_state
        # 읽기 직전의 파일 지문 — 영수증에 싣고, 빌릴 때 같은지 본다(L33-2).
        freshness = resource_state(footprint) if reusable_read and not model_only else None
        stale = None
        if state_change:
            with self.lock:
                self.reuse_writes.append(footprint)

        def failed(error):
            # A failed external leaf is a missing source even when a surrounding
            # catch returns a normal value. Keep the same fact on receipt reuse;
            # ordinary pure computation faults do not imply missing sources.
            exc = error if isinstance(error, Fault) else Fault("VALUE", str(error), node)
            failure = self.event(node, "tool_failure", set(exc.evidence) | {eid},
                                 action=key, code=exc.code, failure_kind=exc.kind,
                                 incomplete=external or exc.kind == "partial")
            exc.evidence = [failure]
            if stateful:
                self.foreign_evidence = frozenset({failure})
            return exc

        route = getattr(self.local, "route", ())
        mapped_node = node.id
        if self.journal and self.journal.node_map:
            mapping = self.journal.node_map
            mapped_node = mapping.get(node.id, node.id)
            def remap(value):
                return tuple(remap(v) for v in value) if isinstance(value, tuple) else mapping.get(value, value) if isinstance(value, str) else value
            route = remap(route)
        call_id = digest([route, mapped_node, self.ordinal(node.id)])
        receipt, source = None, "journal"
        if self.journal and external:
            receipt = self.journal.begin(call_id, request_hash, getattr(self.local, "cleanup", None) is not None,
                                         reusable=reusable_read, state_change=state_change, resources=footprint,
                                         request_parts=request_fingerprints(request),
                                         call_info={"action": key, "location": span(self.plan.source, node)})
        if self.replay and external and receipt is None:
            with self.lock:
                receipt = next((r for r in self.recorded if r["request_hash"] == request_hash), None)
                if receipt is not None:
                    self.recorded.remove(receipt)
            if receipt is None:
                raise Fault("REPLAY_MISSING", "이 입력·정의의 실행 기록이 없습니다. 외부 호출하지 않습니다.", node, kind="protocol")
            source = "replay"
        with self.lock:
            invalidated = any(resources_overlap(footprint, writes) for writes in self.reuse_writes)
        if (receipt is None and external and self.reusable and reusable_read and not invalidated
                and (not model_only or self.reuse_models)):
            # Explicit value-only model contracts share successful receipt reuse.
            # Failed or configuration-changing calls never become candidates.
            with self.lock:
                hit = self.reusable.get(reuse_key)
                if model_only and reuse_key in self.consumed_model_receipts:
                    hit = None
                if hit is not None and "value" in hit and not hit.get("reuse_disabled") and freshness:
                    old_state = hit.get('resource_state')
                    if old_state is None:
                        stale = 'freshness_unknown'      # 지문이 없는 옛 영수증은 빌리지 않는다
                    elif old_state != freshness:
                        stale = 'resource_changed'
                    if stale:
                        hit = None
                if hit is not None and "value" in hit and not hit.get("reuse_disabled"):
                    receipt, source = hit, "reuse"
                    if model_only:
                        self.consumed_model_receipts.add(reuse_key)
        if receipt is None and self.reuse_run and reusable_read:
            if invalidated:
                reason = "overlapping_write"
            elif stale:
                reason = stale
            elif model_only and not self.reuse_models:
                reason = "fresh_model_requested"
            elif model_only and reuse_key in self.consumed_model_receipts:
                reason = "model_receipt_consumed"
            else:
                reason = "no_matching_receipt"
            candidates = [r for r in self.reusable.values() if r.get('action') == key]
            differences = []
            for old in candidates:
                parts = old.get('reuse_parts')
                changed = ([name for name in reuse_parts if parts.get(name) != reuse_parts[name]]
                           if parts else ['identity_changed_or_legacy_receipt'])
                differences.append({'receipt': old.get('reuse_key'), 'changed': changed})
            with self.lock:
                self.reuse_skipped_total += 1
                if len(self.reuse_skipped) < 20:
                    skipped = {'action': key, 'location': span(self.plan.source, node),
                               'reason': reason, 'candidates': differences[:5],
                               'candidates_total': len(differences)}
                    if stale == 'resource_changed':
                        old_state = {e[0]: e[1:] for e in (self.reusable.get(reuse_key) or {}).get('resource_state') or []}
                        skipped['changed_resources'] = [e[0] for e in freshness if old_state.get(e[0]) != e[1:]]
                    self.reuse_skipped.append(skipped)
        if (receipt is not None and "value" in receipt and source == "journal"
                and contract.get("deferred_observation") and not self.replay):
            # Restore the staged local checkpoint, but preserve the original
            # observed result for downstream receipt identities. The adapter's
            # commit is monotonic at this original timestamp, so an old resume
            # cannot roll back a newer successful observation.
            if spec.authorize:
                spec.authorize()
            from execution_commit import bind_scope
            self.local.invocation_id = call_id
            with bind_scope(self.commit_scope, receipt.get("observed_at"), obligations=observation_obligations):
                spec.run(self, copy.deepcopy(args.value), **run_extra)
        if receipt is not None:
            if stateful:
                raise failed(Fault("PY_STATE_EXPIRED", "외부 실행 상태는 새 워커에 복원되지 않습니다. export한 값을 새 입력으로 사용하세요.", node, kind="protocol"))
            if spec.authorize:
                spec.authorize()
            from ibl_v2_ir import unpack
            self.event(node, "receipt_reused", [eid], call_id=call_id, source=source,
                       **({"run_id": self.reuse_run} if source == "reuse" else {}))
            self._report_reused(key)
            if source == "reuse":
                receipt = {**receipt, "request_hash": request_hash}
                with self.lock:
                    self.reused_calls += 1
                    self.reused_model_calls += int(model_only)
                if self.journal:
                    self.journal.finish(call_id, receipt)  # 새 실행의 저널도 완결 — 이 실행을 다시 resume/reuse 할 수 있다
            with self.lock:
                self.recordings.append(receipt)
            if "error" in receipt:
                error = receipt["error"]
                restored = Fault(error["code"], error["message"], node, kind=error["kind"],
                                 partial=unpack(receipt["partial"]), details=error.get("details"))
                raise failed(restored)
            value = unpack(receipt["value"])
            guard(value, contract["result"], f"{key} 반환")
            tool_evidence = copy.deepcopy(receipt.get("evidence", {}))
            if 'model_usage' in tool_evidence:
                tool_evidence['original_model_usage'] = tool_evidence.pop('model_usage')
        else:
            usage = []
            try:
                self.local.invocation_id = call_id
                from execution_commit import bind_scope
                from datetime import datetime
                observed_at = datetime.now().isoformat()
                from model_call_context import capture_usage
                with capture_usage() as usage:
                    try:
                        from thread_context import invocation_scope
                        with bind_scope(self.commit_scope, observed_at, obligations=observation_obligations), invocation_scope(
                                self.journal.run_id if self.journal else None, call_id, request_hash):
                            value = spec.run(self, copy.deepcopy(args.value), **run_extra)
                    finally:
                        # 호출 뒤 첫 걸음은 바로 취소를 확인한다 — 호출 도중 들어온 취소가
                        # 간격에 가려 성공으로 끝나지 않게(걸음 간격 확인은 순수 계산 구간에만 적용된다).
                        self._next_cancel_check = 0.0
                        with self.lock:
                            self.model_usage.extend(usage)
                        if usage:
                            self.event(node, 'model_usage', [eid], calls=copy.deepcopy(usage))
                from ibl_v2_adapters import Adapted
                if isinstance(value, Adapted):
                    tool_evidence, value = value.evidence, value.value
                if usage:
                    tool_evidence = {**tool_evidence, 'model_usage': copy.deepcopy(usage)}
                receipt_adapter = contract.get("script_contract", contract).get("adapter", {})
                if receipt_adapter.get("receipt_ref") and self.journal and isinstance(value, dict):
                    value = {**value, "_receipt_ref": {"run_id": self.journal.run_id, "call_id": call_id}}
                guard(value, contract["result"], f"{key} 반환")
                if external:
                    receipt = {"request_hash": request_hash, "value": pack(value), "evidence": tool_evidence,
                               "action": key, "reuse_key": reuse_key, "reuse_parts": reuse_parts,
                               "access_scope": receipt_access_scope(),
                               "producer": args.value.get("id"),
                               **({"resource_state": freshness} if freshness else {})}
                    if freshness:
                        stable = all(len(r) > 3 and r[3] is not None for r in freshness) and freshness == resource_state(footprint)
                        receipt['reuse_disabled'] = not stable
                        tool_evidence = {**tool_evidence, 'source_snapshot': freshness,
                                         **({'incomplete': True, 'warning': '자료를 읽는 동안 원천이 변경되었거나 내용 지문을 확인하지 못했습니다.'} if not stable else {})}
                        receipt['evidence'] = tool_evidence
                    if model_only:
                        receipt['model_identity'] = model_identity
                        receipt['reuse_disabled'] = spec.model_identity() != model_identity
                    if contract.get("deferred_observation"):
                        receipt["observed_at"] = observed_at
                    if self.journal:
                        self.journal.finish(call_id, receipt)
                    with self.lock:
                        self.recordings.append(receipt)
            except Exception as error:
                if isinstance(error, Fault) and error.kind == "suspended":
                    if self.journal and external:
                        self.journal.finish(call_id, {"suspended": True, "request_hash": request_hash,
                                                     "reason": error.code, "details": projection(error.details)})
                    self.event(node, "suspended", [eid], reason=error.code)
                    raise
                exc = failed(error)
                receipt = {"request_hash": request_hash, "action": key, "reuse_key": reuse_key,
                           "error": projection(exc.view(self.plan.source)), "partial": pack(exc.partial),
                           "effects": list(contract["effects"]),
                           **({'evidence': {'model_usage': copy.deepcopy(usage)}} if usage else {})}
                # Keep resolved values, including pure calculations made before the failed leaf.
                # Callables are not portable values; never turn their display form into input.
                try:
                    receipt['arguments'] = pack(args.value)
                    receipt['argument_evidence'] = list(args.evidence)
                    # Persist the input status as well: original event ids are not
                    # necessarily present in the trace of a later journal replay.
                    with self.lock:
                        ancestors = {event['id']: event for event in self.trace}
                    pending, seen = list(args.evidence), set()
                    receipt['argument_incomplete'] = False
                    while pending:
                        parent = pending.pop()
                        if parent in seen:
                            continue
                        seen.add(parent)
                        event = ancestors.get(parent, {})
                        receipt['argument_incomplete'] |= bool(event.get('incomplete')) or not event
                        pending.extend(event.get('parents', []))
                except Fault:
                    receipt['arguments_unavailable'] = '호출 인자의 손실 없는 값 전송을 지원하지 않습니다.'
                if self.journal and external:
                    self.journal.finish(call_id, receipt)
                with self.lock:
                    self.recordings.append(receipt)
                raise exc
        if tool_evidence:
            eid = self.event(node, "tool_evidence", [eid], **tool_evidence)
        if (contract.get('adapter', {}).get('protocol') == 'ibl-script/2' and isinstance(args.value.get('id'), str)
                and args.value.get('op', 'run') == 'run'):
            self.event(node, 'capability_result', [eid], capability_id='script:' + args.value['id'], success=True)
        if stateful:
            self.foreign_evidence = frozenset({eid})
        return Binding(value, frozenset({eid}))

    def failed_execution(self, exc):
        """Late infrastructure errors retain the same execution and receipts."""
        from ibl_v2_completion import undetermined
        diagnostic = projection(exc.view(self.plan.source)) if isinstance(exc, Fault) else {
            'code': 'EXECUTION_FINALIZATION', 'kind': 'protocol', 'message': str(exc)}
        out = {**(self.last_out or {}), 'edition': 2, 'success': False, 'executed': True,
               'error': str(exc), 'diagnostic': diagnostic, 'evidence': self.trace,
               'source_complete': not any(e.get('incomplete') for e in self.trace),
               'source_map': self.source_map, 'recordings': self.recordings,
               'plan_hash': self.plan.fingerprint}
        if self.completion:
            out['completion'] = undetermined(self.completion, exc)
        if self.journal:
            out['resume'] = {'run_id': self.journal.run_id}
            try:
                out['run_status'] = self.journal.complete(out)
            except Exception as finalization:
                out['finalization_error'] = str(finalization)
        return out

    def run(self):
        try:
            with self.resources, execution_scope():
                return self._run()
        except Exception as exc:
            if not self.execution_started:
                raise
            return self.failed_execution(exc)

    def _partial_transport(self, value):
        """Nested failures use the same lossless partial protocol as the root."""
        if value is UNIT:
            return {}
        protocol = wire_protocol(value)
        if protocol in self.value_protocols:
            return {"partial_wire": {"protocol": protocol, "data": pack(value)}}
        return {"partial_wire_error": {
            "code": "VALUE_PROTOCOL_UNSUPPORTED", "required_protocol": protocol,
            "value_preview": projection(value)}}

    def _fault_view(self, exc):
        return {**projection(exc.view(self.plan.source)), **self._partial_transport(exc.partial)}

    def _run(self):
        from ibl_v2_requirements import require_wire
        self.plan = require_wire(self.plan, self.value_protocols)
        if self.plan.issues:
            from ibl_v2_analysis import rejection_message, compact_check
            rejected = {**compact_check(self.plan), "success": False,
                        "error": rejection_message("실행 전 검사에서 거절했습니다", self.plan.issues)}
            wire = next((issue for issue in self.plan.issues if issue['code'] == 'VALUE_PROTOCOL'), None)
            if wire:
                rejected['diagnostic'] = {**wire, 'kind': 'protocol'}
            return rejected
        if set(self.inputs) != set(self.plan.input_types):
            return {"edition": 2, "success": False, "error": "컴파일 시 입력 서명과 실행 입력이 다릅니다.", "executed": False}
        try:
            from ibl_progress import claim
            self._progress_ticket = claim()   # 표면 티켓이 있으면 좌표 소유권(없으면 None — 신고는 버스로만)
        except Exception:
            self._progress_ticket = None
        self.execution_started = True
        result = None
        try:
            from ibl_v2_types import infer, compatible
            for key, value in self.inputs.items():
                pack(value)
                if not compatible(infer(value), self.plan.input_types[key]):
                    raise Fault("INPUT_TYPE", f"컴파일 시 입력 타입과 다릅니다: {key}", kind="protocol")
            env = {}
            for key, value in self.inputs.items():
                note = self.input_evidence.get(key)
                if note:
                    from ibl_v2_completion import reference_binding
                    env[key] = reference_binding(self, value, note)
                else:
                    env[key] = Binding(value)
            result = self.frame(self.plan.root, env)
            if wire_protocol(result.value) not in self.value_protocols:
                raise Fault('VALUE_PROTOCOL_UNSUPPORTED', '소비자가 외부 참조 wire를 지원하지 않습니다. 실행 안에서 값/파일로 변환하세요.', kind='protocol', details={'value_preview': projection(result.value)})
            wire = pack(result.value)
            out = {"success": True, "value": projection(result.value),
                   "value_wire": {"protocol": wire_protocol(result.value), "data": wire}}
        except Fault as exc:
            out = {"success": False, "error": str(exc), "diagnostic": projection(exc.view(self.plan.source))}
            if exc.kind == "suspended":
                out.update(status="suspended", suspended=True, waiting=projection(exc.details))
            from ibl_v2_analysis import runtime_hint
            if (hint := runtime_hint(exc)) and isinstance(out["diagnostic"], dict):
                out["diagnostic"].setdefault("hint", hint)
            out.update(self._partial_transport(exc.partial))
        out.update({"edition": 2, "executed": True, "plan_hash": self.plan.fingerprint,
                    "source_complete": not any(e.get("incomplete") for e in self.trace),
                    "evidence": self.trace, "source_map": self.source_map, "recordings": self.recordings,
                    "usage": {"steps": self.budget.used_steps, "rows": self.budget.used_rows,
                              "elapsed_ms": round((time.monotonic() - self.budget.started) * 1000)}})
        self.last_out = out
        if self.completion:
            from ibl_v2_completion import evaluate
            try:
                out['completion'] = evaluate(self, result, out['success'])
            except Exception as exc:
                from ibl_v2_completion import undetermined
                out['completion'] = undetermined(self.completion, exc)
            out['usage'].update(steps=self.budget.used_steps, rows=self.budget.used_rows,
                                elapsed_ms=round((time.monotonic() - self.budget.started) * 1000))
        from ibl_v2_component_runtime import report as component_report
        component_report(self, out, result)
        from ibl_v2_component_runtime import export_certificates
        certificates = export_certificates(self, result)
        if certificates['obligations'] or certificates['uninspected']:
            out['component_certificates'] = certificates
        checks = [e for e in self.trace if e.get('kind') == 'assertion']
        entries = self.plan.dependencies.get('source_map', [])[1:]
        used = [{'id': 'fn:' + e['name'], 'success': e['success'], 'source_hash': digest(self.plan.source[source['start']:source['end']]), 'function_ref': source.get('function_ref')}
                for e in self.trace if e.get('kind') == 'function_result'
                for source in entries if source['start'] <= e['definition_start'] < source['end']]
        used += [{'id': e['capability_id'], 'success': e['success']} for e in self.trace if e.get('kind') == 'capability_result']
        if used:
            out['capability_usage'] = used
        if checks:
            out['verification'] = {'plan_hash': self.plan.fingerprint,
                                   'value_hash': digest(out.get('value_wire')),
                                   'checks': checks,
                                   'source_snapshots': [r for e in self.trace for r in e.get('source_snapshot', [])],
                                   'scope': 'declared_assertions', 'source_complete': out['source_complete']}
        if self.model_usage:
            from model_call_context import summarize_usage
            out['usage']['model'] = summarize_usage(self.model_usage)
        costs = sorted(self.budget.by_node.items(), key=lambda item: (-item[1], item[0]))
        out['usage']['limits'] = {"steps": self.budget.steps, "rows": self.budget.rows}
        out['usage']['steps_by_span'] = [
            {"node_id": key, "steps": count, "location": self.source_map.get(key, {})}
            for key, count in costs[:20]]
        out['usage']['steps_other'] = self.budget.used_steps - sum(n for _, n in costs[:20])
        # 한 줄의 람다는 하위 노드 여러 칸으로 흩어진다 — 줄로 모으면 비싼 문장이 바로 보인다(긴문장 L9-4).
        lines = {}
        for key, count in costs:
            where = self.source_map.get(key, {})
            if where.get('line') is not None:
                place = (where.get('source_hash'), where['line'])
                lines[place] = lines.get(place, 0) + count
        top = sorted(lines.items(), key=lambda item: (-item[1], item[0][1]))[:10]
        out['usage']['steps_by_line'] = [{"line": line, "steps": count, "source_hash": source} for (source, line), count in top]
        # 걸음 수는 식 평가만 센다 — 표 변환·읽기 같은 도구 호출은 한 걸음이어도 행 수만큼 시간이 든다(긴문장 L18-1).
        # 느린 줄은 걸음이 아니라 시간으로 가리킨다. 안쪽 호출을 품은 줄(each 본문 등)은 그 시간을 포함한다.
        # `ms` 는 호출 시간의 합이라 병렬 가지·each parallel 에서는 벽시계보다 크다(긴문장 L29-4: 15초 대기 둘이 30초로
        # 읽혔다). 호출이 겹친 줄에는 겹침을 한 번만 센 `wall_ms` 를 함께 싣는다 — 기다린 시간은 wall_ms 다.
        slow = {}
        for node_id, (calls, seconds, action, spans) in self.tool_time.items():
            where = self.source_map.get(node_id, {})
            if where.get('line') is not None:
                cell = slow.setdefault((where.get('source_hash'), where['line']), [0, 0.0, [], []])
                cell[0] += calls
                cell[1] += seconds
                if action not in cell[2]:
                    cell[2].append(action)
                cell[3].extend(spans)
        rows = []
        for (source, line), (calls, seconds, actions, spans) in \
                sorted(slow.items(), key=lambda item: (-item[1][1], item[0][1]))[:10]:
            row = {"line": line, "ms": round(seconds * 1000), "calls": calls, "actions": actions, "source_hash": source}
            wall = round(_covered_seconds(spans) * 1000)
            if wall < row["ms"]:
                row["wall_ms"] = wall
            rows.append(row)
        out['usage']['tool_ms_by_line'] = rows
        notes = [{'event_id': event['id'], 'location': self.source_map.get(event['node_id'], {}),
                  'warning': event['warning'][:1000]}
                 for event in self.trace if event.get('warning')]
        if notes:
            out['execution_notes'] = notes[:20]
            out['execution_notes_omitted'] = max(0, len(notes) - 20)
        if self.completion:
            with self.commit_scope.lock:
                for obligation in out['completion']['obligations']:
                    name = self.completion_scope + obligation['id']
                    if obligation['status'] == 'satisfied':
                        self.commit_scope.certified.add(name)
                        self.commit_scope.certified_evidence[name] = obligation['evidence_refs']
        if self.owns_commit_scope and out.get('success'):
            try:
                if out.get('source_complete'):
                    self.commit_scope.commit()
                elif self.completion:
                    self.commit_scope.commit(satisfied=self.commit_scope.certified,
                                             evidence=self.commit_scope.certified_evidence)
            except Exception as exc:
                out.update(success=False, error=f"관측 원장 확정 실패: {exc}")
        self.commit_scope.report(out, owner=self.owns_commit_scope)
        if self.plan.preflight.get('warnings'):
            out['precheck_warnings'] = self.plan.preflight['warnings']
        if self.journal and self.journal.repair_plan:
            out['repair'] = self.journal.repair_plan
        if self.reuse_run:
            out["reuse"] = {"run_id": self.reuse_run, "reused_calls": self.reused_calls, "candidates": len(self.reusable)}
            if self.reuse_skipped_total:
                out['reuse'].update(skipped=self.reuse_skipped, skipped_total=self.reuse_skipped_total)
        if self.reused_model_calls:
            out['reuse']['model_calls'] = self.reused_model_calls
        if self.journal:
            out["resume"] = {"run_id": self.journal.run_id}
            out["resumed"] = self.journal.resuming
            out["run_status"] = self.journal.complete(out)
            reusable = self.journal.reuse_summary()
            if (reusable['read_calls'] or reusable.get('model_calls') or reusable['state_change_possible']) and out["run_status"] not in {"blocked", "uncertain"}:
                out["continuation"] = {
                    **({"reuse_args": {"reuse": {"run_id": self.journal.run_id}}} if reusable['read_calls'] or reusable.get('model_calls') else {}),
                    **reusable,
                    "hint": "프로그램 수정 뒤 이전 읽기·모델 결과를 이어 쓸 때 reuse_args를 요청에 합치세요. "
                            "현재 자료를 새로 조회해야 하면 쓰지 마세요. 쓰기 자원과 겹치는 이전·동시 읽기(자원 미상은 전체)와 실행 시점 값은 제외합니다. 쓰기 호출은 재사용하지 않습니다. model_reuse 선언 모델은 입력·설정이 같으면 재사용하며 reuse.models:false로 새로 판단합니다. "
                            "동일 코드·inputs의 기록 재개는 resume입니다. 확인된 실패도 그대로 복원합니다."}
        return out
