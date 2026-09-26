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


@dataclass(frozen=True)
class Binding:
    value: object
    evidence: frozenset = frozenset()


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


class Runtime:
    def __init__(self, plan, inputs=None, *, cancel_check=None, budget=None,
                 recordings=None, replay=False, journal=None):
        self.journal = journal
        self.plan = plan
        self.inputs = copy.deepcopy(inputs or {})
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
        if kind == "literal":
            return Binding(copy.deepcopy(d["value"]))
        if kind == "ref":
            if d["name"] not in env:
                raise Fault("UNBOUND", f"정의되지 않은 값: ${d['name']}", node)
            return env[d["name"]]
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
        if kind == "return":
            raise Returned(sub(d["value"]))
        if kind == "list":
            # Source-order, fail-fast evaluation through the ordinary eval /
            # invoke path: nested calls keep budgets, evidence and receipts.
            # Do not hoist children out of their branch or auto-parallelize.
            values = [sub(v) for v in d["values"]]
            return Binding([b.value for b in values], self.parents(values))
        if kind == "record":
            values = {k: sub(v) for k, v in d["fields"].items()}
            return Binding({k: b.value for k, b in values.items()}, self.parents(values.values()))
        if kind in ("field", "index"):
            base = sub(d["base"])
            key = Binding(d["key"]) if kind == "field" else sub(d["key"])
            if isinstance(base.value, dict) and isinstance(key.value, str):
                if key.value not in base.value:
                    raise Fault("MISSING_FIELD", f"필드가 없습니다: {key.value}", node)
            elif kind == "index" and isinstance(base.value, (str, list)):
                if type(key.value) is not int or not 0 <= key.value < len(base.value):
                    raise Fault("INDEX", "인덱스가 범위를 벗어났거나 정수가 아닙니다.", node)
            else:
                raise Fault("FIELD_TYPE", "이 값에는 해당 필드/인덱스 접근을 할 수 없습니다.", node)
            if d["base"].kind == "ref" and d["base"].data["name"] == "error" and key.value == "partial":
                self.event(node, "handled_partial", base.evidence)
            return Binding(base.value[key.value], self.parents([base, key]))
        if kind == "unary":
            value = sub(d["value"])
            out = not boolean(value.value) if d["op"] in ("not", "!") else number(value.value)
            if d["op"] == "-":
                out = -out
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
            return Binding(binary(op, a.value, b.value), self.parents([a, b]))
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
            return Binding("".join(scalar_text(p.value) for p in parts), self.parents(parts))
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
                local = {k: Binding(v, args.evidence) for k, v in args.value.items()}
                for name, default in params.items():
                    if name not in local:
                        local[name] = self.eval(default, {})
                depth = getattr(self.local, "depth", 0)
                self.local.depth = depth + 1
                try:
                    result = self.frame(definition.data["body"], local)
                    eid = self.event(node, "function_result", result.evidence | args.evidence,
                                     name=d["action"], definition_start=definition.start, success=True)
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

    def callback(self, fn, args):
        if isinstance(fn, Builtin):
            self.check()
            check_arity(fn.name, len(args))
            if fn.name == "reduce":
                rows = guard(args[0].value, "List", "reduce 목록")
                acc = args[1]
                for row in rows:
                    self.budget.tick(row=True)
                    acc = self.callback(args[2].value, [acc, Binding(row, args[0].evidence)])
                return acc
            if fn.name == "evidence":
                return Binding(self.evidence(args[0].evidence), self.parents(args))
            return Binding(pure_call(fn.name, [a.value for a in args]), self.parents(args))
        if not isinstance(fn, Closure) or len(args) != len(fn.params):
            raise Fault("CALLABLE", "콜백 또는 인자 수가 잘못되었습니다.")
        env = {**fn.env, **dict(zip(fn.params, args))}
        return self.eval(fn.body, env)

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
        eid = self.event(node, "invoke", args.evidence, action=key,
                         effects=contract["effects"], request_hash=request_hash)
        tool_evidence = {}
        external = contract["effects"] != ["pure"]

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
        receipt = None
        if self.journal and external:
            receipt = self.journal.begin(call_id, request_hash, getattr(self.local, "cleanup", None) is not None)
        if self.replay and external and receipt is None:
            with self.lock:
                receipt = next((r for r in self.recorded if r["request_hash"] == request_hash), None)
                if receipt is not None:
                    self.recorded.remove(receipt)
            if receipt is None:
                raise Fault("REPLAY_MISSING", "이 입력·정의의 실행 기록이 없습니다. 외부 호출하지 않습니다.", node, kind="protocol")
        if receipt is not None:
            if spec.authorize:
                spec.authorize()
            from ibl_v2_ir import unpack
            self.event(node, "receipt_reused", [eid], call_id=call_id)
            with self.lock:
                self.recordings.append(receipt)
            if "error" in receipt:
                error = receipt["error"]
                restored = Fault(error["code"], error["message"], node, kind=error["kind"],
                                 partial=unpack(receipt["partial"]), details=error.get("details"))
                raise failed(restored)
            value = unpack(receipt["value"])
            tool_evidence = receipt.get("evidence", {})
        else:
            try:
                value = spec.run(self, copy.deepcopy(args.value))
                from ibl_v2_adapters import Adapted
                if isinstance(value, Adapted):
                    tool_evidence, value = value.evidence, value.value
                guard(value, contract["result"], f"{key} 반환")
                if external:
                    receipt = {"request_hash": request_hash, "value": pack(value), "evidence": tool_evidence}
                    if self.journal:
                        self.journal.finish(call_id, receipt)
                    with self.lock:
                        self.recordings.append(receipt)
            except Exception as error:
                exc = failed(error)
                receipt = {"request_hash": request_hash,
                           "error": projection(exc.view(self.plan.source)), "partial": pack(exc.partial)}
                if self.journal and external:
                    self.journal.finish(call_id, receipt)
                with self.lock:
                    self.recordings.append(receipt)
                raise exc
        if tool_evidence:
            eid = self.event(node, "tool_evidence", [eid], **tool_evidence)
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
            result = self.frame(self.plan.root, {k: Binding(v) for k, v in self.inputs.items()})
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
        if self.journal:
            out["resume"] = {"run_id": self.journal.run_id}
            out["resumed"] = self.journal.resuming
            out["run_status"] = self.journal.complete(out)
        return out
