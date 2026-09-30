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
from concurrent.futures import wait, FIRST_COMPLETED
from execution_workers import create_executor
from ibl_v2_ir import (Fault, UNIT, Unit, ResultValue, digest, pack, projection, span,
                       parallel_branches)
from ibl_v2_expr import (Builtin, Closure, binary, boolean, number, scalar_text,
                         pure_call, check_arity, free_names)
from ibl_v2_types import guard


from common.expression_eval import Binding, ExpressionEvaluator


class Returned(BaseException):
    def __init__(self, binding):
        self.binding = binding


@dataclass
class Budget:
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
        limits = {"steps": 1000000, "rows": 100000}
        if (not isinstance(value, dict) or set(value) - limits.keys()
                or any(type(v) is not int or not 1 <= v <= limits[k] for k, v in value.items())):
            raise Fault("BUDGET_ARGUMENT", "budget은 steps(1~1000000), rows(1~100000) 정수만 지정합니다.", kind="compile")
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
                hint = ("도구의 필터·검색으로 입력을 좁히거나 전건을 여러 실행으로 나누세요. "
                        "요청 budget:{steps:...,rows:...}로 한도를 명시할 수도 있습니다(최대 steps 1000000·rows 100000). "
                        "usage.steps_by_span에서 비용 위치를 확인하세요. 전건 처리가 필요하면 take로 조용히 잘라내지 마세요.")
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


class Runtime(ExpressionEvaluator):
    def __init__(self, plan, inputs=None, *, cancel_check=None, budget=None,
                 recordings=None, replay=False, journal=None, reusable=None, reuse_run=None,
                 input_evidence=None, value_protocols=None, reuse_models=True):
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
        self.budget = budget or Budget()
        self.trace, self.recordings = [], []
        self.model_usage = []
        self.reuse_models = reuse_models
        self.reused_model_calls = 0
        self.consumed_model_receipts = set()
        self.expression_events = {}
        self.source_map = {}
        self.replay, self.recorded = replay, list(recordings or [])
        self.lock = threading.RLock()
        self.local = threading.local()
        from execution_commit import current_scope, CommitScope
        self.commit_scope = current_scope() or CommitScope()
        self.owns_commit_scope = current_scope() is None

    def event(self, node, kind, parents=(), *, coalesce=False, **extra):
        with self.lock:
            key = (node.id, kind, tuple(sorted(parents)))
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
        if self.cancel_check and self.cancel_check():
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
            eid = self.event(node, node.kind, result.evidence | dependencies, coalesce=True)
            roots = frozenset({eid})
            return Binding(result.value, roots)
        except Returned as returned:
            roots = returned.binding.evidence | dependencies
            returned.binding = Binding(returned.binding.value, frozenset(roots))
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
        value = self.expression(node, env)
        if value is not NotImplemented:
            return value
        if kind == "sequence":
            result, parents = Binding(UNIT), set()
            for statement in d["statements"]:
                try:
                    result = sub(statement)
                except Returned as returned:
                    returned.binding = Binding(returned.binding.value, returned.binding.evidence | parents)
                    raise
                except Fault as exc:
                    exc.evidence = sorted(set(exc.evidence) | parents)
                    raise
                parents.update(result.evidence)
            return Binding(result.value, frozenset(parents))
        if kind == "bind":
            env[d["name"]] = sub(d["value"])
            return Binding(UNIT, env[d["name"]].evidence)
        if kind == "def":
            return Binding(UNIT)
        if kind == "assert":
            condition = sub(d["condition"])
            if not boolean(condition.value):
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
                return Binding(result.value, result.evidence | {eid})
        if kind == "parallel":
            nodes = list(parallel_branches(node))
            results = self.fanout(node, len(nodes), lambda i: self.frame(nodes[i], env.copy()), min(8, len(nodes)))
            return Binding([b.value for b in results], self.parents(results))
        if kind == "call":
            args = sub(d["params"])
            if d["node"] == "table" and d["action"] == "each":
                return self.each(node, env, args, piped)
            if d["node"] == "fn" and "symbol" in d:
                definition = self.plan.functions[d["symbol"]]
                params = definition.data["params"]
                args = self.inject(node, args, next(iter(params), None), piped)
                unknown = args.value.keys() - params.keys()
                missing = [k for k, default in params.items() if k not in args.value and default is None]
                if unknown or missing:
                    raise Fault("FUNCTION_ARGUMENTS", "함수 인자가 계약과 다릅니다.", node,
                                details={"unknown": sorted(unknown), "missing": missing})
                local = {k: Binding(v, args.evidence) for k, v in args.value.items()}
                for name, default in params.items():
                    if name not in local:
                        local[name] = self.eval(default, {})
                depth = getattr(self.local, "depth", 0)
                self.local.depth = depth + 1
                try:
                    result = self.frame(definition.data["body"], local)
                    eid = self.event(node, "function_result", result.evidence | args.evidence,
                                     name=d["action"], definition_start=definition.start, success=True,
                                     **returned_shape(result.value))
                    return Binding(result.value, frozenset({eid}))
                except Fault as exc:
                    eid = self.event(node, "function_result", exc.evidence,
                                     name=d["action"], definition_start=definition.start, success=False)
                    exc.evidence = [eid]
                    exc.frames.append({"function": d["action"], "call": span(self.plan.source, node),
                                       "definition": span(self.plan.source, definition)})
                    raise
                finally:
                    self.local.depth = depth
            return self.invoke(node, args, piped)
        if kind == "if":
            condition = sub(d["value"])
            try:
                result = self.eval(d["body"] if boolean(condition.value) else d["otherwise"],
                                   env, control=condition.evidence)
                return Binding(result.value, result.evidence | condition.evidence)
            except Returned as returned:
                returned.binding = Binding(returned.binding.value, returned.binding.evidence | condition.evidence)
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
                return Binding(result.value, result.evidence | parents)
            except Returned as returned:
                returned.binding = Binding(returned.binding.value, returned.binding.evidence | parents)
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
                        env[name] = Binding(binding.value, binding.evidence | parents)
                if old_i is None:
                    env.pop("i", None)
                else:
                    env["i"] = old_i
            return Binding(UNIT, frozenset(parents))
        raise Fault("IR", f"지원하지 않는 구문: {kind}", node, kind="protocol")

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
        return Binding({**args.value, receiver: piped.value}, args.evidence | piped.evidence)

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
        def row(index):
            self.budget.tick(row=True)
            local = {**env, "it": Binding(items[index], args.evidence), "i": Binding(index)}
            result = self.frame(node.data["body"], local)
            if mode == "flat_map":
                guard(result.value, "List", "flat_map 반환")
            return result
        results = self.fanout(node, len(items), row, options.get("parallel", 1), collect)
        if mode == "effect":
            value = UNIT
        elif mode == "flat_map":
            value = [v for result in results for v in result.value]
        else:
            value = [b.value for b in results]
        return Binding(value, self.parents(results) | args.evidence)

    def fanout(self, node, count, fn, workers, collect=False):
        results, errors, states = {}, {}, ["pending"] * count
        depth = getattr(self.local, "depth", 0)
        control = getattr(self.local, "control", frozenset())
        nested = getattr(self.local, "parallel", False)
        route = getattr(self.local, "route", ()) + ((node.id, self.ordinal("fanout:" + node.id)),)
        def run(i):
            previous = getattr(self.local, "parallel", False)
            previous_depth = getattr(self.local, "depth", 0)
            previous_route = getattr(self.local, "route", ())
            previous_counts = getattr(self.local, "counts", {})
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
        def accept(i, future=None):
            try:
                result = future.result() if future else run(i)
                results[i] = Binding(ResultValue(True, result.value), result.evidence) if collect else result
                states[i] = "ok"
                return True
            except Fault as exc:
                errors[i], states[i] = exc, "failed"
                if collect and exc.catchable:
                    eid = self.event(node, "collected_error", exc.evidence, index=i, incomplete=True)
                    results[i] = Binding(ResultValue(False, error=exc.view(self.plan.source)), frozenset({eid}))
                    return True
                return False
        if workers == 1 or nested or count < 2:
            for i in range(count):
                if not accept(i):
                    break
        else:
            # Stop submitting on failure, then account for every already-started
            # branch. No retry/rollback is inferred from a cancelled future.
            with create_executor("ibl_v2", max_workers=workers) as pool:
                pending, next_i, stopped = {}, 0, False
                while pending or (not stopped and next_i < count):
                    while not stopped and len(pending) < workers and next_i < count:
                        pending[pool.submit(run, next_i)] = next_i
                        states[next_i] = "running"
                        next_i += 1
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        if not accept(pending.pop(future), future):
                            stopped = True
        fatal = [i for i, e in errors.items() if not collect or not e.catchable]
        if fatal:
            first = errors[min(fatal)]
            parents = self.parents(results.values()) | {e for error in errors.values() for e in error.evidence}
            eid = self.event(node, "coverage", parents, states=states,
                             successful_indices=sorted(results), incomplete=True)
            error = Fault(first.code, str(first), first.node,
                          kind=first.kind if not first.catchable else "partial",
                          partial=[results[i].value for i in sorted(results)],
                          details={"coverage": states, "successful_indices": sorted(results),
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
                env["error"] = Binding(exc.view(self.plan.source), frozenset(exc.evidence))
                recovered = self.event(node, "recovered", exc.evidence, code=exc.code)
                try:
                    result = self.eval(d["catch"], env, control={recovered})
                    result = Binding(result.value, result.evidence | {recovered})
                except Returned as returned:
                    returned.binding = Binding(returned.binding.value, returned.binding.evidence | {recovered})
                    raise
                finally:
                    if old is None:
                        env.pop("error", None)
                    else:
                        env["error"] = old
        except (Fault, Returned) as exc:
            primary = exc
        if d["final"]:
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
            primary.binding = Binding(primary.binding.value, primary.binding.evidence | cleanup_result.evidence)
        if primary is not None:
            raise primary
        return Binding(result.value, result.evidence | cleanup_result.evidence)

    def ordinal(self, key):
        counts = getattr(self.local, "counts", None)
        if counts is None:
            counts = self.local.counts = {}
        value = counts.get(key, 0)
        counts[key] = value + 1
        return value

    def invoke(self, node, args, piped):
        spec = self.plan.registry[f"{node.data['node']}:{node.data['action']}"]
        if spec.stateful and spec.stateful(args.value):
            # Serialize invocation AND receipt/evidence, so another branch cannot
            # observe the object mutation before its evidence has been committed.
            with self.foreign_lock:
                return self._invoke(node, args, piped)
        return self._invoke(node, args, piped)

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
        if spec.dependency and spec.dependency(node.data['dependency_args']) != node.data['dependency_snapshot']:
            raise Fault('DEFINITION_CHANGED', '참조한 실행 자산이 검사 이후 변경되었습니다.', node, kind='protocol')
        contract = selected(spec.contract, args.value)
        from ibl_value_checks import value_problems
        failures = problems(contract, args.value) + value_problems(contract, args.value, self.plan.registry)
        failures += [f"필수 인자 누락: {k}" for k in contract.get("required", contract["params"]) if k not in args.value]
        if failures:
            raise Fault('ARGUMENT_CONTRACT', '; '.join(failures), node)
        for name, value in args.value.items():
            guard(value, contract['params'].get(name, 'Unknown'), f'{key}.{name}')
        def request_value(value):
            if isinstance(value, Builtin):
                return {"builtin": value.name}
            if isinstance(value, Closure):
                return {"closure_node": value.body.id, "params": list(value.params),
                        "captures": {k: request_value(b.value) for k, b in sorted(value.env.items())}}
            if isinstance(value, ResultValue):
                # Collected results may contain internal callables. Encode
                # them only for request identity; the public wire still
                # rejects callables, including inside Result containers.
                return ResultValue(value.ok, request_value(value.value), request_value(value.error))
            if isinstance(value, dict):
                return {k: request_value(v) for k, v in value.items()}
            if isinstance(value, list):
                return [request_value(v) for v in value]
            return value
        request = {"action": key, "args": pack(request_value(args.value)), "plan": self.plan.fingerprint}
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
                            "contract": contract,
                            "model_identity": model_identity,
                            "dependency": node.data.get("dependency_snapshot"),
                            "semantics": {k: self.plan.dependencies[k]
                                          for k in ("core", "edition", "semantics", "expressions")}}
        reuse_key = digest(reuse_identity)
        reuse_parts = {name: digest(value) for name, value in reuse_identity.items()}
        stateful = bool(spec.stateful and spec.stateful(args.value))
        parents = args.evidence | (self.foreign_evidence if stateful else frozenset())
        eid = self.event(node, "invoke", parents, action=key,
                         effects=contract["effects"], request_hash=request_hash)
        tool_evidence = {}
        external = contract["effects"] != ["pure"]
        read_only = (contract["effects"] == ["read_external"] or
                     (contract["effects"] == ["unknown"] and spec.reusable is not None
                      and spec.reusable(args.value)))
        model_only = contract['effects'] == ['model'] and model_identity is not None
        reusable_read = (read_only or model_only) and not contract.get('per_run', False)
        from ibl_run_journal import call_resources, resources_overlap
        state_change = external and not read_only and contract['effects'] != ['model']
        footprint = call_resources(spec, contract, args.value, 'write' if state_change else 'read')
        if model_only:
            footprint = []  # All source values are arguments; no hidden external reads.
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

        call_id = digest([getattr(self.local, "route", ()), node.id, self.ordinal(node.id)])
        receipt, source = None, "journal"
        if self.journal and external:
            receipt = self.journal.begin(call_id, request_hash, getattr(self.local, "cleanup", None) is not None,
                                         reusable=reusable_read, state_change=state_change, resources=footprint)
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
                if hit is not None and "value" in hit and not hit.get("reuse_disabled"):
                    receipt, source = hit, "reuse"
                    if model_only:
                        self.consumed_model_receipts.add(reuse_key)
        if receipt is None and self.reuse_run and reusable_read:
            if invalidated:
                reason = "overlapping_write"
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
                    self.reuse_skipped.append({'action': key, 'location': span(self.plan.source, node),
                                              'reason': reason, 'candidates': differences[:5],
                                              'candidates_total': len(differences)})
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
            with bind_scope(self.commit_scope, receipt.get("observed_at")):
                spec.run(self, copy.deepcopy(args.value))
        if receipt is not None:
            if stateful:
                raise failed(Fault("PY_STATE_EXPIRED", "외부 실행 상태는 새 워커에 복원되지 않습니다. export한 값을 새 입력으로 사용하세요.", node, kind="protocol"))
            if spec.authorize:
                spec.authorize()
            from ibl_v2_ir import unpack
            self.event(node, "receipt_reused", [eid], call_id=call_id, source=source,
                       **({"run_id": self.reuse_run} if source == "reuse" else {}))
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
                        with bind_scope(self.commit_scope, observed_at):
                            value = spec.run(self, copy.deepcopy(args.value))
                    finally:
                        with self.lock:
                            self.model_usage.extend(usage)
                        if usage:
                            self.event(node, 'model_usage', [eid], calls=copy.deepcopy(usage))
                from ibl_v2_adapters import Adapted
                if isinstance(value, Adapted):
                    tool_evidence, value = value.evidence, value.value
                if usage:
                    tool_evidence = {**tool_evidence, 'model_usage': copy.deepcopy(usage)}
                guard(value, contract["result"], f"{key} 반환")
                if external:
                    receipt = {"request_hash": request_hash, "value": pack(value), "evidence": tool_evidence,
                               "action": key, "reuse_key": reuse_key, "reuse_parts": reuse_parts}
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
                exc = failed(error)
                receipt = {"request_hash": request_hash, "action": key, "reuse_key": reuse_key,
                           "error": projection(exc.view(self.plan.source)), "partial": pack(exc.partial),
                           **({'evidence': {'model_usage': copy.deepcopy(usage)}} if usage else {})}
                if self.journal and external:
                    self.journal.finish(call_id, receipt)
                with self.lock:
                    self.recordings.append(receipt)
                raise exc
        if tool_evidence:
            eid = self.event(node, "tool_evidence", [eid], **tool_evidence)
        if stateful:
            self.foreign_evidence = frozenset({eid})
        return Binding(value, frozenset({eid}))

    def run(self):
        with self.resources:
            return self._run()

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
        if self.plan.issues:
            from ibl_v2_analysis import rejection_message, compact_check
            return {**compact_check(self.plan), "success": False,
                    "error": rejection_message("실행 전 검사에서 거절했습니다", self.plan.issues)}
        if set(self.inputs) != set(self.plan.input_types):
            return {"edition": 2, "success": False, "error": "컴파일 시 입력 서명과 실행 입력이 다릅니다.", "executed": False}
        try:
            from ibl_v2_types import infer, compatible
            for key, value in self.inputs.items():
                pack(value)
                if not compatible(infer(value), self.plan.input_types[key]):
                    raise Fault("INPUT_TYPE", f"컴파일 시 입력 타입과 다릅니다: {key}", kind="protocol")
            env = {}
            for key, value in self.inputs.items():
                note = self.input_evidence.get(key)
                roots = frozenset()
                if note:
                    eid = self.event(self.plan.root, "input_ref", origin=note,
                                     incomplete=(note.get("evidence") or {}).get("incomplete") is True)
                    roots = frozenset({eid})
                env[key] = Binding(value, roots)
            result = self.frame(self.plan.root, env)
            if wire_protocol(result.value) not in self.value_protocols:
                raise Fault('VALUE_PROTOCOL_UNSUPPORTED', '소비자가 외부 참조 wire를 지원하지 않습니다. 실행 안에서 값/파일로 변환하세요.', kind='protocol', details={'value_preview': projection(result.value)})
            wire = pack(result.value)
            out = {"success": True, "value": projection(result.value),
                   "value_wire": {"protocol": wire_protocol(result.value), "data": wire}}
        except Fault as exc:
            out = {"success": False, "error": str(exc), "diagnostic": projection(exc.view(self.plan.source))}
            out.update(self._partial_transport(exc.partial))
        out.update({"edition": 2, "executed": True, "plan_hash": self.plan.fingerprint,
                    "source_complete": not any(e.get("incomplete") for e in self.trace),
                    "evidence": self.trace, "source_map": self.source_map, "recordings": self.recordings,
                    "usage": {"steps": self.budget.used_steps, "rows": self.budget.used_rows,
                              "elapsed_ms": round((time.monotonic() - self.budget.started) * 1000)}})
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
        notes = [{'event_id': event['id'], 'location': self.source_map.get(event['node_id'], {}),
                  'warning': event['warning'][:1000]}
                 for event in self.trace if event.get('warning')]
        if notes:
            out['execution_notes'] = notes[:20]
            out['execution_notes_omitted'] = max(0, len(notes) - 20)
        if self.owns_commit_scope and out.get("success") and out.get("source_complete"):
            try:
                self.commit_scope.commit()
            except Exception as exc:
                out.update(success=False, error=f"관측 원장 확정 실패: {exc}")
        if self.plan.preflight.get('warnings'):
            out['precheck_warnings'] = self.plan.preflight['warnings']
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
