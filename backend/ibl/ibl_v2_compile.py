"""Name resolution, structural preflight and immutable execution snapshots.

Unknown is an explicit runtime guard, not a successful proof. Function analysis
is shared only within one compiler; plans retain source, definitions, contracts
and dependency fingerprints. No analysis cache survives between compilations.
"""
from dataclasses import dataclass, field
from pathlib import Path
import copy
from ibl_v2_ir import Fault, Node, UNIT, digest, span, parallel_branches, record_fields
from ibl_v2_parser import parse
from ibl_v2_narrow import known_condition
from ibl_v2_expr import BUILTINS
from ibl_dependencies import compilation_dependencies
import re
# f-문자열의 글자 부분에 남은 `$이름` — `$(`·`$5` 같은 다른 쓰임은 잡지 않는다.
_BARE_DOLLAR_NAME = re.compile(r"\$[A-Za-z_\uac00-\ud7a3][\w\uac00-\ud7a3]*")
from ibl_v2_analysis import (finish_diagnostics,
                             assigned_names, location, access_type, HINTS)
from ibl_v2_types import (Type, UNKNOWN, UNIT_T, BOOL, NUMBER, TEXT, NULL, rows_type,
                          infer, join, declared, compatible, alternatives,
                          ordered_list, NEVER, describe_type)

RESERVED = {"it", "i", "error"}
PURE_KINDS = {"literal", "ref", "record", "list", "unary", "binary", "field",
              "index", "slice", "builtin", "pure_call", "named_call", "callable_ref", "lambda", "format", "conditional"}


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
    # 이 계획을 검사한 저장 함수 목록 — 실행 시점의 중첩 문장 검사(code_params)가 컴파일 때와 같은 목록을 본다.
    definitions: dict = field(default_factory=dict)
    # 선언됐지만 제공되지 않은 입력 이름(declared_inputs − inputs). 앱 표면의 빈 입력이 여기 온다 —
    # 호출 인자 자리에서는 그 인자가 생략되고, f-문자열 보간에서는 빈 문자열이다(2026-10-05, 표면 바인딩 개정 ①).
    unspecified: frozenset = frozenset()

    function_scopes: dict = field(default_factory=dict)
    accesses: set = field(default_factory=set)
    components: dict = field(default_factory=dict)
    node_effects: dict = field(default_factory=dict)
    semantic_functions: dict = field(default_factory=dict)

    REPORT_GUARDS_CAP = 24

    def report(self):
        from ibl_v2_access import describe_accesses
        status = "invalid" if self.issues else ("incomplete" if self.guards else "valid")
        # 보고서는 모델 경계(액션당 16K)에 들어야 한다. 4082 실측: 저장 관용구 호출 한 줄의 check 가 guards 62개(76KB)
        # + 스크립트 의존 스냅샷(64KB) = 14만 자로 스필돼 모델이 파일을 다시 읽었다. guards 는 상한 뒤 수만,
        # 의존 스냅샷은 지문만 — 재개 지문(plan_hash)은 그대로다.
        dependencies = {**self.dependencies,
                        "calls": {k: digest(v) for k, v in (self.dependencies.get("calls") or {}).items()}}
        # 호출한 *저장* 함수 안의 실행 시 검사는 그 함수의 몫(describe 의 runtime_checks)이다 — 이 프로그램의 보고서엔
        # 제출 원문(지역 함수 포함, location.source == "<program>") 자리의 검사만 싣고 안쪽은 수로 남긴다.
        own = [g for g in self.guards if (g.get("location") or {}).get("source", "<program>") == "<program>"]
        return {"edition": 2, "mode": "check", "executed": False, "ok": not self.issues,
                "status": status, "issues": self.issues, "guards": own[:self.REPORT_GUARDS_CAP],
                "guards_total": len(self.guards), "guards_inner": len(self.guards) - len(own),
                "guards_omitted": max(0, len(own) - self.REPORT_GUARDS_CAP),
                "result_type": str(self.result_type), "result_contract": describe_type(self.result_type), "effects": sorted(self.effects), "functions": self.function_contracts,
                "plan_hash": self.fingerprint, "dependencies": dependencies,
                "accesses": describe_accesses(self.accesses, self.effects),
                "components": {key: {name: c[name] for name in ('protocol', 'identity', 'producer', 'dependencies', 'completion')}
                               for key, c in self.components.items()},
                "source_hash": digest(self.source[:self.dependencies["source_map"][0]["end"]]),
                "capabilities": ["ibl-edition/2", "ibl-value/1"],
                **({"unspecified_inputs": sorted(self.unspecified)} if self.unspecified else {}),
                "preflight": self.preflight, "warnings": self.preflight.get("warnings", []),
                "note": "incomplete는 미확정 타입의 실행 시 검사를 포함합니다. 업무 품질·전건 완료의 보증이 아닙니다."}


from ibl_v2_call_analysis import CallAnalysis


class Compiler(CallAnalysis):
    def __init__(self, source, registry, inputs, definitions=None, declared_inputs=None, input_types=None):
        self.source, self.registry = source, registry
        self.definitions, self.external = definitions if definitions is not None else {}, {}
        self.source_map = [{"name": "<program>", "start": 0, "end": len(source)}]
        self.inputs = {k: infer(v) for k, v in inputs.items()}
        # input_types: 값 없이 타입만 아는 입력(앱 템플릿의 저술 시점 검사 — 전부 Unknown). 실행에는 쓰지 않는다.
        self.inputs.update(input_types or {})
        # 선언됐지만 제공되지 않은 입력 — 인자 자리에서 생략, 보간에서 "", 그 밖의 자리는 거절(UNSPECIFIED_INPUT).
        self.unspecified = frozenset(declared_inputs or ()) - set(self.inputs)
        self.functions, self.scopes, self.function_scopes = {}, {}, {}
        self.issues, self.guards, self.effects = [], [], set()
        self.warnings = []  # 실행을 막지 않는 관측 불일치 — preflight.warnings 로 합류
        self.stack, self.checked = [], set()
        self.call_path = []
        self.returns = []
        self.function_contracts = {}
        self.used_actions = set()
        self.call_dependencies = {}
        # 방문 중 만난 읽기/쓰기 자원과 미확정 의무 — 병렬 가지·each 병렬 본문이 괄호로 묶어 충돌을 본다(70회차 B70-2).
        self.access_log = set()
        self.reachable = True
        self.catch_value_faults = False
        self.default_scope = frozenset()  # 기본값 식을 검사하는 동안의 인자 이름들
        self.unit_warned = set()
        self.impure_spans = []
        self.pure_calls, self.call_effects = [], {}
        self.constant_bindings = {}
        self.init_call_analysis()
        self.requirements, self.required_calls = {}, {}
        self.requirement_log = {}
        self.requirement_depth = 0
        self.node_effects = {}
        self.component_declarations = {}
        self.component_variants = {}

    def issue(self, node, code, message, **details):
        item = {"code": code, "message": message, "source_span": span(self.source, node),
                "call_path": copy.deepcopy(self.call_path), **details}
        # Value failures remain observable inside recovery expressions. Syntax,
        # effects, permissions and definition contracts are still compile errors.
        if self.catch_value_faults and code in {
                'TYPE', 'NUMBER_REQUIRED', 'ARITHMETIC', 'FIELD_TYPE', 'MISSING_FIELD', 'FORMAT_TYPE'}:
            item.update(expected='복구 경계 안에서 실행 시 확인', recoverable=True)
            if item not in self.guards:
                self.guards.append(item)
        elif item not in self.issues:
            self.issues.append(item)

    def warn(self, node, code, message, **facts):
        item = {"code": code, "rule": code, "severity": "warning", "message": message,
                "source_span": span(self.source, node), "call_path": copy.deepcopy(self.call_path),
                "facts": facts, "hint": HINTS.get(code, "해당 위치의 계약과 실제 결과를 확인하세요.")}
        if item not in self.warnings:
            self.warnings.append(item)

    def omitted(self, node, env):
        """미지정 입력을 그대로 가리키는 자리인가 — 그 자리는 값이 아니라 '없음'이다(인자 생략·보간 "")."""
        return (isinstance(node, Node) and node.kind == "ref" and node.data["name"] in self.unspecified
                and node.data["name"] not in env)

    def need(self, node, actual, expected):
        from ibl_v2_requirements import require
        require(self, node, actual, expected)
        if actual.kind == "Unknown":
            item = {"source_span": span(self.source, node), "expected": str(expected),
                    "actual": str(actual), "call_path": copy.deepcopy(self.call_path)}
            if item not in self.guards:
                self.guards.append(item)
        elif not compatible(actual, expected):
            hint = " 레코드 봉투의 행 목록은 .items로 꺼내 전달하세요." if expected.kind == "List" and actual.kind == "Record" else ""
            self.issue(node, "TYPE", f"{expected}가 필요하지만 {actual}입니다.{hint}",
                       expected=str(expected), actual=str(actual))

    def pure(self, node):
        if node is None:
            return
        if any(start <= node.start and node.end <= end for start, end in self.impure_spans):
            return
        if node.kind in ("lambda", "callable_ref"):
            return  # creating a callable does not execute its latent body
        if node.kind in ("call", "pure_call", "named_call") and node.data.get("body") is None:
            # 순수 자리의 기준은 호출 문법이 아니라 효과다. 효과 없는 함수는 식과 같다 — 효과는 방문 뒤에 확인한다.
            if all(node is not seen for seen in self.pure_calls):
                self.pure_calls.append(node)
            self.check_children(node.data.get("params"), self.pure)
            self.check_children(node.data.get("args"), self.pure)
            self.check_children(node.data.get("fn"), self.pure)
            return
        if node.kind == "pipe":
            self.pure(node.data["left"])
            self.pure(node.data["right"])
            return
        if node.kind not in PURE_KINDS:
            self.impure_spans.append((node.start, node.end))
            hint = HINTS["PURE_EXPRESSION"]
            message = "이 자리에는 순수 식만 쓸 수 있습니다. 호출·조합은 앞 문장에 두세요."
            if node.kind in ("if", "case"):
                message = "이 자리에는 순수 식만 쓸 수 있습니다. 제어 블록 대신 조건 값을 쓰세요."
                hint = "값을 고르는 분기는 `조건 ? 값1 : 값2`입니다. 예: ($a,$r)=>$r.n > $a ? $r.n : $a"
            elif node.kind == "call" and node.data.get("body") is not None:
                hint = ("파이프 전체를 앞 문장 $변환 = 목록 >> [table:each]{...}에 받고 "
                        "현재 식에는 $변환을 쓰세요. 람다 안의 순수 목록 변환은 "
                        "reduce($목록,[],($누적,$행)=>$누적+[$행.필드])로 표현할 수 있습니다.")
            self.issue(node, "PURE_EXPRESSION", message, hint=hint)
            return
        for value in node.data.values():
            self.check_children(value, self.pure)

    def container_value(self, node):
        """Construct values with calls, without adding a statement/return scope.

        Calls own their argument checks and each/function return frames.
        값을 만드는 자리 — 객체·목록 값, 그리고 2026-09-30 개정으로 연산 피연산자·내장 함수 인자·
        보간·슬라이스 — 는 호출·조합을 원문 순서로 그 자리에서 평가한다. 실행 여부나 횟수가 갈리는
        자리(조건·조건 값·and/or·기본값·순수 콜백 적용)는 각자의 방문에서 pure()가 재귀로 지키므로,
        값 자리로 감싸도 그 안에 효과를 숨길 수 없다.
        """
        if node.kind in ("call", "lambda"):
            return
        if node.kind not in PURE_KINDS | {"pipe", "parallel", "fallback"}:
            hint = ("값을 고르는 분기는 조건 값 `조건 ? 값1 : 값2`로 씁니다(가지가 여럿이면 사슬로). "
                    "문장이 필요한 분기만 앞 문장의 [if:]나 함수 본문에 두세요."
                    if node.kind in ("if", "case") else HINTS.get("VALUE_EXPRESSION"))
            self.issue(node, "VALUE_EXPRESSION",
                       "값 자리(객체·목록·연산·내장 함수 인자·보간)에는 식·호출·조합을 쓰세요. "
                       "제어 블록은 앞 문장이나 함수 본문에 두세요.", **({"hint": hint} if hint else {}))
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
        # Only straight-line bindings in this frame are proven constants. Nested
        # functions/loops/branches start fresh; assignments invalidate prior facts.
        outer, self.constant_bindings = self.constant_bindings, {}
        try:
            return self._sequence(node, env, names, readonly, final)
        finally:
            self.constant_bindings = outer

    def _sequence(self, node, env, names, readonly=frozenset(), final=False):
        names = self.predeclare(node, names)
        result = UNIT_T
        terminated = False
        dead_env = None
        for statement in node.data["statements"]:
            from ibl_v2_analysis import constant_value
            from ibl_callable_contract import UNRESOLVED
            value = (constant_value(statement.data["value"], bindings=self.constant_bindings)
                     if statement.kind == "bind" else UNRESOLVED)
            for name in assigned_names(statement):
                self.constant_bindings.pop(name, None)
            if terminated:
                # Still diagnose invalid dead source, but it cannot supply a
                # frame result or add return types to the reachable paths.
                old_returns, self.returns = self.returns, []
                self.visit_branch(statement, dead_env, names, readonly, final, False)
                self.returns = old_returns
            else:
                result = self.visit(statement, env, names, readonly, final)
                if statement.kind == "bind" and value is not UNRESOLVED:
                    self.constant_bindings[statement.data["name"]] = value
                if result == NEVER:
                    terminated, dead_env = True, env.copy()
        return result

    def visit_unreachable(self, node, env, names, readonly=frozenset(), final=False):
        """Still type-check dead source, but do not invent executable writes."""
        previous, self.reachable = self.reachable, False
        try:
            return self.visit(node, env, names, readonly, final)
        finally:
            self.reachable = previous

    def visit_branch(self, node, env, names, readonly, final, possible, *, pure=False, piped=None, piped_node=None):
        if possible:
            if pure:
                self.pure(node)
            return self.visit(node, env, names, readonly, final, piped=piped, piped_node=piped_node)
        # Dead source still receives syntax/name/type checks, but cannot impose
        # latent callback purity, executable effects or return types on the call.
        if node is not None:
            self.pure_calls = [call for call in self.pure_calls
                               if not (node.start <= call.start and call.end <= node.end)]
        outer = (self.effects, self.access_log, self.returns, self.pure_calls,
                 self.call_effects)
        self.effects, self.access_log, self.returns = set(), set(), []
        self.pure_calls, self.call_effects = [], {}
        dead = dict.fromkeys(env, NEVER)
        try:
            previous, self.reachable = self.reachable, False
            try:
                self.visit(node, dead, names, readonly, final, piped=piped, piped_node=piped_node)
            finally:
                self.reachable = previous
            env.clear()
            env.update(dict.fromkeys(dead, NEVER))
        finally:
            (self.effects, self.access_log, self.returns, self.pure_calls,
             self.call_effects) = outer
        return NEVER

    def resolve_function(self, name, names):
        if name in names:
            return names[name]
        if name in self.external:
            return self.external[name]
        if name not in self.definitions:
            return None
        from ibl_v2_semantic_store import resolve
        resolved = resolve(self, name)
        if resolved is not None:
            return resolved
        from ibl_v2_parser import Parser
        from ibl_v2_store import definition_name
        code = self.definitions[name]
        if code is None:
            reason = getattr(self.definitions, 'interface_limits', {}).get(name, 'interface unavailable')
            raise Fault('SEMANTIC_INTERFACE_REQUIRED', f'{name}: {reason}', kind='compile')
        if definition_name(code) != name:
            raise Fault("LIBRARY_NAME", f"등록 이름과 정의 이름이 다릅니다: {name}", kind="compile")
        offset = len(self.source) + 1
        self.source += "\n" + code
        self.source_map.append({"name": name, "start": offset, "end": len(self.source),
                                "function_ref": getattr(self.definitions, "references", {}).get(name)})
        body = Parser(code, offset).program()
        symbols = self.predeclare(body, {})
        self.external[name] = symbols[name]
        return symbols[name]

    def _function(self, sid, args, call=None):
        node = self.functions[sid]
        self.requirements.setdefault(sid, {})
        if sid in self.stack:
            self.issue(node, "RECURSION", f"재귀 호출은 지원하지 않습니다: {node.data['name']}")
            return UNKNOWN
        self.stack.append(sid)
        self.call_path.append({"function": node.data["name"],
                               "call": span(self.source, call) if call else None,
                               "definition": span(self.source, node)})
        old_returns, self.returns = self.returns, []
        outer_effects, self.effects = self.effects, set()
        outer_actions, self.used_actions = self.used_actions, set()
        params = node.data["params"]
        from ibl_v2_component import declaration
        if sid not in self.component_declarations:
            try:
                self.component_declarations[sid] = declaration(node)
            except Fault as exc:
                self.issue(node, exc.code, str(exc))
                self.component_declarations[sid] = {}
        env = {}
        for name, default in params.items():
            if name in RESERVED:
                self.issue(node, "RESERVED", f"예약 바인딩은 인자로 쓸 수 없습니다: {name}")
            dtype = UNKNOWN
            if default:
                self.pure(default)
                self.default_scope = frozenset(params)
                dtype = self.visit(default, {}, {}, frozenset(), False)
                self.default_scope = frozenset()
            from ibl_v2_requirements import parameter
            env[name] = args.get(name, parameter(sid, name) if default is None else dtype)
        explicit = {}
        from ibl_v2_analysis import constant_value
        from ibl_v2_requirements import annotation
        for name, declaration in node.data.get('annotations', {}).items():
            try:
                expected = declared(constant_value(declaration))
            except ValueError as exc:
                self.issue(declaration, 'TYPE', str(exc))
                continue
            annotation(self, declaration, env[name], expected)
            explicit[name] = describe_type(expected)
            if env[name].kind == 'Unknown':
                env[name] = expected
        parameter_types = {k: str(v) for k, v in env.items()}
        parameter_contracts = {k: describe_type(v) for k, v in env.items()}
        result = self.sequence(node.data["body"], env, self.function_scopes[sid])
        for t in self.returns:
            result = join(result, t)
        kinds = {t.kind for t in alternatives(result)}
        if self.returns and "Unit" in kinds and len(kinds) > 1 and sid not in self.unit_warned:
            # 값을 돌려주는 경로와 떨어지는 경로가 섞인 함수는 거의 늘 else/return 누락이다(70회차 F70-2).
            self.unit_warned.add(sid)
            self.warn(node, "UNIT_RETURN_PATH",
                      f"함수 {node.data['name']}의 일부 경로가 값을 반환하지 않아 결과에 Unit이 섞입니다: {result}",
                      function=node.data['name'], result=str(result))
        effects, actions = self.effects, self.used_actions
        if call is not None:
            self.call_effects.setdefault(call.id, set()).update(effects)
        self.effects, self.used_actions = outer_effects | effects, outer_actions | actions
        self.returns = old_returns
        self.stack.pop()
        self.call_path.pop()
        self.checked.add(sid)
        from ibl_v2_access import describe_accesses
        observed = {'accesses': describe_accesses(self.access_log, effects), 'params': parameter_types, 'result': str(result),
                    'param_contracts': parameter_contracts,
                    'result_contract': describe_type(result)}
        summary = self.function_contracts.setdefault(sid, {
            'name': node.data['name'], 'params': parameter_types.copy(),
            'accesses': observed['accesses'],
            'param_contracts': observed['param_contracts'],
            'requirements': self.requirements.get(sid, {}),
            'requirements_protocol': 'ibl-requirements/1',
            'declared_requirements': explicit,
            'result_contract': observed['result_contract'],
            'required': [k for k,v in params.items() if v is None],
            'pipe_input': next(iter(params), None),
            'default_expressions': {k: self.source[v.start:v.end] for k, v in params.items() if v is not None},
            'effects': [], 'actions': [],
            'source_hash': digest(self.source[node.start:node.end]),
            'result': str(result), 'specializations': [], 'specializations_omitted': 0})
        summary['effects'] = sorted((set(summary['effects']) | effects) - {'pure'}) or ['pure']
        summary['actions'] = sorted(set(summary['actions']) | actions)
        for key, value in parameter_types.items():
            if summary['params'][key] != value:
                summary['params'][key] = 'Unknown'
        if summary['result'] != str(result):
            summary['result'] = 'Unknown'
        if summary['result_contract'] != observed['result_contract']:
            summary['result_contract'] = {'type': 'input-dependent', 'specializations': True}
        if summary['param_contracts'] != observed['param_contracts']:
            summary['param_contracts'] = {'specializations': True}
        if observed not in summary['specializations']:
            if len(summary['specializations']) < 32:
                summary['specializations'].append(observed)
            else:
                summary['specializations_omitted'] += 1
        return result

    def visit(self, node, env, names, readonly=frozenset(), final=False, piped=None, piped_node=None):
        if node is None:
            return UNIT_T
        outer, self.effects = self.effects, set()
        try:
            return self._visit(node, env, names, readonly, final, piped, piped_node)
        finally:
            self.node_effects.setdefault(node.id, set()).update(self.effects)
            self.effects |= outer

    def _visit(self, node, env, names, readonly=frozenset(), final=False, piped=None, piped_node=None):
        if node is None:
            return UNIT_T
        d, kind = node.data, node.kind
        def sub(n, e=env, conditional=False):
            self.requirement_depth += int(conditional)
            try:
                return self.visit(n, e, names, readonly, final)
            finally:
                self.requirement_depth -= int(conditional)
        if kind == "sequence":
            return self.sequence(node, env, names, readonly, final)
        if kind == "literal":
            if type(d["value"]) is str:
                import re
                if re.search(r"\$[\w]+\.[\w]", d["value"]):
                    self.warn(node, "LITERAL_DOLLAR", "이 문자열의 $변수.필드는 판본 2에서 문자 그대로입니다. 값 참조나 f 문자열의 ${표현식}을 사용하세요.")
                elif re.search(r"\{\$[\w]+\}|\$\{", d["value"]):
                    # 100회차 L100-7: 평문 "w_{$it}.txt" 는 보간이 아니라 글자다 — 병렬 each 에서 전 행이 같은 파일에 쓰는 거절로만 드러났다.
                    self.warn(node, "LITERAL_BRACE", "평문 문자열의 {$이름}·${…}은 보간되지 않고 문자 그대로입니다. 보간은 f\"…${식}…\" 만입니다.")
                return Type("Text", literal=d["value"])
            if type(d["value"]) is int:
                return Type("Number", literal=d["value"])
            return infer(d["value"])
        if kind == "ref":
            if d["name"] not in env:
                extra = {}
                if d["name"] in self.unspecified:
                    self.issue(node, "UNSPECIFIED_INPUT",
                               f"미지정 입력 ${d['name']} 은 호출 인자 자리(인자 생략)와 f-문자열 보간(빈 문자열)에서만 쓸 수 있습니다.",
                               hint="값이 필요하면 표면 입력에 default 를 선언하거나, 호출 앞 문장에서 조건 값으로 정하세요.")
                    return UNKNOWN
                if d["name"] in self.default_scope:
                    extra["hint"] = ("기본값 식은 호출 전에 따로 평가되어 다른 인자를 볼 수 없습니다. 인자에 따라 정해지는 값은 "
                                     "기본값 인자로 두지 말고 함수 본문에서 계산하세요(예: $최종 = $가격 * (1 - $율)).")
                elif self.inputs and d["name"] not in self.inputs:
                    # 결과 참조의 input_hint 가 이름 변경을 권하므로 흔한 실수다 — 실제 입력 이름을 알린다(69회차 F69-3).
                    names = ", ".join("$" + n for n in sorted(self.inputs)[:8])
                    extra["hint"] = (f"이 프로그램에 전달된 inputs 이름은 {names}입니다. 코드의 변수 이름과 inputs 이름을 "
                                     "맞추세요. 새 값이면 이 위치 전에 정의하세요.")
                self.issue(node, "UNBOUND", f"정의되지 않은 값: ${d['name']}", **extra)
            return env.get(d["name"], UNKNOWN)
        if kind == "bind":
            name = d["name"]
            if name in readonly or name in RESERVED:
                self.issue(node, "READONLY", f"읽기 전용 바인딩: ${name}")
            if self.reachable and self.returns_unconditionally(d["value"]):
                # 블록을 값으로 받으려다 가지마다 return 을 쓴 모양 — return 은 함수 전체를 끝내 대입이 일어나지 않고
                # 뒤 문장은 죽은 코드가 된다(긴문장 29회차 L29-2: 검사가 말없이 통과시켜 보고서 칸이 빠졌다).
                # 뒤가 `return $이름` 뿐이면 결과가 같아 쓰이던 모양이라 거절하지 않고 경고한다.
                self.warn(node, "BIND_RETURNS",
                          f"${name} 에 대입하는 블록의 모든 경로가 return 으로 끝납니다 — return 은 블록이 아니라 "
                          f"함수 전체를 끝내므로 ${name} 은 값을 받지 못하고 이 뒤의 문장은 실행되지 않습니다.", name=name)
            env[name] = sub(d["value"])
            return NEVER if env[name] == NEVER else UNIT_T
        if kind == "assert":
            for key in ("condition", "message", "details"):
                self.pure(d[key])
            self.need(node, sub(d["condition"]), BOOL)
            failure_possible = known_condition(d['condition'], env) is not True
            if d["message"] is not None:
                message_type = sub(d["message"])
                if failure_possible:
                    self.need(node, message_type, TEXT)
            if d["details"] is not None:
                details_type = sub(d["details"])
                if failure_possible:
                    self.need(node, details_type, Type("Record"))
            return UNIT_T
        if kind == "return":
            if final:
                self.issue(node, "FINALLY_RETURN", "finally 안에는 return을 쓸 수 없습니다.")
            result = sub(d["value"])
            if result != NEVER:
                self.returns.append(result)
            return NEVER
        if kind == "def":
            return UNIT_T
        if kind == "list":
            self.container_value(node)
            return ordered_list(sub(v) for v in d["values"])
        if kind == "record":
            self.container_value(node)
            from ibl_v2_semantic import record_type
            entries = d.get("entries", list(d.get("fields", {}).items()))
            # Omitted surface inputs are absent arguments, not Unknown values.
            return record_type(self, [(k, sub(v), v) for k, v in entries
                                      if k is None or not self.omitted(v, env)])
        if kind == "slice":
            self.container_value(node)
            base = sub(d["base"])
            self.need(node, base, join(TEXT, Type("List", item=UNKNOWN)))
            for key in ("lower", "upper", "stride"):
                if d[key] is not None:
                    self.need(d[key], sub(d[key]), join(NUMBER, NULL))
                    if d[key].kind == "literal":
                        v = d[key].data["value"]
                        if v is not None and (type(v) is not int or key == "stride" and v == 0):
                            self.issue(d[key], "SLICE_BOUND", "슬라이스는 정수 경계와 0이 아닌 간격을 받습니다.")
            return Type("List", item=base.item or UNKNOWN) if base.kind == "List" else base
        if kind in ("field", "index"):
            base = sub(d["base"])
            key = d.get("key")
            key_type = None
            if isinstance(key, Node):
                key_type = sub(key)
                key = key.data["value"] if key.kind == "literal" else key_type.literal
            return access_type(self, node, base, key, key_type)
        if kind in ("binary", "unary"):
            op = d["op"]
            if kind == "binary" and op in ("and", "&&", "or", "||"):
                from ibl_v2_narrow import predicate, branch_environment
                self.pure(d['left'])
                left = sub(d['left'])
                right_env, possible = branch_environment(env, predicate(d['left']), op in ('and', '&&'))
                self.requirement_depth += 1
                try:
                    right = self.visit_branch(d['right'], right_env, names, readonly, final, possible, pure=True)
                finally:
                    self.requirement_depth -= 1
                self.need(node, left, BOOL)
                self.need(node, right, BOOL)
                from ibl_v2_narrow import predicate_value
                return predicate_value(BOOL, predicate(node), env)
            self.container_value(node)
            values = ([sub(d["value"])] if kind == "unary" else [sub(d["left"]), sub(d["right"])])
            operands = [d["value"]] if kind == "unary" else [d["left"], d["right"]]
            from ibl_v2_semantic import scalar_type
            from ibl_v2_narrow import predicate, predicate_value
            return predicate_value(scalar_type(self, node, op, values, operands), predicate(node), env)
        if kind == "conditional":
            from ibl_v2_narrow import predicate, branch_environment
            self.pure(d['condition'])
            self.need(d['condition'], sub(d['condition']), BOOL)
            guard = predicate(d['condition'])
            result = NEVER
            self.requirement_depth += 1
            try:
                for truth, branch in ((True, 'yes'), (False, 'no')):
                    local, possible = branch_environment(env, guard, truth)
                    result = join(result, self.visit_branch(d[branch], local, names, readonly,
                                                           final, possible, pure=True))
            finally:
                self.requirement_depth -= 1
            return result
        if kind == "builtin":
            if d["name"] not in BUILTINS:
                from common.expression_ops import unknown_builtin_message
                self.issue(node, "BUILTIN", unknown_builtin_message(d["name"]))
            return Type("Callable", item=("builtin", d["name"]))
        if kind == "callable_ref":
            return self.reference_type(node, names)
        if kind == "named_call":
            fn_type = sub(d["fn"])
            if fn_type == NEVER:
                self.visit_branch(d["params"], env.copy(), names, readonly, final, False)
                return NEVER
            arg_type = sub(d["params"])
            return self.apply_callable(node, fn_type, arg_type, d["params"], env, names, readonly,
                                       piped=piped)
        if kind == "pure_call":
            self.container_value(node)
            fn_type = sub(d["fn"])
            nodes = list(d["args"])
            types = [sub(a) for a in nodes]
            if piped is not None:
                types.insert(0, piped)
                nodes.insert(0, piped_node or node)
            return self.apply_callable(node, fn_type, types, nodes, env, names, readonly)
        if kind == "lambda":
            params = d["params"]
            if len(set(params)) != len(params) or RESERVED.intersection(params):
                self.issue(node, "PARAMETERS", "람다 인자는 중복·예약 이름을 쓸 수 없습니다.")
            self.container_value(d["body"])
            typ = self.lambda_type(node, env, names, readonly)
            return typ
        if kind == "format":
            from ibl_v2_semantic import format_type
            parts = []
            for part in d["parts"]:
                if isinstance(part, Node):
                    if self.omitted(part, env):
                        parts.append((Type("Text", literal=""), part))
                        continue
                    self.container_value(part)
                    parts.append((sub(part), part))
                else:
                    parts.append((Type("Text", literal=part), node))
                    if isinstance(part, str) and _BARE_DOLLAR_NAME.search(part):
                        self.warn(node, "FORMAT_UNINTERPOLATED",
                                  "f-문자열 안의 $이름 이 ${…} 밖에 있어 보간되지 않고 문자 그대로 남습니다.",
                                  text=_BARE_DOLLAR_NAME.search(part)[0])
            return format_type(self, parts)
        if kind == "pipe":
            left = sub(d["left"])
            if d["right"].kind not in ("call", "pure_call", "named_call"):
                details = {}
                if d["right"].kind == "parallel":
                    details = {"actual": "parallel", "hint":
                               "&가 >>보다 먼저 묶입니다. A >> B & C >> D는 "
                               "(A >> (B & C)) >> D로 해석됩니다. 독립된 파이프를 "
                               "병렬 실행하려면 (A >> B) & (C >> D)처럼 각 가지를 "
                               "괄호로 묶으세요. 병렬 결과를 넘기려면 (A & B) >> C입니다."}
                self.issue(node, "PIPE_TARGET", "파이프 오른쪽은 명시 입력이 있는 호출이어야 합니다.",
                           **details)
                return UNKNOWN
            if left == NEVER:
                self.visit_branch(d["right"], env.copy(), names, readonly, final, False, piped=NEVER, piped_node=d["left"])
                return NEVER
            return self.visit(d["right"], env, names, readonly, final, piped=left, piped_node=d["left"])
        if kind == "parallel":
            from ibl_v2_semantic import parallel_type
            return parallel_type(self, node, [lambda branch=branch: sub(branch, env.copy())
                                              for branch in parallel_branches(node)])
        if kind == "fallback":
            from ibl_v2_exits import source_fallback
            return source_fallback(self, node, env, names, readonly, final)
        if kind == "call":
            arg_type = sub(d["params"])
            return self.named_target(node, arg_type, env, names, readonly, piped)
        if kind == "if":
            from ibl_v2_narrow import predicate, branch_environment
            self.pure(d['value'])
            self.need(node, sub(d['value']), BOOL)
            guard = predicate(d['value'])
            paths, result = [], NEVER
            self.requirement_depth += 1
            try:
                for truth, branch in ((True, 'body'), (False, 'otherwise')):
                    local, possible = branch_environment(env, guard, truth)
                    result = join(result, self.visit_branch(d[branch], local, names, readonly, final, possible))
                    # Lexical definite assignment remains independent of actual inputs.
                    paths.append((d[branch], local))
            finally:
                self.requirement_depth -= 1
            self.merge_continuations(env, paths)
            return result
        if kind == "case":
            self.pure(d["value"])
            sub(d["value"])
            environments, types = [], []
            for condition, body in d["branches"]:
                self.pure(condition)
                sub(condition)
                child = env.copy()
                types.append(sub(body, child, True))
                environments.append((body, child))
            child = env.copy()
            types.append(sub(d["otherwise"], child, True))
            environments.append((d["otherwise"], child))
            self.merge_continuations(env, environments)
            result = types[0]
            for t in types[1:]:
                result = join(result, t)
            return result
        if kind == "repeat":
            from ibl_v2_repeat import source_repeat
            return source_repeat(self, node, env, names, readonly, final)
        if kind == "try":
            from ibl_v2_recovery import source_recovery
            return source_recovery(self, node, env, names, readonly, final)
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
        if kind == "bind":
            return recur(d["value"])
        if kind == "pipe":
            return recur(d["left"]) or recur(d["right"])
        if kind == "named_call":
            return recur(d["fn"])
        if kind == "fallback":
            return recur(d["left"]) and recur(d["right"])
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

    def named_target(self, node, arg_type, env, names, readonly, piped=None):
        if arg_type.kind == 'Union':
            result = NEVER
            for arguments in alternatives(arg_type):
                result = join(result, self.named_target(node, arguments, env, names, readonly, piped))
            return result
        d = node.data
        if d['node'] == 'fn' or (d['node'], d['action']) == ('table', 'each'):
            return self._named_target(node, arg_type, env, names, readonly, piped)
        frame = {'function': d['node'] + ':' + d['action'],
                 'call': span(self.source, node), 'definition': None}
        # Primitive contracts have no body to unfold. Their transfer summary
        # retains the call site because adapter diagnostics/dependencies own it.
        identity = ('action', node.id, frame['function'], arg_type, piped,
                    digest(self.constant_bindings))
        return self.summary(identity, node, frame,
                            lambda: self._named_target(node, arg_type, env, names, readonly, piped),
                            'action')

    def _named_target(self, node, arg_type, env, names, readonly, piped=None):
        d = node.data
        args = dict(arg_type.fields)
        d["open_arguments"] = arg_type.open
        if arg_type.open:
            self.need(d['params'], UNKNOWN, Type('Record'))
        key = f"{d['node']}:{d['action']}"
        if d.get("target") and (d["node"] == "fn" or key == "table:each"):
            self.issue(node, "TARGET_NODE", f"노드 지정 @{d['target']} 은 도구 호출에만 붙습니다 — 함수·each 블록에는 쓸 수 없습니다.")
        if key == "table:each":
            return self.each(node, args, env, names, piped)
        if d["node"] == "fn":
            sid = d.get("symbol") or self.resolve_function(d["action"], names)
            if sid:
                d["symbol"] = sid
                params = self.functions[sid].data["params"]
                receiver = next(iter(params), None)
                self.arguments(node, args, params, receiver, piped)
                return self.function(sid, args, node)
            conflict = getattr(self.definitions, "conflicts", {}).get(d["action"])
            if conflict:
                # 겹친 저장 이름은 부르는 자리만 거절한다 — 무관한 프로그램은 돈다 (71회차 B71-1).
                self.issue(node, "DUPLICATE_LIBRARY",
                           f"같은 이름의 저장 정의가 여럿이라 고를 수 없습니다: {d['action']} ({', '.join(conflict)})")
                return UNKNOWN
            if key not in self.registry:
                self.issue(node, "FUNCTION", f"등록된 함수가 없습니다: {d['action']}")
                return UNKNOWN
        spec = self.registry.get(key)
        if not spec:
            self.effects.add('unknown')
            self.issue(node, "UNSUPPORTED_ADAPTER", f"판본 2 계약이 없는 어휘: {key}")
            return UNKNOWN
        from ibl_callable_contract import normalize, selected, problems, UNRESOLVED
        try:
            args = normalize(spec.contract, args)
            fields = normalize(spec.contract, record_fields(d["params"]))
        except Fault as exc:
            self.issue(node, exc.code, str(exc))
            return UNKNOWN
        from ibl_v2_analysis import constant_value
        values = {k: constant_value(v, bindings=self.constant_bindings) for k, v in fields.items()}
        for arg in args:
            if values.get(arg, UNRESOLVED) is UNRESOLVED:
                values[arg] = args[arg].literal if args[arg].literal is not None else UNRESOLVED
        if arg_type.open:
            for arg in spec.contract['params']:
                values.setdefault(arg, UNRESOLVED)
        # Argument relationships see the same receiver as runtime.invoke.
        # The value is not known here, but its presence is statically known.
        from ibl_callable_contract import pipe_receiver
        receiver = pipe_receiver(spec.contract, values)
        if piped is not None and receiver and receiver not in values:
            values[receiver] = UNRESOLVED
        self.used_actions.add(key)
        if spec.dependency:
            selectors = {k: v for k, v in values.items() if v is not UNRESOLVED}
            snapshot = spec.dependency(selectors)
            d['dependency_args'], d['dependency_snapshot'] = selectors, snapshot
            binding = {'args': selectors, 'snapshot': snapshot}
            bindings = d.setdefault('dependency_bindings', [])
            if binding not in bindings:
                bindings.append(binding)
            self.call_dependencies[node.id + ":" + key + ":" + digest(selectors)] = snapshot
        contract = selected(spec.contract, values)
        if spec.specialize and not d.get('target'):
            # Nested literal selectors remain known even when a sibling
            # argument (e.g. window_id/source) is supplied at runtime.
            # These partial values are only for contract selection, never
            # dependency snapshots, receipts or execution arguments.
            partial = {k: constant_value(v, partial_records=True, bindings=self.constant_bindings)
                       for k, v in fields.items()}
            selectors = {**values, **{k: v for k, v in partial.items() if v is not UNRESOLVED}}
            contract = spec.specialize(contract, selectors)
        self.component_variants.setdefault(key, {})[digest(contract)] = contract
        from ibl_value_checks import value_problems
        for problem in ([] if arg_type.open else problems(contract, values)) + value_problems(contract, values, self.registry, self.definitions):
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
        self.arguments(node, args, allowed, pipe_receiver(contract, args), piped,
                       hint=contract.get("unknown_param_hint"))
        if contract.get("adapter", {}).get("protocol") == "core-table/2" and "items" in args:
            # 행 목록 자리의 봉투는 그 행 목록이다 — join·groupby·dedup 의 결과를 그대로 이어 받는다.
            args["items"] = rows_type(args["items"])
        from ibl_v2_semantic import apply_primitive
        return apply_primitive(self, node, key, spec, contract, args, fields, values, env, names, readonly)

    def arguments(self, node, args, params, receiver, piped, hint=None):
        if piped is not None:
            if receiver is None or receiver in args:
                from ibl_v2_analysis import pipe_collision_message
                d = node.data
                callee = f"[{d['node']}:{d['action']}]" if d.get("node") and d.get("action") else ""
                self.issue(node, "PIPE_COLLISION", pipe_collision_message(callee, receiver))
            else:
                args[receiver] = piped
        for name, default in params.items():
            if name not in args and node.data.get("open_arguments"):
                args[name] = UNKNOWN
            elif name not in args and default is None:
                self.issue(node, "MISSING_ARGUMENT", f"필수 인자 누락: {name}")
        for name in args.keys() - params.keys():
            from difflib import get_close_matches
            candidates = get_close_matches(name, params, n=3, cutoff=0.45)
            near = f" 비슷한 인자: {', '.join(candidates)}." if candidates else ""
            # 계약의 안내(선언 데이터)가 있으면 덧붙인다 — 받지 않는 필터를 어디서 하는지(예: 받은 행을 거르는 자리).
            note = f". {hint}" if hint else ""
            self.issue(node, "UNKNOWN_ARGUMENT", f"알 수 없는 인자: {name}.{near} 사용 가능한 인자: {', '.join(sorted(params))}{note}")

    def each(self, node, args, env, names, piped):
        self.arguments(node, args, {"items": None, "mode": UNIT, "on_error": UNIT, "parallel": UNIT}, "items", piped)
        fields = record_fields(node.data["params"])
        options = {}
        for key, default in (("mode", "map"), ("on_error", "stop"), ("parallel", 1)):
            value = fields.get(key)
            if value is None and (key in args or node.data.get("open_arguments")):
                self.issue(node, "STATIC_OPTION", f"펼친 each의 {key}는 뒤에 리터럴로 명시하세요.")
            if value and value.kind != "literal":
                self.issue(value, "STATIC_OPTION", f"{key}는 컴파일 시 리터럴이어야 합니다.")
            options[key] = value.data.get("value") if value else default
        from ibl_v2_semantic import iteration_type
        def analyze(element):
            local = {**env, "it": element, "i": NUMBER}
            return self.visit(node.data["body"], local, names, frozenset(env) | RESERVED)
        return iteration_type(self, node, args.get("items", UNKNOWN), options, analyze)

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


@compilation_dependencies()
def compile_program(source, registry=None, inputs=None, definitions=None, *, declared_inputs=None, input_types=None, value_protocols=None):
    """declared_inputs: 표면이 템플릿에서 참조하는 입력 이름 전부. inputs 에 없는 이름은 '미지정'으로 컴파일된다.
    input_types: 값 없는 입력의 타입 선언(저술 시점 검사용) — 실행 요청에는 쓰지 않는다."""
    from ibl_v2_adapters import Adapter
    registry = {k: Adapter(copy.deepcopy(v.contract), v.run, v.authorize, v.dependency,
                          getattr(v, "reusable", None), getattr(v, "stateful", None),
                          getattr(v, "resource_identity", None), getattr(v, "model_identity", None),
                          getattr(v, 'invocation_dependency', None), getattr(v, 'specialize', None))
                for k, v in (registry or {}).items()}
    inputs = copy.deepcopy(inputs or {})
    compiler = Compiler(source, registry, inputs, copy.deepcopy(definitions) if definitions is not None else {},
                        declared_inputs=declared_inputs, input_types=input_types)
    root = parse(source)
    result = compiler.sequence(root, compiler.inputs.copy(), {})
    for t in compiler.returns:
        result = join(result, t)
    # Unused definitions must also be well formed; validate to a fixed point for
    # nested forward definitions, without inventing caller-local parameters.
    while (set(compiler.functions) - compiler.checked or
           set(compiler.lambda_nodes) - compiler.lambda_checked):
        remaining = set(compiler.functions) - compiler.checked
        if remaining:
            sid = sorted(remaining)[0]
            reachable_effects, accesses_before = set(compiler.effects), set(compiler.access_log)
            compiler.function(sid, {})
            compiler.effects, compiler.access_log = reachable_effects, accesses_before
        else:
            lid = next(iter(set(compiler.lambda_nodes) - compiler.lambda_checked))
            node = compiler.lambda_nodes[lid]
            typ = compiler.lambda_contracts[lid]
            outer = compiler.effects, compiler.access_log, compiler.reachable
            compiler.effects, compiler.access_log, compiler.reachable = set(), set(), False
            compiler.apply_callable(node, typ, [UNKNOWN] * len(node.data['params']),
                                    [node] * len(node.data['params']))
            compiler.effects, compiler.access_log, compiler.reachable = outer
    dependencies = {"source": digest(compiler.source), "libraries": digest({k: (compiler.semantic_functions[compiler.external[k]] if compiler.external[k] in compiler.semantic_functions else compiler.definitions[k]) for k in sorted(compiler.external)}),
                    "calls": compiler.call_dependencies,
                    "input_types": {k: str(t) for k, t in compiler.inputs.items()},
                    "source_map": compiler.source_map, "contracts": digest({k: registry[k].contract for k in sorted(compiler.used_actions)}),
                    "edition": digest((Path(__file__).parents[1] / "base/ibl_edition.py").read_text()),
                    "semantics": digest((Path(__file__).parents[1] / "common/value_semantics.py").read_text()),
                    "expressions": digest({p.name: digest(p.read_text()) for p in sorted(set((Path(__file__).parents[1] / "common").glob("expression_*.py")) | {Path(__file__).parents[1] / "common/foreign_ref.py"})}),
                    "core": digest({p.name: digest(p.read_text()) for p in sorted(set(Path(__file__).parent.glob("ibl_v2_*.py")) |
                              {Path(__file__).parent / name for name in ("ibl_script_session.py", "ibl_file_script.py", "ibl_document_value.py", "ibl_member_library.py",
                                                                        "ibl_remote_call.py", "ibl_run_journal.py", "ibl_callable_contract.py", "ibl_dependencies.py")} |
                              {Path(__file__).parents[1] / 'base' / name for name in ('file_script.py', 'script_process.py', 'script_workspace.py')})})}
    refs = [getattr(compiler.definitions, 'references', {}).get(name) for name in sorted(compiler.external)]
    refs += [ref for key in sorted(compiler.used_actions)
             for ref in registry[key].contract.get('function_refs', [])]
    dependencies['function_refs'] = list({(r['function_id'], r['revision']): r for r in refs if r}.values())
    compiler.check_purity()
    from ibl_v2_requirements import finish
    finish(compiler)
    finish_diagnostics(compiler)
    for entry in compiler.warnings:
        old = entry['source_span']
        node = Node('diagnostic', old['start'], old['end'])
        entry['location'] = location(compiler.source, compiler.source_map, node)
    for sid, contract in compiler.function_contracts.items():
        contract['definition'] = location(compiler.source, compiler.source_map, compiler.functions[sid])
    from ibl_v2_preflight import analyze
    try:
        preflight = analyze(compiler, root, inputs)
    except Exception as exc:
        preflight = {'status': 'abstained', 'declared_ai_visits_upper_bound': None,
                     'unknowns': [{'reason': '분석 기반 오류', 'kind': type(exc).__name__}],
                     'warnings': []}
    if compiler.warnings:
        merged = compiler.warnings + [w for w in preflight.get('warnings', []) if w not in compiler.warnings]
        preflight['warnings'] = merged[:32]
        preflight['warnings_omitted'] = preflight.get('warnings_omitted', 0) + max(0, len(merged) - 32)
    preflight['analysis'] = compiler.analysis_stats
    preflight['actions'] = sorted(compiler.used_actions)  # 검사 단계의 문맥 사전경고가 읽는다(L33-3)
    plan = Plan(compiler.source, root, compiler.functions, registry, compiler.inputs,
                compiler.issues, compiler.guards, compiler.effects, result,
                digest(dependencies), dependencies, compiler.function_contracts, preflight,
                compiler.definitions, compiler.unspecified)

    plan.function_scopes = compiler.function_scopes
    plan.accesses = compiler.access_log
    plan.node_effects = compiler.node_effects
    from ibl_v2_component import compiled_contracts
    plan.components = compiled_contracts(compiler)
    if value_protocols is not None:
        from ibl_v2_requirements import require_wire
        plan = require_wire(plan, value_protocols)
    plan.semantic_functions = compiler.semantic_functions
    return plan
