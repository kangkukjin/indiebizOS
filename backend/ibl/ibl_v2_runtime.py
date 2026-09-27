"""Edition 2 interpreter over the checked core tree.

One shared budget, explicit Outcome boundaries and evidence sidecars. No source
is reparsed while mapping rows. External calls use only the plan's adapters.
"""
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
    lock: object = field(default_factory=threading.RLock)

    def tick(self, row=False, depth=0):
        with self.lock:
            self.used_steps += 1
            self.used_rows += int(row)
            if (self.used_steps > self.steps or self.used_rows > self.rows or
                    (self.seconds is not None and time.monotonic() - self.started > self.seconds) or depth > self.depth):
                raise Fault("BUDGET", "공유 실행 예산을 초과했습니다.", kind="budget")


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
                 input_evidence=None):
        self.journal = journal
        # 편집한 프로그램이 앞 실행(reuse_run)의 읽기 영수증을 액션·인자·구현 지문으로 재사용한다.
        # 프로그램 지문은 키에 없다 — 함수 하나를 고쳐도 검증된 수집 결과가 살아남는 통로(2026-09-26).
        self.reusable, self.reuse_run, self.reused_calls = dict(reusable or {}), reuse_run, 0
        self.read_receipts = set()
        self.plan = plan
        self.inputs = copy.deepcopy(inputs or {})
        self.input_evidence = copy.deepcopy(input_evidence or {})
        self.reuse_invalidated = False
        self.cancel_check = cancel_check
        self.budget = budget or Budget()
        self.trace, self.recordings = [], []
        self.source_map = {}
        self.replay, self.recorded = replay, list(recordings or [])
        self.lock = threading.RLock()
        self.local = threading.local()

    def event(self, node, kind, parents=(), **extra):
        with self.lock:
            eid = len(self.trace) + 1
            if node.id not in self.source_map:
                self.source_map[node.id] = span(self.plan.source, node)
            self.trace.append({"id": eid, "node_id": node.id, "invocation_id": eid,
                               "kind": kind, "parents": sorted(parents),
                               **extra})
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
        self.budget.tick(depth=getattr(self.local, "depth", 0))

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
            eid = self.event(node, node.kind, result.evidence | dependencies)
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
            raise Fault("PIPE_COLLISION", "파이프 입력 자리가 없거나 중복입니다.", node)
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
        items = guard(options["items"], "List", "each.items")
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
                                   "errors": {str(i): projection(e.view(self.plan.source)) for i, e in errors.items()}})
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
        key = f"{node.data['node']}:{node.data['action']}"
        spec = self.plan.registry[key]
        from ibl_callable_contract import normalize, selected, problems
        args = Binding(normalize(spec.contract, args.value), args.evidence)
        args = self.inject(node, args, spec.contract.get("pipe_input"), piped)
        if spec.dependency and spec.dependency(node.data['dependency_args']) != node.data['dependency_snapshot']:
            raise Fault('DEFINITION_CHANGED', '참조한 실행 자산이 검사 이후 변경되었습니다.', node, kind='protocol')
        contract = selected(spec.contract, args.value)
        failures = problems(contract, args.value)
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
        request_hash = digest(request)
        # The whole program may change, but the selected call contract and its
        # dependency snapshot must still describe the same value/effect boundary.
        reuse_key = digest({"action": key, "args": request["args"],
                            "contract": contract,
                            "dependency": node.data.get("dependency_snapshot"),
                            "semantics": {k: self.plan.dependencies[k]
                                          for k in ("core", "edition", "semantics", "expressions")}})
        eid = self.event(node, "invoke", args.evidence, action=key,
                         effects=contract["effects"], request_hash=request_hash)
        tool_evidence = {}
        external = contract["effects"] != ["pure"]
        read_only = (contract["effects"] == ["read_external"] or
                     (contract["effects"] == ["unknown"] and spec.reusable is not None
                      and spec.reusable(args.value)))
        # A write/opaque/model call can change the state read by any later
        # external leaf. Reuse remains available before that boundary only.
        if external and not read_only:
            with self.lock:
                self.reuse_invalidated = True

        def failed(error):
            # A failed external leaf is a missing source even when a surrounding
            # catch returns a normal value. Keep the same fact on receipt reuse;
            # ordinary pure computation faults do not imply missing sources.
            exc = error if isinstance(error, Fault) else Fault("VALUE", str(error), node)
            failure = self.event(node, "tool_failure", set(exc.evidence) | {eid},
                                 action=key, code=exc.code, failure_kind=exc.kind,
                                 incomplete=external or exc.kind == "partial")
            exc.evidence = [failure]
            return exc

        call_id = digest([getattr(self.local, "route", ()), node.id, self.ordinal(node.id)])
        receipt, source = None, "journal"
        if self.journal and external:
            receipt = self.journal.begin(call_id, request_hash, getattr(self.local, "cleanup", None) is not None)
        if self.replay and external and receipt is None:
            with self.lock:
                receipt = next((r for r in self.recorded if r["request_hash"] == request_hash), None)
                if receipt is not None:
                    self.recorded.remove(receipt)
            if receipt is None:
                raise Fault("REPLAY_MISSING", "이 입력·정의의 실행 기록이 없습니다. 외부 호출하지 않습니다.", node, kind="protocol")
            source = "replay"
        if receipt is None and external and self.reusable and read_only and not self.reuse_invalidated:
            # 선언된 읽기 효과, 또는 미상 효과 어휘의 부작용 해소 규칙이 '없음'인 op 만 — 쓰기·모델 호출은 언제나
            # 다시 실행한다. 실패 영수증도 재사용하지 않는다.
            hit = self.reusable.get(reuse_key)
            if hit is not None and "value" in hit:
                receipt, source = hit, "reuse"
        if receipt is not None:
            if spec.authorize:
                spec.authorize()
            from ibl_v2_ir import unpack
            self.event(node, "receipt_reused", [eid], call_id=call_id, source=source,
                       **({"run_id": self.reuse_run} if source == "reuse" else {}))
            if source == "reuse":
                receipt = {**receipt, "request_hash": request_hash}
                with self.lock:
                    self.reused_calls += 1
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
            tool_evidence = receipt.get("evidence", {})
        else:
            try:
                value = spec.run(self, copy.deepcopy(args.value))
                from ibl_v2_adapters import Adapted
                if isinstance(value, Adapted):
                    tool_evidence, value = value.evidence, value.value
                guard(value, contract["result"], f"{key} 반환")
                if external:
                    receipt = {"request_hash": request_hash, "value": pack(value), "evidence": tool_evidence,
                               "action": key, "reuse_key": reuse_key}
                    if self.journal:
                        self.journal.finish(call_id, receipt)
                    with self.lock:
                        self.recordings.append(receipt)
            except Exception as error:
                exc = failed(error)
                receipt = {"request_hash": request_hash, "action": key, "reuse_key": reuse_key,
                           "error": projection(exc.view(self.plan.source)), "partial": pack(exc.partial)}
                if self.journal and external:
                    self.journal.finish(call_id, receipt)
                with self.lock:
                    self.recordings.append(receipt)
                raise exc
        if tool_evidence:
            eid = self.event(node, "tool_evidence", [eid], **tool_evidence)
        if external and read_only:
            with self.lock:
                self.read_receipts.add(call_id)
        return Binding(value, frozenset({eid}))

    def run(self):
        if self.plan.issues:
            return {**self.plan.report(), "success": False, "error": "실행 전 검사에서 거절했습니다."}
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
            wire = pack(result.value)
            out = {"success": True, "value": projection(result.value),
                   "value_wire": {"protocol": "ibl-value/1", "data": wire}}
        except Fault as exc:
            out = {"success": False, "error": str(exc), "diagnostic": projection(exc.view(self.plan.source))}
            if exc.partial is not UNIT:
                out["partial_wire"] = {"protocol": "ibl-value/1", "data": pack(exc.partial)}
        out.update({"edition": 2, "executed": True, "plan_hash": self.plan.fingerprint,
                    "source_complete": not any(e.get("incomplete") for e in self.trace),
                    "evidence": self.trace, "source_map": self.source_map, "recordings": self.recordings,
                    "usage": {"steps": self.budget.used_steps, "rows": self.budget.used_rows,
                              "elapsed_ms": round((time.monotonic() - self.budget.started) * 1000)}})
        if self.plan.preflight.get('warnings'):
            out['precheck_warnings'] = self.plan.preflight['warnings']
        if self.reuse_run:
            out["reuse"] = {"run_id": self.reuse_run, "reused_calls": self.reused_calls, "candidates": len(self.reusable)}
        if self.journal:
            out["resume"] = {"run_id": self.journal.run_id}
            out["resumed"] = self.journal.resuming
            out["run_status"] = self.journal.complete(out)
            if self.read_receipts and out["run_status"] not in {"blocked", "uncertain"}:
                out["continuation"] = {
                    "reuse_args": {"reuse": {"run_id": self.journal.run_id}},
                    "read_calls": len(self.read_receipts),
                    "hint": "프로그램 수정 뒤 이전 읽기를 이어 쓸 때 reuse_args를 요청에 합치세요. "
                            "현재 자료를 새로 조회해야 하면 쓰지 마세요. 계약·인자·권한 검사는 유지하며 쓰기·모델 호출은 재사용하지 않습니다. "
                            "동일 코드·inputs의 기록 재개는 resume입니다. 확인된 실패도 그대로 복원합니다."}
        return out
