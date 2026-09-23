"""Bounded plan observations over the current AST, with no tool execution.

Only declared model calls and statically known list cardinalities are observed.
Unknown cardinalities/definitions are explicitly reported, never counted as zero.
"""
from dataclasses import dataclass

from ibl_v2_ir import Node
from ibl_v2_analysis import location


@dataclass(frozen=True)
class Facts:
    count: object = None
    dependencies: frozenset = frozenset()


def analyze(compiler, root, inputs):
    warnings, unknowns = [], []
    visits, steps = 0, 0
    active = set()

    def where(node):
        return location(compiler.source, compiler.source_map, node)

    def unknown(node, reason):
        entry = {'location': where(node), 'reason': reason}
        if entry not in unknowns and len(unknowns) < 32:
            unknowns.append(entry)

    def walk(node, env, loops=(), multiplier=1, depth=0):
        nonlocal visits, steps
        if node is None:
            return Facts()
        steps += 1
        if steps > 2000 or depth > 8:
            unknown(node, '분석 예산 초과')
            return Facts()
        d, kind = node.data, node.kind
        sub = lambda n, e=env: walk(n, e, loops, multiplier, depth)
        if kind == 'literal':
            return Facts()
        if kind == 'ref':
            return env.get(d['name'], Facts())
        if kind == 'list':
            deps = frozenset().union(*(sub(v).dependencies for v in d['values']))
            return Facts(len(d['values']), deps)
        if kind == 'bind':
            env[d['name']] = sub(d['value'])
            return Facts()
        if kind == 'return':
            return sub(d['value'])
        if kind in ('def', 'lambda'):
            return Facts()
        if kind == 'sequence':
            result = Facts()
            for statement in d['statements']:
                result = sub(statement)
                if compiler.returns_unconditionally(statement):
                    break
            return result
        if kind == 'pipe':
            return call(d['right'], env, loops, multiplier, depth, sub(d['left']))
        if kind == 'call':
            return call(node, env, loops, multiplier, depth)
        if kind == 'repeat':
            count = d['value'].data.get('value') if d['mode'] == 'count' and d['value'].kind == 'literal' else None
            count = count if type(count) is int and count >= 0 else None
            if count is None:
                unknown(node, '동적 반복 횟수')
            local = env.copy()
            local['i'] = Facts(dependencies=frozenset({node.id}))
            walk(d['body'], local, (*loops, (node.id, count)),
                 multiplier * count if multiplier is not None and count is not None else None, depth)
            # Repeated mutation is not a proof of an exact post-loop cardinality.
            from ibl_v2_analysis import assigned_names
            for name in assigned_names(d['body']) & env.keys():
                env[name] = Facts()
            return Facts()
        if kind in ('if', 'case', 'try', 'fallback', 'parallel'):
            # Visit all branches for a conservative bound, but do not assert an
            # exact result cardinality or retain pre-branch mutation facts.
            for child in children(node):
                sub(child, env.copy())
            from ibl_v2_analysis import assigned_names
            for name in assigned_names(node) & env.keys():
                env[name] = Facts()
            return Facts()
        dependencies = frozenset().union(*(sub(c).dependencies for c in children(node)))
        return Facts(dependencies=dependencies)

    def call(node, env, loops, multiplier, depth, piped=None):
        nonlocal visits
        if node.kind != 'call':
            return Facts()
        d = node.data
        args = {k: walk(v, env, loops, multiplier, depth)
                for k, v in d['params'].data['fields'].items()}
        key = d['node'] + ':' + d['action']
        if key == 'table:each':
            items = piped if piped is not None else args.get('items', Facts())
            if items.count is None:
                unknown(node, 'each 입력 건수 미상')
            local = {**env, 'it': Facts(dependencies=frozenset({node.id})),
                     'i': Facts(dependencies=frozenset({node.id}))}
            walk(d['body'], local, (*loops, (node.id, items.count)),
                 multiplier * items.count if multiplier is not None and items.count is not None else None, depth)
            mode = d['params'].data['fields'].get('mode')
            return Facts(items.count if mode is None or mode.data.get('value') == 'map' else None,
                         items.dependencies)
        sid = d.get('symbol')
        if sid in compiler.functions:
            if sid in active:
                unknown(node, '재귀 함수')
                return Facts()
            fn = compiler.functions[sid]
            params = fn.data['params']
            if piped is not None and params:
                args[next(iter(params))] = piped
            for name, default in params.items():
                args.setdefault(name, walk(default, {}, loops, multiplier, depth))
            active.add(sid)
            try:
                return walk(fn.data['body'], args, loops, multiplier, depth + 1)
            finally:
                active.remove(sid)
        spec = compiler.registry.get(key)
        if spec is None:
            unknown(node, '어휘 계약 미상')
            return Facts()
        from ibl_callable_contract import normalize, selected, UNRESOLVED
        try:
            args = normalize(spec.contract, args)
            fields = normalize(spec.contract, d['params'].data['fields'])
        except Exception:
            unknown(node, '인자 계약 해석 실패')
            return Facts()
        values = {k: v.data['value'] if v.kind == 'literal' else UNRESOLVED for k, v in fields.items()}
        contract = selected(spec.contract, values)
        if piped is not None and contract.get('pipe_input'):
            args[contract['pipe_input']] = piped
        effects = contract.get('effects', [])
        analysis = spec.contract.get('analysis', {})
        inspect_param = analysis.get('ai_inspect_param')
        inspect_only = bool(inspect_param and values.get(inspect_param) in ('batch', 'each'))
        is_model = not inspect_only and ('model' in effects or analysis.get('ai_call') is True)
        if is_model:
            if multiplier is None:
                unknown(node, 'AI 호출 방문 상한 미상')
            else:
                visits += multiplier
            for loop_id, count in loops:
                if count is None or count <= 1 or multiplier == 0:
                    continue
                for name, fact in args.items():
                    if fact.count is not None and fact.count > 1 and loop_id not in fact.dependencies:
                        entry = {'rule': 'repeated_ai_batch', 'code': 'repeated_ai_batch',
                                 'severity': 'warning', 'location': where(node),
                                 'message': '반복 행에 의존하지 않는 목록 전체를 AI 호출에 반복 전달합니다.',
                                 'hint': '행별 판단이면 현재 행을 전달하고, 전체 비교 의도라면 이 경고를 수용하세요.',
                                 'facts': {'argument': name, 'input_count': fact.count,
                                           'repeat_count': count, 'loop': loop_id}}
                        if entry not in warnings:
                            warnings.append(entry)
        elif 'unknown' in effects and not inspect_only:
            unknown(node, '호환·스크립트 경계 내부의 모델 호출은 미상')
        return Facts(dependencies=frozenset().union(*(v.dependencies for v in args.values())))

    env = {k: Facts(len(v) if isinstance(v, list) else None) for k, v in inputs.items()}
    walk(root, env)
    return {'status': 'partial' if unknowns else 'analyzed',
            'declared_ai_visits_upper_bound': None if unknowns else visits,
            'unknowns': unknowns, 'warnings': warnings[:32],
            'warnings_omitted': max(0, len(warnings) - 32),
            'note': '선언된 AI 호출 방문 상한입니다. 도구 내부 호출·토큰·실행 시간·업무 품질의 보증이 아닙니다.'}


def children(node):
    def descend(value):
        if isinstance(value, Node):
            yield value
        elif isinstance(value, dict):
            for v in value.values():
                yield from descend(v)
        elif isinstance(value, (tuple, list)):
            for v in value:
                yield from descend(v)
    yield from descend(node.data)
