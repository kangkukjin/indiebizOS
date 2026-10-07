"""Name resolution, structural preflight and immutable execution snapshots.

Unknown is an explicit runtime guard, not a successful proof. No warm cache is
used yet: every plan contains its source/definitions/contracts and dependency
fingerprint, avoiding the legacy transitive-cache invalidation problem.
"""
from dataclasses import dataclass, field
from pathlib import Path
import copy
from ibl_v2_ir import Fault, Node, UNIT, digest, span, parallel_branches, record_fields
from ibl_v2_parser import parse
from ibl_v2_narrow import narrow
from ibl_v2_expr import BUILTINS
import re
# f-문자열의 글자 부분에 남은 `$이름` — `$(`·`$5` 같은 다른 쓰임은 잡지 않는다.
_BARE_DOLLAR_NAME = re.compile(r"\$[A-Za-z_\uac00-\ud7a3][\w\uac00-\ud7a3]*")
from ibl_v2_analysis import (finish_diagnostics, numeric_operand, builtin_type,
                             assigned_names, location, access_type, HINTS)
from ibl_v2_types import (Type, UNKNOWN, UNIT_T, BOOL, NUMBER, TEXT, NULL, rows_type,
                          infer, join, declared, compatible, alternatives,
                          ordered_list, concat_lists, static_text)

RESERVED = {"it", "i", "error"}
PURE_KINDS = {"literal", "ref", "record", "list", "unary", "binary", "field",
              "index", "slice", "builtin", "pure_call", "lambda", "format", "conditional"}


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

    REPORT_GUARDS_CAP = 24

    def report(self):
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
                "result_type": str(self.result_type), "effects": sorted(self.effects), "functions": self.function_contracts,
                "plan_hash": self.fingerprint, "dependencies": dependencies,
                "source_hash": digest(self.source[:self.dependencies["source_map"][0]["end"]]),
                "capabilities": ["ibl-edition/2", "ibl-value/1"],
                **({"unspecified_inputs": sorted(self.unspecified)} if self.unspecified else {}),
                "preflight": self.preflight, "warnings": self.preflight.get("warnings", []),
                "note": "incomplete는 미확정 타입의 실행 시 검사를 포함합니다. 업무 품질·전건 완료의 보증이 아닙니다."}


class Compiler:
    def __init__(self, source, registry, inputs, definitions=None, declared_inputs=None, input_types=None):
        self.source, self.registry = source, registry
        self.definitions, self.external = definitions or {}, {}
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
        # 방문 중 만난 선언 쓰기 자원 — 병렬 가지·each 병렬 본문이 괄호로 묶어 충돌을 본다(70회차 B70-2).
        self.write_log = set()
        self.reachable = True
        self.default_scope = frozenset()  # 기본값 식을 검사하는 동안의 인자 이름들
        self.unit_warned = set()
        self.impure_spans = []
        self.pure_calls, self.call_effects = [], {}

    def issue(self, node, code, message, **details):
        item = {"code": code, "message": message, "source_span": span(self.source, node),
                "call_path": copy.deepcopy(self.call_path), **details}
        if item not in self.issues:
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
        if node.kind == "call" and node.data.get("node") == "fn" and node.data.get("body") is None:
            # 순수 자리의 기준은 호출 문법이 아니라 효과다. 효과 없는 함수는 식과 같다 — 효과는 방문 뒤에 확인한다.
            if all(node is not seen for seen in self.pure_calls):
                self.pure_calls.append(node)
            self.check_children(node.data.get("params"), self.pure)
            return
        if node.kind not in PURE_KINDS:
            self.impure_spans.append((node.start, node.end))
            hint = HINTS["PURE_EXPRESSION"]
            message = "이 자리에는 순수 식만 쓸 수 있습니다. 호출·조합은 앞 문장에 두세요."
            if node.kind in ("if", "case"):
                message = "이 자리에는 순수 식만 쓸 수 있습니다. 제어 블록 대신 조건 값을 쓰세요."
                hint = "값을 고르는 분기는 `조건 ? 값1 : 값2`입니다. 예: ($a,$r)=>$r.n > $a ? $r.n : $a"
            elif node.kind == "pipe":
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
        자리(조건·조건 값·and/or·람다 본문·기본값)는 각자의 방문에서 pure()가 재귀로 지키므로,
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
        names = self.predeclare(node, names)
        result = UNIT_T
        terminated = False
        dead_env = None
        for statement in node.data["statements"]:
            if terminated:
                # Still diagnose invalid dead source, but it cannot supply a
                # frame result or add return types to the reachable paths.
                old_returns, self.returns = self.returns, []
                self.visit_unreachable(statement, dead_env, names, readonly, final)
                self.returns = old_returns
            else:
                result = self.visit(statement, env, names, readonly, final)
                if self.returns_unconditionally(statement):
                    terminated, dead_env = True, env.copy()
        return result

    def visit_unreachable(self, node, env, names, readonly=frozenset(), final=False):
        """Still type-check dead source, but do not invent executable writes."""
        previous, self.reachable = self.reachable, False
        try:
            return self.visit(node, env, names, readonly, final)
        finally:
            self.reachable = previous

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
            env[name] = args.get(name, dtype)
        parameter_types = {k: str(v) for k, v in env.items()}
        result = self.sequence(node.data["body"], env, self.function_scopes[sid])
        for t in self.returns:
            result = t if result == UNIT_T else join(result, t)
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
        observed = {'params': parameter_types, 'result': str(result)}
        summary = self.function_contracts.setdefault(sid, {
            'name': node.data['name'], 'params': parameter_types.copy(),
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
            if type(d["value"]) is str:
                import re
                if re.search(r"\$[\w]+\.[\w]", d["value"]):
                    self.warn(node, "LITERAL_DOLLAR", "이 문자열의 $변수.필드는 판본 2에서 문자 그대로입니다. 값 참조나 f 문자열의 ${표현식}을 사용하세요.")
                return Type("Text", literal=d["value"])
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
            return UNIT_T
        if kind == "assert":
            for key in ("condition", "message", "details"):
                self.pure(d[key])
            self.need(node, sub(d["condition"]), BOOL)
            if d["message"] is not None:
                self.need(node, sub(d["message"]), TEXT)
            if d["details"] is not None:
                self.need(node, sub(d["details"]), Type("Record"))
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
            if "entries" not in d:
                # 미지정 입력에 매인 필드는 레코드(=호출 인자)에서 빠진다 — 핸들러의 기본값이 산다.
                return Type("Record", tuple((k, sub(v)) for k, v in d["fields"].items()
                                            if not self.omitted(v, env)), open=False)
            fields, opened = {}, False
            for key, value in d["entries"]:
                if key is not None and self.omitted(value, env):
                    continue
                typ = sub(value)
                if key is None:
                    self.need(value, typ, Type("Record"))
                    if typ.kind == "Record":
                        if typ.open:
                            fields = {k: UNKNOWN for k in fields}
                        fields.update(dict(typ.fields))
                        opened |= typ.open
                    else:
                        fields = {k: UNKNOWN for k in fields}
                        opened = True
                else:
                    fields[key] = typ
            return Type("Record", tuple(fields.items()), open=opened)
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
                key = key.data["value"] if key.kind == "literal" else None
            return access_type(self, node, base, key, key_type)
        if kind in ("binary", "unary"):
            op = d["op"]
            if kind == "binary" and op in ("and", "&&", "or", "||"):
                self.pure(node)  # 오른쪽은 평가되지 않을 수 있다 — 효과의 실행 여부를 식에 숨기지 않는다.
            else:
                self.container_value(node)
            right_env = (narrow(env, d["left"], op in ("and", "&&"))
                         if kind == "binary" and op in ("and", "&&", "or", "||") else env)
            values = ([sub(d["value"])] if kind == "unary"
                      else [sub(d["left"]), sub(d["right"], right_env)])
            never = next((t for t in values if t.kind == "Never"), None)
            if never is not None:
                # 도달할 수 없는 값이 낀 연산은 통째로 도달 불가다. 남은 피연산자를 숫자로 검사하면
                # 이어 붙이기의 문자열 리터럴이 거짓 NUMBER_REQUIRED 가 된다(긴문장 10회차 L10-3).
                return never
            if op in ("and", "or", "&&", "||", "!", "not"):
                for t in values:
                    self.need(node, t, BOOL)
                return BOOL
            if op in ("==", "!=", "<", ">", "<=", ">=", "in"):
                return BOOL
            if op == "+" and len(values) == 2 and values[0].kind == values[1].kind and values[0].kind in ("List", "Text"):
                if values[0].kind == "List":
                    return concat_lists(*values)
                texts = [static_text(t) for t in values]
                if all(t is not None for t in texts):
                    from common.value_semantics import normalized_text
                    return Type("Text", literal=normalized_text("".join(texts)))
                return TEXT
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
        if kind == "conditional":
            # `조건 ? 값1 : 값2` — 조건은 Bool 만(참거짓 흉내 없음), 고르지 않은 가지는 실행하지 않는다.
            # 결과 타입은 두 가지의 합이다(73회차 G73-1 언어 개정).
            self.pure(node)
            self.need(d["condition"], sub(d["condition"]), BOOL)
            return join(sub(d["yes"], narrow(env, d["condition"])),
                        sub(d["no"], narrow(env, d["condition"], False)))
        if kind == "builtin":
            if d["name"] not in BUILTINS:
                from common.expression_ops import unknown_builtin_message
                self.issue(node, "BUILTIN", unknown_builtin_message(d["name"]))
            return Type("Callable")
        if kind == "pure_call":
            self.container_value(node)
            fn = d["fn"]
            self.need(fn, sub(fn), Type("Callable"))
            types = [sub(a) for a in d["args"]]
            if fn.kind == "builtin" and fn.data["name"] in BUILTINS:
                name = fn.data["name"]
                low, high = BUILTINS[name]
                if not low <= len(types) <= high:
                    wanted = f"{low}개" if low == high else f"{low}~{high}개"
                    self.issue(node, "ARITY", f"{name}은 인자 {wanted}를 받습니다(받은 인자 {len(types)}개).")
                return builtin_type(self, node, name, types, env, names, readonly)
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
            known = []
            for part in d["parts"]:
                if isinstance(part, Node) and self.omitted(part, env):
                    known.append("")   # 미지정 입력의 보간은 빈 문자열(구형 표면 치환과 같은 뜻)
                    continue
                if isinstance(part, Node):
                    self.container_value(part)
                    t = sub(part)
                    if not compatible(t, join(join(TEXT, NUMBER), BOOL)):
                        self.issue(part, "FORMAT_TYPE", f"보간에는 Text·Number·Bool이 필요하지만 {t}입니다.",
                                   expected=str(join(join(TEXT, NUMBER), BOOL)), actual=str(t))
                    elif t.kind == "Unknown":
                        self.need(part, t, join(join(TEXT, NUMBER), BOOL))
                    known.append(static_text(t))
                else:
                    known.append(part if isinstance(part, str) else None)
                    if isinstance(part, str) and _BARE_DOLLAR_NAME.search(part):
                        # ep4214: f"…{json($html)}…" 가 문자 그대로 나갔다 — 보간은 ${식} 뿐이다.
                        self.warn(node, "FORMAT_UNINTERPOLATED",
                                  "f-문자열 안의 $이름 이 ${…} 밖에 있어 보간되지 않고 문자 그대로 남습니다.",
                                  text=_BARE_DOLLAR_NAME.search(part)[0])
            if known and all(isinstance(k, str) for k in known):
                return Type("Text", literal="".join(known))
            return TEXT
        if kind == "pipe":
            left = sub(d["left"])
            if d["right"].kind != "call":
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
            return self.visit(d["right"], env, names, readonly, final, piped=left)
        if kind == "parallel":
            types = []
            writes, conflict = set(), set()
            for branch in parallel_branches(node):
                old_returns, self.returns = self.returns, []
                outer_writes, self.write_log = self.write_log, set()
                result = sub(branch, env.copy())
                for t in self.returns:
                    result = t if result == UNIT_T else join(result, t)
                self.returns = old_returns
                types.append(result)
                branch_writes, self.write_log = self.write_log, outer_writes | self.write_log
                conflict.update(writes & branch_writes)
                writes.update(branch_writes)
            if conflict:
                self.issue(node, "PARALLEL_WRITE_CONFLICT", f"병렬 가지가 같은 선언 자원에 씁니다: {sorted(conflict)}")
            return ordered_list(types)
        if kind == "fallback":
            return join(sub(d["left"], env.copy()), sub(d["right"], env.copy()))
        if kind == "call":
            arg_type = sub(d["params"])
            args = dict(arg_type.fields)
            d["open_arguments"] = arg_type.open
            if arg_type.open:
                self.need(d["params"], UNKNOWN, Type("Record"))
            key = f"{d['node']}:{d['action']}"
            if d.get("target") and (d["node"] == "fn" or key == "table:each"):
                self.issue(node, "TARGET_NODE", f"노드 지정 @{d['target']} 은 도구 호출에만 붙습니다 — 함수·each 블록에는 쓸 수 없습니다.")
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
            values = {k: constant_value(v) for k, v in fields.items()}
            for arg in args:
                values.setdefault(arg, UNRESOLVED)
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
                self.call_dependencies[node.id] = snapshot
            contract = selected(spec.contract, values)
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
            for k, t in args.items():
                if k in params:
                    self.need(node, t, declared(params[k]))
            self.effects.update(contract["effects"])
            self.call_effects.setdefault(node.id, set()).update(contract["effects"])
            # 자원 정체 = 타입 검사가 아는 컴파일 시 값(리터럴·변수·기본값·특수화 인자·정적 보간). 같은 값이면 같은 자원이다.
            for realm, param in spec.contract.get("write_resources", {}).items():
                known = static_text(args.get(param))
                if known is not None and self.reachable:
                    identity = spec.resource_identity(realm, known) if spec.resource_identity else known
                    self.write_log.add((realm, identity))
            result_type = declared(contract["result"])
            from ibl_v2_adapters import observed_result
            # A dynamic shape selector is present, not absent. Keep its marker
            # so observations from the default shape cannot leak into it.
            result_type = observed_result(key, spec.contract, values, result_type)
            from ibl_v2_analysis import row_flow_type
            result_type = row_flow_type(self, node, contract, args, fields, values,
                                        result_type, env, names, readonly)
            if (result_type.kind == "Record" and "items" not in dict(result_type.fields)
                    and contract.get("analysis", {}).get("flow", {}).get("emits") == "items"
                    and "items" in contract.get("adapter", {}).get("input_envelopes", [])):
                # 행 봉투를 받아 행 봉투를 내는 변환자(선언: input_envelopes + flow.emits)의 결과는 items 행 목록을
                # 가진다 — 행 목록 자리가 그대로 받는다. 문서·건수처럼 행이 아닌 Record 는 해당하지 않는다.
                result_type = Type("Record", (*result_type.fields, ("items", Type("List", item=UNKNOWN))),
                                   open=result_type.open, observed=result_type.observed)
            if result_type.kind == "Unknown":
                self.need(node, UNKNOWN, UNKNOWN)
            return result_type
        if kind == "if":
            self.pure(d["value"])
            self.need(node, sub(d["value"]), BOOL)
            a, b = narrow(env, d["value"]), narrow(env, d["value"], False)
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
            if count == 0:
                self.visit_unreachable(d["body"], local, names, readonly, final)
            else:
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
        items = rows_type(args.get("items", UNKNOWN))
        self.need(node, items, Type("List", item=UNKNOWN))
        fields = record_fields(node.data["params"])
        options = {}
        for key, default in (("mode", "map"), ("on_error", "stop"), ("parallel", 1)):
            value = fields.get(key)
            if value is None and (key in args or node.data.get("open_arguments")):
                self.issue(node, "STATIC_OPTION", f"펼친 each의 {key}는 뒤에 리터럴로 명시하세요.")
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
        outer_writes, self.write_log = self.write_log, set()
        local = {**env, "it": items.item or UNKNOWN, "i": NUMBER}
        visit = self.visit_unreachable if items.positions == () else self.visit
        result = visit(node.data["body"], local, names, frozenset(env) | RESERVED)
        for t in self.returns:
            result = t if result == UNIT_T else join(result, t)
        self.returns = old_returns
        body_writes, self.write_log = self.write_log, outer_writes | self.write_log
        single = items.positions is not None and len(items.positions) <= 1
        if type(options["parallel"]) is int and options["parallel"] > 1 and body_writes and not single:
            # 반복마다 같은 자원 — 병렬 반복들이 서로 덮어쓴다. 원소에 따라 정해지는 자원은 여기 오지 않는다.
            self.issue(node, "PARALLEL_WRITE_CONFLICT",
                       f"each 병렬 반복이 모두 같은 선언 자원에 씁니다: {sorted(body_writes)}")
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


def compile_program(source, registry=None, inputs=None, definitions=None, *, declared_inputs=None, input_types=None):
    """declared_inputs: 표면이 템플릿에서 참조하는 입력 이름 전부. inputs 에 없는 이름은 '미지정'으로 컴파일된다.
    input_types: 값 없는 입력의 타입 선언(저술 시점 검사용) — 실행 요청에는 쓰지 않는다."""
    from ibl_v2_adapters import Adapter
    registry = {k: Adapter(copy.deepcopy(v.contract), v.run, v.authorize, v.dependency,
                          getattr(v, "reusable", None), getattr(v, "stateful", None),
                          getattr(v, "resource_identity", None), getattr(v, "model_identity", None),
                          getattr(v, 'invocation_dependency', None))
                for k, v in (registry or {}).items()}
    inputs = copy.deepcopy(inputs or {})
    compiler = Compiler(source, registry, inputs, copy.deepcopy(definitions or {}),
                        declared_inputs=declared_inputs, input_types=input_types)
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
                    "expressions": digest({p.name: digest(p.read_text()) for p in sorted(set((Path(__file__).parents[1] / "common").glob("expression_*.py")) | {Path(__file__).parents[1] / "common/foreign_ref.py"})}),
                    "core": digest({p.name: digest(p.read_text()) for p in sorted(set(Path(__file__).parent.glob("ibl_v2_*.py")) |
                              {Path(__file__).parent / name for name in ("ibl_script_session.py", "ibl_file_script.py", "ibl_document_value.py", "ibl_member_library.py",
                                                                        "ibl_remote_call.py", "ibl_run_journal.py", "ibl_callable_contract.py", "ibl_dependencies.py")} |
                              {Path(__file__).parents[1] / 'base' / name for name in ('file_script.py', 'script_process.py', 'script_workspace.py')})})}
    for call in compiler.pure_calls:
        effects = compiler.call_effects.get(call.id)
        if effects is not None and effects - {"pure"}:
            compiler.issue(call, "PURE_EXPRESSION",
                           f"이 자리의 [fn:{call.data['action']}] 호출은 효과가 없어야 합니다(이 함수의 효과: "
                           f"{', '.join(sorted(effects - {'pure'}))}). 조건·조건 값·and/or·람다 본문·기본값은 실행 여부나 횟수가 갈리는 자리입니다.",
                           hint="효과가 있는 호출은 앞 문장에서 $이름=[fn:…]{…}으로 받거나, 행마다 필요하면 table:each 본문에서 호출하세요.")
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
    return Plan(compiler.source, root, compiler.functions, registry, compiler.inputs,
                compiler.issues, compiler.guards, compiler.effects, result,
                digest(dependencies), dependencies, compiler.function_contracts, preflight,
                compiler.definitions, compiler.unspecified)
