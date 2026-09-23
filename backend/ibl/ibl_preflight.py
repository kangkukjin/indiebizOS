"""실행 없는 IBL 계획 분석. 값 대신 건수·정수·반복 의존성만 전달한다.

내용어 이름은 알지 않는다. 모델 단계는 사전의 ai_call, 문장은 공통 IR로 읽는다.
파일/도구/모델을 실행하지 않으며 경고는 차단 근거가 아니다. 비용은 선언된 AI
어휘의 방문 상한일 뿐 내부 모델 호출 수·토큰·완료 시간을 예측하지 않는다.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace
from typing import Optional

from common.ibl_vars import REF_RE, split_ref
from common.field_path import parse_path
from ibl_code_ir import Literal, Ref, STEP_RE, Template, compile_code
from ibl_parser import IBLSyntaxError, parse_function_body


@dataclass(frozen=True)
class Fact:
    rows: Optional[int] = None
    integer: Optional[int] = None
    fields: dict = field(default_factory=dict)
    element: Optional['Fact'] = None
    dependencies: frozenset = frozenset()

    def dependent(self, names):
        return replace(self, dependencies=self.dependencies | frozenset(names))


UNKNOWN = Fact(dependencies=frozenset({'unknown'}))
ABSENT = Fact()  # 파이프 입력 없음과 값 미상을 구별한다(identity 비교).
MAX_STEPS = 2000
MAX_DEPTH = 8
MAX_FINDINGS = 32


def _product(a, b):
    if a == 0 or b == 0:
        return 0
    return None if a is None or b is None else a * b


def _merge(facts):
    if not facts:
        return UNKNOWN
    keys = set(facts[0].fields).intersection(*(set(f.fields) for f in facts[1:]))
    return Fact(
        rows=facts[0].rows if all(f.rows == facts[0].rows for f in facts) else None,
        integer=facts[0].integer if all(f.integer == facts[0].integer for f in facts) else None,
        fields={k: _merge([f.fields[k] for f in facts]) for k in keys},
        dependencies=frozenset().union(*(f.dependencies for f in facts)),
    )


def _path(fact, path):
    for part in parse_path(path.rstrip('?')):
        if part == 'items' and fact.rows is not None:
            continue
        if part == 'count' and fact.rows is not None:
            fact = Fact(integer=fact.rows, dependencies=fact.dependencies)
        else:
            fact = fact.fields.get(part, UNKNOWN).dependent(fact.dependencies)
    return fact


class _Plan:
    def __init__(self, action_def, function_code):
        self.action_def = action_def
        self.function_code = function_code
        self.definitions = {}
        self.captures = {}
        self.issues = []
        self.sites = []
        self.unknowns = []
        self.unbounded = False
        self.steps_seen = 0
        self.origin = (1, 1)

    def unknown(self, path, reason):
        if reason != 'dynamic_each_input':
            self.unbounded = True
        entry = {'path': path, 'reason': reason}
        if entry not in self.unknowns and len(self.unknowns) < MAX_FINDINGS:
            self.unknowns.append(entry)

    def issue(self, rule, path, message, hint, **facts):
        if len(self.issues) >= MAX_FINDINGS:
            return
        self.issues.append({
            'severity': 'warning', 'rule': rule, 'statement': self.origin[0],
            'step': self.origin[1], 'at': path, 'message': message, 'hint': hint,
            'facts': facts,
        })

    def resolve(self, ref, names, slots):
        if ref.namespace == 'name':
            value = names.get(ref.name, UNKNOWN)
        elif ref.namespace == 'step':
            value = slots.get(int(ref.name), UNKNOWN)
        else:
            value = self.captures.get(ref.namespace, {}).get(ref.name, UNKNOWN)
        return _path(value, ref.path)

    def value(self, value, names, slots, depth=0):
        if depth > MAX_DEPTH:
            return UNKNOWN
        if isinstance(value, Fact):
            return value
        if type(value) is int:
            return Fact(integer=value)
        if isinstance(value, list):
            children = [self.value(v, names, slots, depth + 1) for v in value[:200]]
            deps = frozenset().union(*(f.dependencies for f in children))
            if len(value) > 200:
                return Fact(rows=len(value), dependencies=frozenset({'unknown'}))
            return Fact(rows=len(value), element=_merge(children), dependencies=deps)
        if isinstance(value, dict):
            if len(value) > 200:
                return UNKNOWN
            fields = {k: self.value(v, names, slots, depth + 1) for k, v in value.items()}
            return Fact(fields=fields, dependencies=frozenset().union(*(f.dependencies for f in fields.values())))
        if isinstance(value, Literal):
            return Fact()
        if isinstance(value, Template):
            if len(value.parts) == 1 and isinstance(value.parts[0], Ref):
                return self.resolve(value.parts[0], names, slots)
            return Fact().dependent(frozenset().union(*(
                self.resolve(p, names, slots).dependencies for p in value.parts if isinstance(p, Ref))))
        if isinstance(value, str):
            m = STEP_RE.fullmatch(value)
            if m:
                return _path(slots.get(int(m[1]), UNKNOWN), m[2])
            m = REF_RE.fullmatch(value)
            if m:
                name, path = split_ref(m)
                return _path(names.get(name, UNKNOWN), path)
            if REF_RE.search(value) or STEP_RE.search(value):
                return UNKNOWN  # 보간 문자열을 불변 입력으로 단정하지 않는다.
        return Fact()

    def expression(self, text, names, slots, refs=None):
        """구성식의 크기만 읽는다. eval·함수 호출·산술의 사설 해석은 하지 않는다."""
        refs = refs or {}
        bindings = {}

        def reference(match):
            name, path = split_ref(match)
            fact = (self.resolve(refs[name], names, slots) if name in refs
                    else names.get(name, UNKNOWN))
            symbol = '_preflight_ref_' + str(len(bindings))
            bindings[symbol] = _path(fact, path)
            return symbol

        try:
            tree = ast.parse(REF_RE.sub(reference, str(text)), mode='eval').body
        except (SyntaxError, ValueError, RecursionError):
            return UNKNOWN

        def walk(node, depth=0):
            if depth > MAX_DEPTH:
                return UNKNOWN
            if isinstance(node, ast.Name):
                return bindings.get(node.id, UNKNOWN)
            if isinstance(node, ast.Constant):
                if isinstance(node.value, str) and any(s in node.value for s in bindings):
                    return Fact().dependent(frozenset().union(*(
                        f.dependencies for s, f in bindings.items() if s in node.value)))
                return self.value(node.value, {}, {})
            if isinstance(node, ast.List):
                if len(node.elts) > 200:
                    return Fact(rows=len(node.elts), dependencies=frozenset({'unknown'}))
                children = [walk(v, depth + 1) for v in node.elts]
                return Fact(rows=len(children), element=_merge(children),
                            dependencies=frozenset().union(*(f.dependencies for f in children)))
            if isinstance(node, ast.Dict):
                if len(node.keys) > 200:
                    return UNKNOWN
                fields = {}
                for k, v in zip(node.keys, node.values):
                    key = k.id if isinstance(k, ast.Name) else k.value if isinstance(k, ast.Constant) else None
                    if not isinstance(key, str):
                        return UNKNOWN
                    fields[key] = walk(v, depth + 1)
                return Fact(fields=fields, dependencies=frozenset().union(*(f.dependencies for f in fields.values())))
            return UNKNOWN.dependent({'unknown'})

        return walk(tree)

    def body(self, body, names, slots, incoming, multiplier, loops, path, depth):
        if isinstance(body, str):
            if REF_RE.fullmatch(body.strip()):
                self.unknown(path, 'dynamic_body')
                return UNKNOWN
            try:
                code = compile_code(body)
            except (IBLSyntaxError, SyntaxError, ValueError):
                self.unknown(path, 'unparsed_body')
                return UNKNOWN
            self.captures['capture:' + code.scope] = dict(slots)
            steps = code.tree
        elif isinstance(body, dict):
            steps = body.get('_branch_steps') or [body]
        else:
            steps = body or []
        definitions = dict(self.definitions)
        try:
            return self.run(steps, dict(names), incoming, multiplier, loops, path, depth + 1)
        finally:
            self.definitions = definitions

    def run(self, steps, names=None, incoming=ABSENT, multiplier=1, loops=(), path='program', depth=0):
        if multiplier == 0:
            return UNKNOWN
        if depth > MAX_DEPTH:
            self.unknown(path, 'analysis_depth_limit')
            return UNKNOWN
        names = dict(names or {})
        slots, name_slots, previous, returned = {}, {}, incoming, None
        for st in steps:
            if isinstance(st, dict) and st.get('_def'):
                self.definitions[st['name']] = st
        statement = 1
        for i, st in enumerate(steps):
            if not isinstance(st, dict):
                continue
            self.steps_seen += 1
            if self.steps_seen > MAX_STEPS:
                self.unknown(path, 'analysis_step_limit')
                return UNKNOWN
            if st.get('_seq_boundary'):
                previous = ABSENT
                if i and not steps[i - 1].get('_def'):
                    statement += 1
            if depth == 0:
                self.origin = (statement, i + 1)
            location = f'{path}/{i + 1}'
            if st.get('_def'):
                continue  # 사용하지 않은 함수는 비용·경고에 합산하지 않는다.
            result = self.step(st, names, slots, previous, multiplier, loops, location, depth)
            slots[i] = result
            if st.get('_assign_name'):
                names[st['_assign_name']] = result
                name_slots[st['_assign_name']] = i
                if st['_assign_name'] == 'return':
                    returned = result
            # 분기/반복에서 쓰인 변수의 옛 값으로 이후 건수를 단정하지 않는다.
            from ibl_honesty import assigned_in_body
            written = assigned_in_body({k: v for k, v in st.items() if k != '_assign_name'})
            if st.get('_assign'):
                written = []
            for name in written:
                names[name] = UNKNOWN
                if name == 'return':
                    returned = UNKNOWN
                slot = name_slots.get(name, (st.get('_vars') or {}).get(name))
                if slot is not None:
                    slots[slot] = UNKNOWN
            previous = result
        return returned if returned is not None else previous

    def step(self, st, names, slots, previous, multiplier, loops, path, depth):
        if st.get('_assign'):
            return self.expression(st.get('expr', ''), names, slots, st.get('_ir_expr_refs'))
        if st.get('_var_emit'):
            name = st.get('name')
            refs = st.get('_ir_expr_refs') or {}
            fact = self.resolve(refs[name], names, slots) if name in refs else names.get(name, UNKNOWN)
            return _path(fact, st.get('path') or '')
        if st.get('_repeat'):
            count = self.value(st.get('count'), names, slots).integer
            cap = self.value(st.get('max'), names, slots).integer
            bound = min(count, cap) if count is not None and cap is not None else cap if cap is not None else count
            bound = max(0, bound) if bound is not None else None
            reset = {**names, **{k: UNKNOWN for k in (st.get('body_vars') or {})}}
            reset[st.get('var') or 'i'] = UNKNOWN.dependent({path})
            self.body(st.get('body'), reset, slots, previous, _product(multiplier, bound),
                      (*loops, (path, bound)), path + '/repeat', depth)
            return UNKNOWN
        if st.get('_goal'):
            self.unknown(path, 'dynamic_goal')
            return UNKNOWN
        branches = None
        if st.get('_parallel'):
            branches = st.get('branches', [])
        elif st.get('_condition') or st.get('_case'):
            branches = [b.get('action', b) if isinstance(b, dict) else b for b in st.get('branches', [])]
            if st.get('default') is not None:
                branches.append(st['default'])
        elif '_fallback_chain' in st:
            branches = st['_fallback_chain']
        elif st.get('_try'):
            branches = [st[k] for k in ('body', 'catch', 'finally') if st.get(k) is not None]
        elif st.get('_branch_steps'):
            return self.body(st['_branch_steps'], names, slots, previous, multiplier, loops, path, depth)
        if branches is not None:
            from ibl_honesty import assigned_in_body
            written = assigned_in_body(st)
            branch_names = {**names, **{name: UNKNOWN for name in written}}
            # try/finally·공유 변수 분기에서는 앞 가지의 쓰기가 뒤 가지에 보일 수 있다.
            # 슬롯 참조까지 이전 값으로 단정하지 않는다. 가지 안의 새 할당은 다시 추론한다.
            branch_slots = {k: UNKNOWN for k in slots} if written else slots
            for j, branch in enumerate(branches):
                self.body(branch, branch_names, branch_slots, previous, multiplier, loops,
                          f'{path}/branch{j + 1}', depth)
            # 배타적인 분기도 합산한 보수적 상한. 가지의 결과·변수 갱신은 확정하지 않는다.
            return UNKNOWN
        node, action = st.get('_node') or st.get('node'), st.get('action')
        params = st.get('params') or {}
        if node == 'fn':
            definition = self.definitions.get(action)
            if definition is None:
                code = self.function_code(action)
                if code:
                    try:
                        definition = {'body': parse_function_body(code)}
                    except (IBLSyntaxError, SyntaxError, ValueError):
                        self.unknown(path, 'unparsed_function')
                        return UNKNOWN
            if not definition or not definition.get('body'):
                self.unknown(path, 'unresolved_function')
                return UNKNOWN
            args = {k: self.value(v, names, slots) for k, v in params.items() if not k.startswith('_')}
            from workflow_contract import pipe_input_param
            pipe_param = pipe_input_param(definition['body'])
            if pipe_param and pipe_param not in args:
                args[pipe_param] = previous
            return self.body(definition['body'], args, {}, previous, multiplier, loops, path + '/fn:' + action, depth)
        if not node or not action:
            self.unknown(path, 'unsupported_step')
            return UNKNOWN
        if node == 'table' and action == 'each':
            # 실행기를 import하지 않고 공유 계약을 읽는다(교차층 순환 방지).
            from workflow_contract import EACH_DEFAULT_LIMIT
            inp = self.input(params, names, slots, previous)
            if inp.rows is None:
                self.unknown(path, 'dynamic_each_input')
            limit = self.value(params['limit'], names, slots).integer if params.get('limit') is not None else EACH_DEFAULT_LIMIT
            if limit is not None and limit < 0:
                limit = EACH_DEFAULT_LIMIT
            bound = min(inp.rows, limit) if inp.rows is not None and limit is not None else limit
            if multiplier != 0 and inp.rows is not None and limit is not None and inp.rows > limit:
                self.issue('each_input_limit', path,
                           f'입력 {inp.rows}행 중 each limit={limit} 뒤의 {inp.rows - limit}행은 처리 대상에서 제외됩니다.',
                           '전건 처리가 목적이면 입력 건수에 맞게 limit을 지정하세요. 의도한 일부 처리면 이 경고를 무시할 수 있습니다.',
                           input_rows=inp.rows, limit=limit, omitted_rows=inp.rows - limit)
            if bound is None:
                self.unknown(path, 'dynamic_each_bound')
            child = dict(names)
            child[str(params.get('as') or 'it').lstrip('$')] = (inp.element or UNKNOWN).dependent({path})
            self.body(params.get('do'), child, slots, ABSENT, _product(multiplier, bound),
                      (*loops, (path, bound)), path + '/each', depth)
            return UNKNOWN
        definition = self.action_def(node, action) or {}
        if not definition:
            self.unknown(path, 'unresolved_action')
        inspection = definition.get('ai_inspect_param')
        inspect_only = inspection and params.get(inspection) in ('batch', 'each')
        if inspect_only:
            return self.input(params, names, slots, previous)
        if definition.get('ai_call') is True:
            self.sites.append({'path': path, 'action': f'{node}:{action}', 'visits_upper_bound': multiplier})
            inp = self.input(params, names, slots, previous)
            flow = definition.get('flow') or {}
            if flow.get('accepts') == 'items' and inp.rows is not None and inp.rows > 1:
                repeated = [(loop, n) for loop, n in loops if n is not None and n > 1 and loop not in inp.dependencies]
                if repeated and not inp.dependencies and multiplier != 0:
                    loop, n = repeated[-1]
                    self.issue('repeated_ai_batch', path,
                               f'반복 본문이 바뀌지 않는 {inp.rows}행 전체를 AI 어휘에 회차마다 전달합니다(반복 상한 {n}).',
                               '행별 처리가 목적이면 현재 행을 전달하세요. 공통 자료가 필요한 판단이면 반복 입력 비용을 확인하세요. 자동으로 입력을 줄이지 않습니다.',
                               input_rows=inp.rows, loop_upper_bound=n, row_transmissions_upper_bound=inp.rows * n,
                               loop=loop)
        # 임의 액션의 출력 건수를 열 보존 선언으로 추측하지 않는다.
        return UNKNOWN

    def input(self, params, names, slots, previous):
        # 통화 소비자의 파이프 입력 우선 규약. 값 미상을 입력 없음으로 바꾸지 않는다.
        if previous is ABSENT:
            raw = params.get('items')  # items-ok: 실행 값이 아닌 IR의 건수만 추론. 문자열 통화는 미상으로 남긴다.
            fact = self.value(raw, names, slots)
        else:
            fact = previous
        return fact.fields['items'].dependent(fact.dependencies) if 'items' in fact.fields else fact


def analyze(steps, action_def, function_code):
    """알려진 계획만 반환한다. 분석 실패로 기존 타입 진단·실행 여부를 바꾸지 않는다."""
    plan = _Plan(action_def, function_code)
    try:
        plan.run(steps or [])
        sites = plan.sites
        upper = None if plan.unbounded or any(s['visits_upper_bound'] is None for s in sites) else sum(
            s['visits_upper_bound'] for s in sites)
        return {'status': 'partial' if plan.unknowns else 'analyzed', 'issues': plan.issues,
                'declared_ai_visits_upper_bound': upper, 'ai_sites': sites[:MAX_FINDINGS],
                'ai_sites_omitted': max(0, len(sites) - MAX_FINDINGS), 'unknowns': plan.unknowns,
                'note': '코드를 실행하지 않은 구조 상한입니다. 분기 합산으로 과대 추정될 수 있습니다. '
                        '스크립트·도구 내부 모델 호출, 조건 판단, 재시도·토큰·시간은 포함하지 않습니다. '
                        '출력 데이터 크기는 추측하지 않습니다. 의미 품질과 실행 성공을 보증하지 않습니다.'}
    except Exception as exc:
        return {'status': 'abstained', 'issues': [], 'declared_ai_visits_upper_bound': None,
                'ai_sites': [], 'unknowns': [{'reason': type(exc).__name__}],
                'note': '계획 분석을 완료하지 못했습니다. 실행 안전을 확인했다는 뜻이 아닙니다.'}
