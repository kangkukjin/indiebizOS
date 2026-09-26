"""Name resolution, structural preflight and immutable execution snapshots.

Unknown is an explicit runtime guard, not a successful proof. No warm cache is
used yet: every plan contains its source/definitions/contracts and dependency
fingerprint, avoiding the legacy transitive-cache invalidation problem.
"""
from dataclasses import dataclass, field
from pathlib import Path
import copy
from ibl_v2_ir import Fault, Node, UNIT, digest, span, parallel_branches
from ibl_v2_parser import parse
from ibl_v2_expr import BUILTINS
from ibl_v2_analysis import (finish_diagnostics, numeric_operand, builtin_type,
                             assigned_names, location, access_type)
from ibl_v2_types import (Type, UNKNOWN, UNIT_T, BOOL, NUMBER, TEXT, NULL,
                          infer, join, declared, compatible, alternatives,
                          ordered_list, concat_lists)

RESERVED = {"it", "i", "error"}
PURE_KINDS = {"literal", "ref", "record", "list", "unary", "binary", "field",
              "index", "builtin", "pure_call", "lambda", "format"}


@dataclass
class Plan:
    source: str
    root: Node
    functions: dict
    registry: dict
    input_types: dict
    issues: list
    guards: list
    effects: set
    result_type: Type
    fingerprint: str
    dependencies: dict
    function_contracts: dict = field(default_factory=dict)
    preflight: dict = field(default_factory=dict)

    def report(self):
        status = "invalid" if self.issues else ("incomplete" if self.guards else "valid")
        return {"edition": 2, "mode": "check", "executed": False, "ok": not self.issues,
                "status": status, "issues": self.issues, "guards": self.guards,
                "result_type": str(self.result_type), "effects": sorted(self.effects), "functions": self.function_contracts,
                "plan_hash": self.fingerprint, "dependencies": self.dependencies,
                "source_hash": digest(self.source[:self.dependencies["source_map"][0]["end"]]),
                "capabilities": ["ibl-edition/2", "ibl-value/1"],
                "preflight": self.preflight, "warnings": self.preflight.get("warnings", []),
                "note": "incomplete는 미확정 타입의 실행 시 검사를 포함합니다. 업무 품질·전건 완료의 보증이 아닙니다."}


class Compiler:
    def __init__(self, source, registry, inputs, definitions=None):
        self.source, self.registry = source, registry
        self.definitions, self.external = definitions or {}, {}
        self.source_map = [{"name": "<program>", "start": 0, "end": len(source)}]
        self.inputs = {k: infer(v) for k, v in inputs.items()}
        self.functions, self.scopes, self.function_scopes = {}, {}, {}
        self.issues, self.guards, self.effects = [], [], set()
        self.stack, self.checked = [], set()
        self.call_path = []
        self.returns = []
        self.function_contracts = {}
        self.used_actions = set()
        self.call_dependencies = {}

    def issue(self, node, code, message, **details):
        item = {"code": code, "message": message, "source_span": span(self.source, node),
                "call_path": copy.deepcopy(self.call_path), **details}
        if item not in self.issues:
            self.issues.append(item)

    def need(self, node, actual, expected):
        if actual.kind == "Unknown":
            item = {"source_span": span(self.source, node), "expected": str(expected),
                    "actual": str(actual), "call_path": copy.deepcopy(self.call_path)}
            if item not in self.guards:
                self.guards.append(item)
        elif not compatible(actual, expected):
            self.issue(node, "TYPE", f"{expected}가 필요하지만 {actual}입니다.",
                       expected=str(expected), actual=str(actual))

    def pure(self, node):
        if node is None:
            return
        if node.kind not in PURE_KINDS:
            self.issue(node, "PURE_EXPRESSION", "이 자리에는 순수 식만 쓸 수 있습니다. 도구 호출은 앞 문장에 두세요.")
        for value in node.data.values():
            self.check_children(value, self.pure)

    def container_value(self, node):
        """Construct values with calls, without adding a statement/return scope.

        Calls own their argument checks and each/function return frames. Pure
        slots (operators, lambdas, defaults, conditions) still check recursively
        in visit; a nested record cannot smuggle effects into those slots.
        """
        if node.kind in ("call", "lambda"):
            return
        if node.kind not in PURE_KINDS | {"pipe", "parallel", "fallback"}:
            self.issue(node, "VALUE_EXPRESSION",
                       "객체·목록의 값에는 식·호출·조합을 쓰세요. 제어 블록은 앞 문장이나 함수 본문에 두세요.")
            return
        for value in node.data.values():
            self.check_children(value, self.container_value)

    def check_children(self, value, check):
        if isinstance(value, Node):
            check(value)
        elif isinstance(value, dict):
            for v in value.values():
                self.check_children(v, check)
        elif isinstance(value, (list, tuple)):
            for v in value:
                self.check_children(v, check)

    def predeclare(self, body, names):
        names = dict(names)
        local = set()
        for node in body.data["statements"]:
            if node.kind == "def":
                name = node.data["name"]
                if name in local:
                    self.issue(node, "DUPLICATE_FUNCTION", f"중복 함수: {name}")
                local.add(name)
                sid = node.id
                names[name] = sid
                self.functions[sid] = node
                node.data["symbol"] = sid
        for node in body.data["statements"]:
            if node.kind == "def":
                self.function_scopes[node.id] = names.copy()
        return names

    def sequence(self, node, env, names, readonly=frozenset(), final=False):
        names = self.predeclare(node, names)
        result = UNIT_T
        terminated = False
        dead_env = None
        for statement in node.data["statements"]:
            if terminated:
                # Still diagnose invalid dead source, but it cannot supply a
                # frame result or add return types to the reachable paths.
                old_returns, self.returns = self.returns, []
                self.visit(statement, dead_env, names, readonly, final)
                self.returns = old_returns
            else:
                result = self.visit(statement, env, names, readonly, final)
                if self.returns_unconditionally(statement):
                    terminated, dead_env = True, env.copy()
        return result

    def resolve_function(self, name, names):
        if name in names:
            return names[name]
        if name in self.external:
            return self.external[name]
        if name not in self.definitions:
            return None
        from ibl_v2_parser import Parser
        from ibl_v2_store import definition_name
        code = self.definitions[name]
        if definition_name(code) != name:
            raise Fault("LIBRARY_NAME", f"등록 이름과 정의 이름이 다릅니다: {name}", kind="compile")
        offset = len(self.source) + 1
        self.source += "\n" + code
        self.source_map.append({"name": name, "start": offset, "end": len(self.source)})
        body = Parser(code, offset).program()
        symbols = self.predeclare(body, {})
        self.external[name] = symbols[name]
        return symbols[name]

    def function(self, sid, args, call=None):
        node = self.functions[sid]
        if sid in self.stack:
            self.issue(node, "RECURSION", "첫 판본에서는 재귀 함수를 지원하지 않습니다.")
            return UNKNOWN
        self.stack.append(sid)
        self.call_path.append({"function": node.data["name"],
                               "call": span(self.source, call) if call else None,
                               "definition": span(self.source, node)})
        old_returns, self.returns = self.returns, []
        params = node.data["params"]
        env = {}
        for name, default in params.items():
            if name in RESERVED:
                self.issue(node, "RESERVED", f"예약 바인딩은 인자로 쓸 수 없습니다: {name}")
            dtype = UNKNOWN
            if default:
                self.pure(default)
                dtype = self.visit(default, {}, {}, frozenset(), False)
            env[name] = args.get(name, dtype)
        parameter_types = {k: str(v) for k, v in env.items()}
        result = self.sequence(node.data["body"], env, self.function_scopes[sid])
        for t in self.returns:
            result = t if result == UNIT_T else join(result, t)
        self.returns = old_returns
        self.stack.pop()
        self.call_path.pop()
        self.checked.add(sid)
        observed = {'params': parameter_types, 'result': str(result)}
        summary = self.function_contracts.setdefault(sid, {
            'name': node.data['name'], 'params': parameter_types.copy(),
            'required': [k for k,v in params.items() if v is None],
            'result': str(result), 'specializations': [], 'specializations_omitted': 0})
        for key, value in parameter_types.items():
            if summary['params'][key] != value:
                summary['params'][key] = 'Unknown'
        if summary['result'] != str(result):
            summary['result'] = 'Unknown'
        if observed not in summary['specializations']:
            if len(summary['specializations']) < 32:
                summary['specializations'].append(observed)
            else:
                summary['specializations_omitted'] += 1
        return result

    def visit(self, node, env, names, readonly=frozenset(), final=False, piped=None):
        if node is None:
            return UNIT_T
        d, kind = node.data, node.kind
        sub = lambda n, e=env: self.visit(n, e, names, readonly, final)
        if kind == "sequence":
            return self.sequence(node, env, names, readonly, final)
        if kind == "literal":
            return infer(d["value"])
        if kind == "ref":
            if d["name"] not in env:
                self.issue(node, "UNBOUND", f"정의되지 않은 값: ${d['name']}")
            return env.get(d["name"], UNKNOWN)
        if kind == "bind":
            name = d["name"]
            if name in readonly or name in RESERVED:
                self.issue(node, "READONLY", f"읽기 전용 바인딩: ${name}")
            env[name] = sub(d["value"])
            return UNIT_T
        if kind == "return":
            if final:
                self.issue(node, "FINALLY_RETURN", "finally 안에는 return을 쓸 수 없습니다.")
            result = sub(d["value"])
            self.returns.append(result)
            return result
        if kind == "def":
            return UNIT_T
        if kind == "list":
            self.container_value(node)
            return ordered_list(sub(v) for v in d["values"])
        if kind == "record":
            self.container_value(node)
            return Type("Record", tuple((k, sub(v)) for k, v in d["fields"].items()), open=False)
        if kind in ("field", "index"):
            base = sub(d["base"])
            key = d.get("key")
            key_type = None
            if isinstance(key, Node):
                key_type = sub(key)
                key = key.data["value"] if key.kind == "literal" else None
            return access_type(self, node, base, key, key_type)
        if kind in ("binary", "unary"):
            self.pure(node)
            op = d["op"]
            values = [sub(d["value"])] if kind == "unary" else [sub(d["left"]), sub(d["right"])]
            if op in ("and", "or", "&&", "||", "!", "not"):
                for t in values:
                    self.need(node, t, BOOL)
                return BOOL
            if op in ("==", "!=", "<", ">", "<=", ">=", "in"):
                return BOOL
            if op == "+" and len(values) == 2 and values[0].kind == values[1].kind and values[0].kind in ("List", "Text"):
                return concat_lists(*values) if values[0].kind == "List" else TEXT
            if op == "+" and any(t.kind in ("Unknown", "Union") for t in values):
                # An unknown accumulator/callback operand may concatenate.
                # Do not select numeric addition until both shapes are known.
                if all(member.kind in ("Unknown", "List", "Text", "Number")
                       for t in values for member in alternatives(t)):
                    self.need(node, UNKNOWN, UNKNOWN)
                    return UNKNOWN
            operands = [d["value"]] if kind == "unary" else [d["left"], d["right"]]
            for operand, typ in zip(operands, values):
                numeric_operand(self, operand, typ)
            return NUMBER
        if kind == "builtin":
            if d["name"] not in BUILTINS:
                self.issue(node, "BUILTIN", f"알 수 없는 내장 함수: {d['name']}")
            return Type("Callable")
        if kind == "pure_call":
            self.pure(node)
            fn = d["fn"]
            self.need(fn, sub(fn), Type("Callable"))
            types = [sub(a) for a in d["args"]]
            if fn.kind == "builtin" and fn.data["name"] in BUILTINS:
                name = fn.data["name"]
                low, high = BUILTINS[name]
                if not low <= len(types) <= high:
                    self.issue(node, "ARITY", f"{name}은 {low}~{high}개 인자를 받습니다.")
                return builtin_type(self, node, name, types)
            return UNKNOWN
        if kind == "lambda":
            params = d["params"]
            if len(set(params)) != len(params) or RESERVED.intersection(params):
                self.issue(node, "PARAMETERS", "람다 인자는 중복·예약 이름을 쓸 수 없습니다.")
            local = {**env, **dict.fromkeys(params, UNKNOWN)}
            self.pure(d["body"])
            sub(d["body"], local)
            return Type("Callable")
        if kind == "format":
            for part in d["parts"]:
                if isinstance(part, Node):
                    self.pure(part)
                    t = sub(part)
                    if not compatible(t, join(join(TEXT, NUMBER), BOOL)):
                        self.issue(part, "FORMAT_TYPE", "보간에는 Text·Number·Bool만 사용할 수 있습니다.")
                    elif t.kind == "Unknown":
                        self.need(part, t, join(join(TEXT, NUMBER), BOOL))
            return TEXT
        if kind == "pipe":
            left = sub(d["left"])
            if d["right"].kind != "call":
                self.issue(node, "PIPE_TARGET", "파이프 오른쪽은 명시 입력이 있는 호출이어야 합니다.")
                return UNKNOWN
            return self.visit(d["right"], env, names, readonly, final, piped=left)
        if kind == "parallel":
            types = []
            writes, conflict = set(), set()
            for branch in parallel_branches(node):
                old_returns, self.returns = self.returns, []
                result = sub(branch, env.copy())
                for t in self.returns:
                    result = t if result == UNIT_T else join(result, t)
                self.returns = old_returns
                types.append(result)
                branch_writes = self.writes(branch)
                conflict.update(writes & branch_writes)
                writes.update(branch_writes)
            if conflict:
                self.issue(node, "PARALLEL_WRITE_CONFLICT", f"병렬 가지가 같은 선언 자원에 씁니다: {sorted(conflict)}")
            return ordered_list(types)
        if kind == "fallback":
            return join(sub(d["left"], env.copy()), sub(d["right"], env.copy()))
        if kind == "call":
            args = dict(sub(d["params"]).fields)
            key = f"{d['node']}:{d['action']}"
            if key == "table:each":
                return self.each(node, args, env, names, piped)
            if d["node"] == "fn":
                sid = self.resolve_function(d["action"], names)
                if sid:
                    d["symbol"] = sid
                    params = self.functions[sid].data["params"]
                    receiver = next(iter(params), None)
                    self.arguments(node, args, params, receiver, piped)
                    return self.function(sid, args, node)
                if key not in self.registry:
                    self.issue(node, "FUNCTION", f"등록된 함수가 없습니다: {d['action']}")
                    return UNKNOWN
            spec = self.registry.get(key)
            if not spec:
                self.issue(node, "UNSUPPORTED_ADAPTER", f"판본 2 계약이 없는 어휘: {key}")
                return UNKNOWN
            from ibl_callable_contract import normalize, selected, problems, UNRESOLVED
            try:
                args = normalize(spec.contract, args)
                fields = normalize(spec.contract, d['params'].data['fields'])
            except Fault as exc:
                self.issue(node, exc.code, str(exc))
                return UNKNOWN
            values = {k: v.data['value'] if v.kind == 'literal' else UNRESOLVED for k, v in fields.items()}
            # Argument relationships see the same receiver as runtime.invoke.
            # The value is not known here, but its presence is statically known.
            receiver = spec.contract.get('pipe_input')
            if piped is not None and receiver and receiver not in values:
                values[receiver] = UNRESOLVED
            self.used_actions.add(key)
            if spec.dependency:
                selectors = {k: v for k, v in values.items() if v is not UNRESOLVED}
                snapshot = spec.dependency(selectors)
                d['dependency_args'], d['dependency_snapshot'] = selectors, snapshot
                self.call_dependencies[node.id] = snapshot
            contract = selected(spec.contract, values)
            for problem in problems(contract, values):
                self.issue(node, 'ARGUMENT_CONTRACT', problem)
            if any(values.get(k) is UNRESOLVED for variant in spec.contract.get('variants', []) for k in variant['when']):
                self.guards.append({'source_span': span(self.source, node), 'expected': '동적 인자에 따른 도구 계약은 실행 직전에 확인합니다.'})
            if contract.get("compatibility"):
                self.guards.append({"source_span": span(self.source, node),
                                    "boundary": contract["compatibility"], "action": key,
                                    "expected": "기존 JSON 봉투 Record; 인자·효과는 기존 실행기에서 확인"})
            params = contract["params"]
            required = set(contract.get("required", params))
            allowed = {k: None if k in required else UNIT for k in params}
            if contract.get("open_params"):
                allowed.update({k: UNIT for k in args if not k.startswith("_")})
            self.arguments(node, args, allowed, contract.get("pipe_input"), piped)
            for k, t in args.items():
                if k in params:
                    self.need(node, t, declared(params[k]))
            self.effects.update(contract["effects"])
            result_type = declared(contract["result"])
            if result_type.kind == "Unknown":
                self.need(node, UNKNOWN, UNKNOWN)
            return result_type
        if kind == "if":
            self.pure(d["value"])
            self.need(node, sub(d["value"]), BOOL)
            a, b = env.copy(), env.copy()
            ta, tb = sub(d["body"], a), sub(d["otherwise"], b)
            self.merge_continuations(env, [(d["body"], a), (d["otherwise"], b)])
            return join(ta, tb)
        if kind == "case":
            self.pure(d["value"])
            sub(d["value"])
            environments, types = [], []
            for condition, body in d["branches"]:
                self.pure(condition)
                sub(condition)
                child = env.copy()
                types.append(sub(body, child))
                environments.append((body, child))
            child = env.copy()
            types.append(sub(d["otherwise"], child))
            environments.append((d["otherwise"], child))
            self.merge_continuations(env, environments)
            result = types[0]
            for t in types[1:]:
                result = join(result, t)
            return result
        if kind == "repeat":
            self.pure(d["value"])
            count = d["value"].data.get("value") if d["mode"] == "count" and d["value"].kind == "literal" else None
            if count is not None and (type(count) is not int or count < 0):
                self.issue(d["value"], "REPEAT_COUNT", "repeat 횟수는 0 이상의 정수입니다.")
            # Count is evaluated outside the new index scope. While sees the
            # first iteration's environment before any body assignment.
            if d["mode"] == "count":
                self.need(node, sub(d["value"]), NUMBER)
            elif d["mode"] == "while":
                sub_env = {**env, "i": NUMBER}
                self.need(node, sub(d["value"], sub_env), BOOL)
            mutated = assigned_names(d["body"]) & env.keys()
            local = {**env, "i": NUMBER}
            # Later iterations may see a different shape. Widen before checking
            # the body rather than certify a stale first-iteration type.
            if count not in (0, 1):
                local.update(dict.fromkeys(mutated, UNKNOWN))
            if d["mode"] == "while":
                self.need(node, sub(d["value"], local), BOOL)
            sub(d["body"], local)
            if d["mode"] == "until":
                # Post-test conditions may use values definitely assigned by
                # the body, including new bindings. Conditional ones still fail.
                self.need(node, sub(d["value"], local), BOOL)
            if d["mode"] == "until" or (type(count) is int and count > 0):
                env.update({k: v for k, v in local.items() if k != "i"})
            elif count != 0:
                self.merge_env(env, env.copy(), {k: v for k, v in local.items() if k != "i" or k in env})
            return UNIT_T
        if kind == "try":
            a, b = env.copy(), {**env, "error": Type("Record")}
            # A fault may happen before or after any shared-frame assignment.
            # Catch observes partial progress, not a rollback to entry types.
            mutated = assigned_names(d["body"]) & env.keys()
            b.update(dict.fromkeys(mutated, UNKNOWN))
            ta, tb = sub(d["body"], a), sub(d["catch"], b)
            if "error" in env:
                b["error"] = env["error"]
            else:
                b.pop("error", None)
            paths = [(d["body"], a)]
            cleanup_env = a.copy()
            if d["catch"]:
                paths.append((d["catch"], b))
                self.merge_env(cleanup_env, a, b)
            # Cleanup also observes failures partway through body/catch.
            cleanup_mutated = (mutated | assigned_names(d["catch"])) & env.keys()
            cleanup_env.update(dict.fromkeys(cleanup_mutated, UNKNOWN))
            self.merge_continuations(env, paths)
            # finally also runs on returning paths. Check it before excluding
            # their bindings, then carry its assignments into the continuation.
            self.visit(d["final"], cleanup_env, names, readonly, True)
            for name in assigned_names(d["final"]):
                if name in cleanup_env:
                    env[name] = cleanup_env[name]
                elif name in env:
                    env[name] = UNKNOWN
            return join(ta, tb) if d["catch"] else ta
        self.issue(node, "IR", f"지원하지 않는 구문: {kind}")
        return UNKNOWN

    @staticmethod
    def returns_unconditionally(node):
        if node is None:
            return False
        d, kind = node.data, node.kind
        recur = Compiler.returns_unconditionally
        if kind == "return":
            return True
        if kind == "sequence":
            return any(recur(s) for s in d["statements"])
        if kind == "if":
            return recur(d["body"]) and recur(d["otherwise"])
        if kind == "case":
            return recur(d["otherwise"]) and all(recur(b) for _, b in d["branches"])
        if kind == "try":
            return recur(d["body"]) and (d["catch"] is None or recur(d["catch"]))
        if kind == "repeat":
            count = d['value'].data.get('value') if d['value'].kind == 'literal' else None
            once = d['mode'] == 'until' or (d['mode'] == 'count' and type(count) is int and count > 0)
            return once and recur(d['body'])
        return False

    def writes(self, node, bindings=None, seen=frozenset()):
        """Only declared, statically known resource identities justify conflicts."""
        bindings = bindings or {}
        if not isinstance(node, Node) or node.kind == "def":
            return set()
        out = set()
        if node.kind == "call":
            fields = node.data["params"].data["fields"]
            values = {k: v.data["value"] if v.kind == "literal" else
                      bindings.get(v.data["name"]) if v.kind == "ref" else None
                      for k, v in fields.items()}
            sid = node.data.get("symbol") if node.data["node"] == "fn" else None
            if sid in self.functions and sid not in seen:
                out.update(self.writes(self.functions[sid].data["body"], values, seen | {sid}))
            key = f"{node.data['node']}:{node.data['action']}"
            # A resolved definition shadows the adapter of the same name.
            spec = None if sid in self.functions else self.registry.get(key)
            if spec:
                from ibl_callable_contract import normalize
                values = normalize(spec.contract, values)
                out.update((realm, values[param]) for realm, param in spec.contract.get("write_resources", {}).items()
                           if isinstance(values.get(param), str))
        # Arguments now execute too. An outer read/pure call (or a function)
        # must not hide a declared write in its nested argument expressions.
        def visit(value):
            if isinstance(value, Node):
                out.update(self.writes(value, bindings, seen))
            elif isinstance(value, dict):
                for v in value.values():
                    visit(v)
            elif isinstance(value, (list, tuple)):
                for v in value:
                    visit(v)
        for value in node.data.values():
            visit(value)
        return out

    def arguments(self, node, args, params, receiver, piped):
        if piped is not None:
            if receiver is None or receiver in args:
                self.issue(node, "PIPE_COLLISION", "파이프 입력 자리가 없거나 명시 인자와 충돌합니다.")
            else:
                args[receiver] = piped
        for name, default in params.items():
            if name not in args and default is None:
                self.issue(node, "MISSING_ARGUMENT", f"필수 인자 누락: {name}")
        for name in args.keys() - params.keys():
            self.issue(node, "UNKNOWN_ARGUMENT", f"알 수 없는 인자: {name}")

    def each(self, node, args, env, names, piped):
        self.arguments(node, args, {"items": None, "mode": UNIT, "on_error": UNIT, "parallel": UNIT}, "items", piped)
        items = args.get("items", UNKNOWN)
        self.need(node, items, Type("List", item=UNKNOWN))
        fields = node.data["params"].data["fields"]
        options = {}
        for key, default in (("mode", "map"), ("on_error", "stop"), ("parallel", 1)):
            value = fields.get(key)
            if value and value.kind != "literal":
                self.issue(value, "STATIC_OPTION", f"{key}는 컴파일 시 리터럴이어야 합니다.")
            options[key] = value.data.get("value") if value else default
        if options["mode"] not in ("map", "flat_map", "effect") or options["on_error"] not in ("stop", "collect"):
            self.issue(node, "EACH_MODE", "each mode/on_error가 잘못되었습니다.")
        if options["on_error"] == "collect" and options["mode"] != "map":
            self.issue(node, "EACH_COLLECT", "on_error:collect는 map에서만 지원합니다.")
        if type(options["parallel"]) is not int or not 1 <= options["parallel"] <= 8:
            self.issue(node, "CONCURRENCY", "parallel은 1~8 정수입니다.")
        old_returns, self.returns = self.returns, []
        local = {**env, "it": items.item or UNKNOWN, "i": NUMBER}
        result = self.visit(node.data["body"], local, names, frozenset(env) | RESERVED)
        for t in self.returns:
            result = t if result == UNIT_T else join(result, t)
        self.returns = old_returns
        if options["mode"] == "effect":
            return UNIT_T
        if options["mode"] == "flat_map":
            self.need(node, result, Type("List", item=UNKNOWN))
            return result
        if options["on_error"] == "collect":
            result = Type("Result", item=result)
        return Type("List", item=result)

    @staticmethod
    def merge_env(target, a, b):
        target.clear()
        target.update({k: join(a[k], b[k]) for k in a.keys() & b.keys()})

    def merge_continuations(self, target, paths):
        """Only paths reaching the next statement constrain its bindings."""
        continuing = [env for body, env in paths if not self.returns_unconditionally(body)]
        if not continuing:
            return  # Keep checking unreachable source without inventing bindings.
        merged = continuing[0].copy()
        for env in continuing[1:]:
            self.merge_env(merged, merged.copy(), env)
        target.clear()
        target.update(merged)


def compile_program(source, registry=None, inputs=None, definitions=None):
    from ibl_v2_adapters import Adapter
    registry = {k: Adapter(copy.deepcopy(v.contract), v.run, v.authorize, v.dependency) for k, v in (registry or {}).items()}
    inputs = copy.deepcopy(inputs or {})
    compiler = Compiler(source, registry, inputs, copy.deepcopy(definitions or {}))
    root = parse(source)
    result = compiler.sequence(root, compiler.inputs.copy(), {})
    for t in compiler.returns:
        result = t if result == UNIT_T else join(result, t)
    # Unused definitions must also be well formed; validate to a fixed point for
    # nested forward definitions, without inventing caller-local parameters.
    while set(compiler.functions) - compiler.checked:
        sid = sorted(set(compiler.functions) - compiler.checked)[0]
        compiler.function(sid, {})
    dependencies = {"source": digest(compiler.source), "libraries": digest({k: compiler.definitions[k] for k in sorted(compiler.external)}),
                    "calls": compiler.call_dependencies,
                    "input_types": {k: str(t) for k, t in compiler.inputs.items()},
                    "source_map": compiler.source_map, "contracts": digest({k: registry[k].contract for k in sorted(compiler.used_actions)}),
                    "edition": digest((Path(__file__).parents[1] / "base/ibl_edition.py").read_text()),
                    "semantics": digest((Path(__file__).parents[1] / "common/value_semantics.py").read_text()),
                    "core": digest({p.name: digest(p.read_text()) for p in sorted(set(Path(__file__).parent.glob("ibl_v2_*.py")) |
                              {Path(__file__).parent / name for name in ("ibl_document_value.py", "ibl_member_library.py",
                                                                        "ibl_remote_call.py", "ibl_run_journal.py", "ibl_callable_contract.py", "ibl_dependencies.py")})})}
    finish_diagnostics(compiler)
    for sid, contract in compiler.function_contracts.items():
        contract['definition'] = location(compiler.source, compiler.source_map, compiler.functions[sid])
    from ibl_v2_preflight import analyze
    try:
        preflight = analyze(compiler, root, inputs)
    except Exception as exc:
        preflight = {'status': 'abstained', 'declared_ai_visits_upper_bound': None,
                     'unknowns': [{'reason': '분석 기반 오류', 'kind': type(exc).__name__}],
                     'warnings': []}
    return Plan(compiler.source, root, compiler.functions, registry, compiler.inputs,
                compiler.issues, compiler.guards, compiler.effects, result,
                digest(dependencies), dependencies, compiler.function_contracts, preflight)
