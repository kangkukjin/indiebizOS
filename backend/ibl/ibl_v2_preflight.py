"""Bounded plan observations over the current AST, with no tool execution.

Declared model calls, approval policies and static list cardinalities are observed.
Unknown cardinalities/definitions are explicitly reported, never counted as zero.
"""
from dataclasses import dataclass
from functools import cached_property
import copy

from ibl_v2_ir import Node, record_fields
from ibl_v2_analysis import location
from ibl_callable_contract import UNRESOLVED
from common.expression_ops import free_names


@dataclass(frozen=True)
class Facts:
    count: object = None
    dependencies: frozenset = frozenset()
    value: object = UNRESOLVED
    fields: tuple = ()
    target: tuple = ()
    open: bool = True

    @cached_property
    def _hash(self):
        # Shared captures are a DAG, not an exponentially expanded hash tree.
        return hash((self.count, self.dependencies, self.value, self.fields, self.target, self.open))

    def __hash__(self):
        return self._hash


def _scalar(value):
    # Small selector facts only: no arbitrary evaluation or payload copies.
    return value if value is None or type(value) in (bool, int, str) else UNRESOLVED


def _unknown_spread(node):
    return any(key is None and (value.kind != 'record' or _unknown_spread(value))
               for key, value in node.data.get('entries', ()))


def approval_notice(policy, values, key, where, multiplier, conditional):
    """Observe declarations with the gate's op/inheritance semantics, without invoking it."""
    from action_requires import declared
    from ibl_ops import resolve_op, op_names
    if not policy or multiplier == 0:
        return None
    selector = values.get('op')
    dynamic = selector is UNRESOLVED
    if dynamic:
        candidates = op_names(policy)
        choices = [(op, (declared(policy, op) or {}).get('human_confirm') is True)
                   for op in candidates]
        # Include the base policy for unresolved/invalid op values just as gate does.
        base = (declared(policy) or {}).get('human_confirm') is True
        required = [op for op, confirm in choices if confirm]
        if not base and not required:
            return None
        requirement = 'declared' if base and all(confirm for _, confirm in choices) else 'possible'
        op = None
    else:
        op = resolve_op(policy, values)
        if (declared(policy, op) or {}).get('human_confirm') is not True:
            return None
        requirement, required = 'declared', []
    return {'rule': 'human_confirm', 'code': 'HUMAN_CONFIRM', 'severity': 'warning',
            'location': where,
            'message': ('이 호출은 사람 승인 대상으로 선언돼 있습니다. 호출에 도달하면 권한·대상 확인 후 유효한 사람 승인이 필요합니다.'
                        if requirement == 'declared' else
                        'op가 동적으로 결정되어 사람 승인이 필요한 연산을 실행할 수 있습니다.'),
            'hint': 'check는 승인 발급·소비·대상 조회를 하지 않습니다. 실행이 suspended이면 승인 후 같은 code·inputs와 resume으로 이어가세요.',
            'facts': {'action': key, 'op': op, 'requirement': requirement,
                      'selector_dynamic': dynamic, 'conditional': conditional,
                      'visits_upper_bound': multiplier,
                      **({'approval_ops': required[:32], 'approval_ops_omitted': max(0, len(required) - 32)}
                         if dynamic else {})}}


def analyze(compiler, root, inputs):
    warnings, unknowns = [], []
    visits, steps = 0, 0
    active = set()
    callers = []
    summaries = compiler.function_cache  # one compile-local summary store, distinct observation mode
    summary_hits = 0
    warnings_omitted = 0

    def where(node):
        return location(compiler.source, compiler.source_map, node)

    def unknown(node, reason):
        entry = {'location': where(node), 'reason': reason}
        if entry not in unknowns and len(unknowns) < 32:
            unknowns.append(entry)

    def walk(node, env, loops=(), multiplier=1, depth=0, conditional=False):
        nonlocal visits, steps
        if node is None:
            return Facts()
        steps += 1
        if steps > 2000 or depth > 128:
            unknown(node, '분석 예산 초과')
            return Facts()
        d, kind = node.data, node.kind
        sub = lambda n, e=env: walk(n, e, loops, multiplier, depth, conditional)
        if kind == 'literal':
            return Facts(value=_scalar(d['value']))
        if kind == 'ref':
            return env.get(d['name'], Facts())
        if kind == 'list':
            values = [sub(v) for v in d['values']]
            deps = frozenset().union(*(v.dependencies for v in values))
            return Facts(len(values), deps, fields=tuple(enumerate(values)), open=False)
        if kind == 'record':
            fields, opened = {}, False
            for key, child in d.get('entries', d.get('fields', {}).items()):
                value = sub(child)
                if key is None:
                    if value.open:
                        fields.clear()  # unknown spread may replace every earlier field
                        opened = True
                    fields.update(dict(value.fields))
                else:
                    fields[key] = value
            return Facts(fields=tuple(fields.items()), open=opened)
        if kind in ('field', 'index'):
            base = sub(d['base'])
            key = d['key'] if kind == 'field' else sub(d['key']).value
            return dict(base.fields).get(key, Facts())
        if kind == 'builtin':
            return Facts(target=('builtin', d['name']))
        if kind == 'callable_ref':
            return Facts(target=('function', d['symbol']) if d.get('symbol') else
                         ('action', d['node'] + ':' + d['action']))
        if kind == 'lambda':
            captures = tuple(sorted((k, env[k]) for k in free_names(node) if k in env))
            return Facts(target=('lambda', node.id, captures))
        if kind in ('pure_call', 'named_call'):
            return application(node, env, loops, multiplier, depth, conditional)
        if kind == 'conditional':
            condition = sub(d['condition']).value
            if type(condition) is bool:
                return sub(d['yes'] if condition else d['no'])
            yes, no = sub(d['yes']), sub(d['no'])
            return yes if yes == no else Facts(target=('alternatives', yes, no))

        if kind == 'bind':
            env[d['name']] = sub(d['value'])
            return Facts()
        if kind == 'return':
            return sub(d['value'])
        if kind == 'def':
            return Facts()
        if kind == 'sequence':
            result = Facts()
            for statement in d['statements']:
                result = sub(statement)
                if compiler.returns_unconditionally(statement):
                    break
            return result
        if kind == 'pipe':
            source = sub(d['left'])
            if d['right'].kind == 'call':
                return call(d['right'], env, loops, multiplier, depth, source, conditional)
            return application(d['right'], env, loops, multiplier, depth, conditional, source)
        if kind == 'call':
            return call(node, env, loops, multiplier, depth, conditional=conditional)
        if kind == 'repeat':
            value = sub(d['value']).value
            if d['mode'] == 'while' and value is False:
                return Facts()
            count = value if d['mode'] == 'count' else None
            count = count if type(count) is int and count >= 0 else None
            if count is None:
                unknown(node, '동적 반복 횟수')
            if count == 0:
                return Facts()
            local = env.copy()
            from ibl_v2_analysis import assigned_names
            if count is None or count > 1:
                for name in assigned_names(d['body']) & local.keys():
                    local[name] = Facts()
            local['i'] = Facts(dependencies=frozenset({node.id}))
            walk(d['body'], local, (*loops, (node.id, count)),
                 multiplier * count if multiplier is not None and count is not None else None, depth,
                 conditional or count is None)
            # Repeated mutation is not a proof of an exact post-loop cardinality.
            from ibl_v2_analysis import assigned_names
            for name in assigned_names(d['body']) & env.keys():
                env[name] = Facts()
            return Facts()
        if kind == 'if':
            condition = sub(d['value']).value
            if type(condition) is bool:
                return sub(d['body'] if condition else d['otherwise'])
        if kind in ('if', 'case', 'try', 'fallback', 'parallel'):
            # Visit all branches for a conservative bound, but do not assert an
            # exact result cardinality or retain pre-branch mutation facts.
            for child in children(node):
                walk(child, env.copy(), loops, multiplier, depth, conditional or kind != 'parallel')
            from ibl_v2_analysis import assigned_names
            for name in assigned_names(node) & env.keys():
                env[name] = Facts()
            return Facts()
        dependencies = frozenset().union(*(sub(c).dependencies for c in children(node)))
        return Facts(dependencies=dependencies)

    def application(node, env, loops, multiplier, depth, conditional, piped=None):
        if node.kind not in ('pure_call', 'named_call'):
            unknown(node, '미확정 적용 대상')
            return Facts()
        d = node.data
        target = walk(d['fn'], env, loops, multiplier, depth, conditional)
        open_args = False
        if node.kind == 'named_call':
            params = walk(d['params'], env, loops, multiplier, depth, conditional)
            args, open_args = dict(params.fields), params.open
            if open_args:
                unknown(node, '열린 명명 인자')
        else:
            args = [walk(n, env, loops, multiplier, depth, conditional) for n in d['args']]
            if piped is not None:
                args.insert(0, piped)
        return apply_fact(node, target, args, env, loops, multiplier, depth, conditional,
                          piped if isinstance(args, dict) else None, open_args)

    def apply_fact(node, fact, args, env, loops, multiplier, depth, conditional, piped=None, open_args=False):
        target = fact.target
        if not target:
            unknown(node, '호출 부품 계약 미상')
            return Facts()
        kind = target[0]
        if kind == 'alternatives':
            values = [apply_fact(node, v, args, env, loops, multiplier, depth, True, piped, open_args)
                      for v in target[1:]]
            return values[0] if all(v == values[0] for v in values) else Facts()
        if kind == 'lambda':
            body = compiler.lambda_nodes[target[1]]
            params = body.data['params']
            actual = dict(args) if isinstance(args, dict) else dict(zip(params, args))
            if piped is not None and params:
                actual[params[0]] = piped
            if open_args:
                for param in params:
                    actual.setdefault(param, Facts())
            actual = {**dict(target[2]), **actual}
            return body_summary(node, target[1], body.data['body'], actual, loops, multiplier, depth, conditional)
        if kind in ('function', 'action'):
            if not isinstance(args, dict):
                unknown(node, '명명 인자 계약 미상')
                return Facts()
            if kind == 'function':
                fn = compiler.functions[target[1]]
                if fn.data.get('semantic_interface'):
                    unknown(node, '저장 의미 인터페이스: 실행 비용 상한은 미확정')
                    return Facts()
                owner, action = 'fn', fn.data['name']
            else:
                owner, action = target[1].split(':', 1)
            data = {'node': owner, 'action': action,
                    'params': Node('record', node.start, node.end, {'fields':{}})}
            if kind == 'function':
                data['symbol'] = target[1]
            virtual = Node('call', node.start, node.end, data)
            return call(virtual, env, loops, multiplier, depth, piped, conditional, args, open_args)
        name = target[1]
        if isinstance(args, dict):
            unknown(node, '위치 인자 계약 미상')
            return Facts()
        if name == 'get' and len(args) >= 2:
            if args[1].value is UNRESOLVED:
                return Facts()
            fields = dict(args[0].fields)
            if args[1].value in fields:
                return fields[args[1].value]
            if args[0].open:
                return Facts()
            return args[2] if len(args) > 2 else Facts(value=None)
        if name in ('map', 'filter', 'sorted', 'reduce') and args:
            count = args[0].count
            if count == 0:
                return args[1] if name == 'reduce' else Facts(0)
            callback = args[2] if name == 'reduce' and len(args) > 2 else args[1] if len(args) > 1 else None
            if callback and callback.target:
                row = next(iter(dict(args[0].fields).values()), Facts()) if count == 1 else Facts()
                cb_args = [args[1], row] if name == 'reduce' else [row]
                output = apply_fact(node, callback, cb_args, env, loops,
                                    multiplier * count if multiplier is not None and count is not None else None,
                                    depth + 1, conditional)
                if name == 'map':
                    return Facts(count, fields=((0, output),) if count == 1 else ())
                if name == 'reduce':
                    return output
            return Facts(count)
        return Facts(dependencies=frozenset().union(*(a.dependencies for a in args)))

    def body_summary(node, sid, body, args, loops, multiplier, depth, conditional):
        nonlocal visits, warnings, unknowns, summary_hits, warnings_omitted
        if sid in active:
            unknown(node, '재귀 부품')
            return Facts()
        cache_key = ('visits', sid, tuple(sorted(args.items())), loops, multiplier, conditional)
        saved = summaries.get(cache_key) if compiler.analysis_cache_enabled else None
        if saved is None:
            before_visits = visits
            outer_warnings, outer_unknowns, outer_omitted = warnings, unknowns, warnings_omitted
            warnings, unknowns, warnings_omitted = [], [], 0
            active.add(sid)
            callers.append(where(node))
            try:
                result = walk(body, args, loops, multiplier, depth + 1, conditional)
                relative = copy.deepcopy(warnings)
                for entry in relative:
                    facts = entry.get('facts', {})
                    if 'callers' in facts:
                        facts['callers'] = facts['callers'][len(callers):]
                saved = (result, visits - before_visits, relative, unknowns, warnings_omitted)
                if compiler.analysis_cache_enabled:
                    summaries[cache_key] = saved
            finally:
                callers.pop()
                active.remove(sid)
                warnings, unknowns, warnings_omitted = outer_warnings, outer_unknowns, outer_omitted
        else:
            summary_hits += 1
            visits += saved[1]
        warnings_omitted += saved[4]
        for entry in saved[2]:
            entry = copy.deepcopy(entry)
            facts = entry.get('facts', {})
            if 'callers' in facts:
                facts['callers'] = [*callers, where(node), *facts['callers']]
            if entry not in warnings:
                if len(warnings) < 32:
                    warnings.append(entry)
                else:
                    warnings_omitted += 1
        for entry in saved[3]:
            if entry not in unknowns and len(unknowns) < 32:
                unknowns.append(entry)
        return saved[0]

    def call(node, env, loops, multiplier, depth, piped=None, conditional=False, supplied=None, supplied_open=False):
        nonlocal visits, warnings, unknowns, summary_hits, warnings_omitted
        if node.kind != 'call':
            return Facts()
        d = node.data
        if 'entries' in d['params'].data:
            unknown(node, '펼침 인자의 값·효과는 실행 시 해소합니다.')
        args = (dict(supplied) if supplied is not None else
                {k: walk(v, env, loops, multiplier, depth, conditional)
                 for k, v in record_fields(d['params']).items()})
        key = d['node'] + ':' + d['action']
        if key == 'table:each':
            items = piped if piped is not None else args.get('items', Facts())
            if items.count is None:
                unknown(node, 'each 입력 건수 미상')
            if items.count == 0:
                return Facts(0)
            local = {**env, 'it': Facts(dependencies=frozenset({node.id})),
                     'i': Facts(dependencies=frozenset({node.id}))}
            from ibl_v2_analysis import assigned_names
            if items.count is None or items.count > 1:
                for name in assigned_names(d['body']) & env.keys():
                    local[name] = Facts()
            walk(d['body'], local, (*loops, (node.id, items.count)),
                 multiplier * items.count if multiplier is not None and items.count is not None else None, depth,
                 conditional or items.count is None)
            mode = record_fields(d['params']).get('mode')
            return Facts(items.count if mode is None or mode.data.get('value') == 'map' else None,
                         items.dependencies)
        sid = d.get('symbol')
        if sid in compiler.functions:
            if sid in active:
                unknown(node, '재귀 함수')
                return Facts()
            fn = compiler.functions[sid]
            if fn.data.get('semantic_interface'):
                unknown(node, '저장 의미 인터페이스: 실행 비용 상한은 미확정')
                return Facts()
            params = fn.data['params']
            if piped is not None and params:
                args[next(iter(params))] = piped
            for name, default in params.items():
                if name not in args:
                    args[name] = (Facts() if supplied_open else
                                  walk(default, {}, loops, multiplier, depth, conditional))
            return body_summary(node, sid, fn.data['body'], args, loops, multiplier, depth, conditional)
        spec = compiler.registry.get(key)
        if spec is None:
            unknown(node, '어휘 계약 미상')
            return Facts()
        from ibl_callable_contract import normalize, selected, UNRESOLVED
        if supplied_open:
            for name in spec.contract['params']:
                args.setdefault(name, Facts())
        try:
            args = normalize(spec.contract, args)
            fields = normalize(spec.contract, record_fields(d['params']))
        except Exception:
            unknown(node, '인자 계약 해석 실패')
            return Facts()
        values = {k: v.value for k, v in args.items()}
        contract = selected(spec.contract, values)
        from ibl_callable_contract import pipe_receiver
        receiver = pipe_receiver(contract, args)
        if piped is not None and receiver:
            args[receiver] = piped
        effects = contract.get('effects', [])
        analysis = spec.contract.get('analysis', {})
        fixed = spec.contract.get('adapter', {}).get('fixed_params', {})
        approval_values = {**spec.contract.get('defaults', {}), **{k: v.value for k, v in args.items()}, **fixed}
        if 'op' not in args and 'op' not in fixed and (_unknown_spread(d['params']) or
                ('op' not in approval_values and spec.contract.get('adapter', {}).get('protocol') == 'ibl-script/2')):
            approval_values['op'] = UNRESOLVED
        notice = approval_notice(analysis.get('approval_policy'), approval_values, key, where(node),
                                 multiplier, conditional)
        if notice:
            if callers:
                notice['facts']['callers'] = list(callers)
            if notice not in warnings:
                warnings.append(notice)
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
                # Only the payload is repeated work. Column/schema/contract
                # lists configure a call; they are not batch input data.
                payload = contract.get('pipe_input')
                for name, fact in args.items():
                    if name != payload:
                        continue
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

    env = {k: Facts(len(v) if isinstance(v, list) else None, value=_scalar(v)) for k, v in inputs.items()}
    walk(root, env)
    return {'status': 'partial' if unknowns else 'analyzed',
            'declared_ai_visits_upper_bound': None if unknowns else visits,
            'unknowns': unknowns, 'warnings': warnings[:32],
            'analysis_steps': steps, 'function_summary_reuses': summary_hits,
            'warnings_omitted': warnings_omitted + max(0, len(warnings) - 32),
            'note': '선언된 호출의 정적 안내입니다. 승인 안내의 방문 상한은 실제 승인 횟수가 아닙니다. 경고 부재도 승인 불필요의 보증이 아니며, 도구 내부 호출·토큰·실행 시간·업무 품질은 보증하지 않습니다.'}


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
