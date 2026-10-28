"""Compile-local callable contracts and reusable function-body observations.

Only analysis is memoized. Runtime calls, receipts and authorization are untouched.
Diagnostic paths retain a representative and a count instead of expanding a DAG.
"""
import copy

from ibl_v2_ir import Node, span
from ibl_v2_types import Type, UNKNOWN, NEVER, join, alternatives
from ibl_v2_expr import BUILTINS, free_names
from ibl_v2_analysis import builtin_type


def merge_diagnostics(target, entries, prefix=()):
    for entry in entries:
        item = copy.deepcopy(entry)
        item['call_path'] = list(prefix) + item.get('call_path', [])
        identity = {k: v for k, v in item.items() if k not in ('call_path', 'call_paths_omitted')}
        previous = next((v for v in target if
                         {k: x for k, x in v.items() if k not in ('call_path', 'call_paths_omitted')} == identity), None)
        if previous is None:
            target.append(item)
        elif previous.get('call_path') != item.get('call_path') or item.get('call_paths_omitted'):
            previous['call_paths_omitted'] = (previous.get('call_paths_omitted', 0)
                                             + item.get('call_paths_omitted', 0) + 1)


class CallAnalysis:
    def init_call_analysis(self):
        self.function_cache = {}
        self.semantic_functions = {}
        self.semantic_abilities = {}
        self.analysis_stats = {kind + suffix: 0 for kind in ('function', 'lambda', 'builtin', 'action')
                               for suffix in ('_bodies', '_reuses')}
        self.summary_active = set()
        self.lambda_nodes = {}
        self.lambda_contracts = {}
        self.lambda_checked = set()
        self.analysis_cache_enabled = True

    def function(self, sid, args, call=None):
        definition = self.functions[sid]
        frame = {'function': definition.data['name'],
                 'call': span(self.source, call) if call else None,
                 'definition': span(self.source, definition)}
        def analyze():
            if sid in self.semantic_functions:
                from ibl_v2_semantic import apply_function
                return apply_function(self, sid, args, call)
            return self._function(sid, args, call)
        return self.summary(('function', sid, tuple(sorted(args.items()))), call or definition,
                            frame, analyze, 'function')

    def summary(self, identity, call, frame, analyze, category):
        """One compile-local summary boundary for every callable producer.

        Full abstract inputs/captures are keys; invocation locations are applied
        after reuse. Mutable caller effects and diagnostics never enter a key.
        """
        key = identity, self.reachable, self.catch_value_faults
        if key in self.summary_active:
            self.issue(call, 'RECURSION', '재귀 호출은 지원하지 않습니다.')
            return UNKNOWN
        cached = self.function_cache.get(key) if self.analysis_cache_enabled else None
        if cached is None:
            if len(self.function_cache) >= 4096 or len(self.summary_active) >= 128:
                self.need(call, UNKNOWN, Type('Callable'))
                self.guards.append({'source_span': span(self.source, call),
                                    'expected': '부품 분석 특수화 예산 초과', 'specializations_omitted': 1})
                self.effects.add('unknown')
                self.call_effects.setdefault(call.id, set()).add('unknown')
                return UNKNOWN
            self.analysis_stats[category + '_bodies'] += 1
            outer = (self.issues, self.guards, self.warnings, self.effects,
                     self.used_actions, self.access_log, self.call_path,
                     self.pure_calls, self.call_effects, self.requirement_log, self.requirement_depth)
            self.issues, self.guards, self.warnings = [], [], []
            self.effects, self.used_actions, self.access_log = set(), set(), set()
            self.call_path, self.pure_calls, self.call_effects = [], [], {}
            self.requirement_log, self.requirement_depth = {}, 0
            self.summary_active.add(key)
            try:
                result = analyze()
                self.check_purity()
                diagnostics = []
                for items in (self.issues, self.guards, self.warnings):
                    compact = []
                    merge_diagnostics(compact, items)
                    for item in compact:
                        item['call_path'] = item.get('call_path', [])[1:]
                    diagnostics.append(compact)
                cached = (result, frozenset(self.effects), frozenset(self.used_actions),
                          frozenset(self.access_log), diagnostics, tuple(self.requirement_log.values()))
                if self.analysis_cache_enabled:
                    self.function_cache[key] = cached
            finally:
                self.summary_active.remove(key)
                (self.issues, self.guards, self.warnings, self.effects,
                 self.used_actions, self.access_log, self.call_path,
                 self.pure_calls, self.call_effects, self.requirement_log, self.requirement_depth) = outer
        else:
            self.analysis_stats[category + '_reuses'] += 1
        result, effects, actions, writes, diagnostics, requirements = cached
        for sid, name, condition, expected, depth in requirements:
            own = identity[0] == 'function' and sid == identity[1]
            from ibl_v2_requirements import emit
            emit(self, sid, name, condition, expected,
                 depth + (0 if own else self.requirement_depth))
        self.effects.update(effects)
        self.used_actions.update(actions)
        self.access_log.update(writes)
        self.call_effects.setdefault(call.id, set()).update(effects or {'pure'})
        for target, items in zip((self.issues, self.guards, self.warnings), diagnostics):
            merge_diagnostics(target, items, [*self.call_path, frame])
        return result

    def check_purity(self):
        for call in self.pure_calls:
            effects = self.call_effects.get(call.id)
            if effects is None or effects - {'pure'}:
                self.issue(call, 'PURE_EXPRESSION',
                           '이 자리의 호출은 순수해야 합니다(효과: '
                           + ', '.join(sorted((effects or {'unknown'}) - {'pure'})) + ').',
                           hint='효과 있는 작업은 일반 호출·함수·each 본문에서 적용하세요.')

    def reference_type(self, node, names):
        d = node.data
        if d['node'] == 'fn':
            sid = self.resolve_function(d['action'], names)
            if sid:
                d['symbol'] = sid
                params = self.functions[sid].data['params']
                return Type('Callable', item=('function', sid, d['action'], tuple(params),
                                             tuple(k for k,v in params.items() if v is None)))
        key = d['node'] + ':' + d['action']
        if key not in self.registry or key == 'table:each':
            self.issue(node, 'UNSUPPORTED_ADAPTER', f'참조할 호출 계약이 없습니다: {key}')
            return UNKNOWN
        self.used_actions.add(key)  # references pin contracts even without invocation
        contract = self.registry[key].contract
        from ibl_v2_types import declared
        return Type('Callable', item=('action', key,
                    tuple((k, declared(v)) for k,v in contract['params'].items()),
                    tuple(contract.get('required', contract['params'])), contract.get('pipe_input'),
                    tuple(contract['effects']), declared(contract['result'])))

    def lambda_type(self, node, env, names, readonly):
        self.lambda_nodes[node.id] = node
        captures = tuple(sorted((k, env[k]) for k in free_names(node) if k in env))
        typ = Type('Callable', item=('lambda', node.id, captures, tuple(sorted(names.items())),
                                     tuple(sorted(readonly)), tuple(node.data['params'])))
        self.lambda_contracts[node.id] = typ
        return typ

    def apply_callable(self, node, typ, types, nodes, env=None, names=None, readonly=frozenset(),
                       *, piped=None, require_pure=False):
        if isinstance(types, Type) and types.kind == 'Union':
            result = NEVER
            for arguments in alternatives(types):
                branch_nodes = nodes
                if isinstance(nodes, Node) and nodes.kind != 'record':
                    from ibl_v2_semantic import literal_node
                    branch_nodes = literal_node(arguments, node)
                result = join(result, self.apply_callable(node, typ, arguments, branch_nodes, env, names, readonly,
                                                         piped=piped, require_pure=require_pure))
            return result
        from ibl_v2_requirements import application
        required = application(self, node, typ, types, require_pure or node in self.pure_calls)
        if required is not None:
            effects = {'pure'} if require_pure or node in self.pure_calls else {'unknown'}
            self.effects.update(effects)
            self.call_effects.setdefault(node.id, set()).update(effects)
            return required
        outer_effects, self.effects = self.effects, set()
        try:
            return self._apply_callable(node, typ, types, nodes, env, names, readonly, piped)
        finally:
            effects = self.effects
            if require_pure and effects - {'pure'}:
                self.issue(node, 'PURE_EXPRESSION', '이 콜백에는 효과가 없어야 합니다.',
                           effects=sorted(effects))
            self.effects = outer_effects | effects

    def _apply_callable(self, node, typ, types, nodes, env, names, readonly, piped):
        if typ == NEVER:
            return NEVER
        result = NEVER
        candidates = list(alternatives(typ))
        if len(candidates) > 64:
            self.guards.append({'source_span': span(self.source, node),
                                'expected': '호출 계약 대안이 64개를 넘어 나머지는 실행 경계에서 검사합니다.',
                                'alternatives_omitted': len(candidates) - 64})
            self.effects.add('unknown')
            self.call_effects.setdefault(node.id, set()).add('unknown')
            result = UNKNOWN
        for candidate in candidates[:64]:
            self.need(node, candidate, Type('Callable'))
            contract = candidate.item if candidate.kind == 'Callable' else None
            if not contract:
                self.need(node, UNKNOWN, Type('Callable'))
                self.call_effects.setdefault(node.id, set()).add('unknown')
                self.effects.add('unknown')
                result = join(result, UNKNOWN)
                continue
            category = contract[0]
            named = isinstance(types, Type)
            if category == 'semantic':
                from ibl_v2_semantic import apply
                _, identity, captures, params = contract
                if piped is not None and not named:
                    types = [piped, *types]
                actual = dict(types.fields) if named else dict(zip(params, types))
                if named:
                    virtual = Node(node.kind, node.start, node.end, {'open_arguments': types.open})
                    self.arguments(virtual, actual, dict.fromkeys(params), next(iter(params), None), piped)
                elif len(types) != len(params):
                    self.issue(node, 'ARITY', '의미 인터페이스 콜백 인자가 다릅니다.')
                bound = {**dict(captures), **actual}
                frame = {'function': '<relation>', 'call': span(self.source, node), 'definition': None}
                current = self.summary(('semantic', identity, tuple(sorted(bound.items()))), node, frame,
                    lambda: apply(self, self.semantic_abilities[identity], bound, node), 'lambda')
                self.call_effects.setdefault(node.id, set()).update(self.effects or {'pure'})
            elif category == 'requirement':
                _, params, returned, effects = contract
                if isinstance(params, tuple) != (not named):
                    self.issue(node, 'ARGUMENT_STYLE', '명시 콜백 계약의 인자 방식과 다릅니다.')
                elif not named:
                    if len(types) != len(params):
                        self.issue(node, 'ARITY', '명시 콜백 계약의 인자 수와 다릅니다.')
                    for actual, expected in zip(types, params):
                        from ibl_v2_requirements import annotation
                        annotation(self, node, actual, expected)
                else:
                    from ibl_v2_requirements import annotation
                    annotation(self, node, types, params)
                self.effects.update(effects)
                self.call_effects.setdefault(node.id, set()).update(effects)
                current = returned
            elif category in ('function', 'action'):
                if not named:
                    self.issue(node, 'ARGUMENT_STYLE', '이 부품은 명명 인자 {...}로 적용하세요.')
                    current = UNKNOWN
                else:
                    owner, action = ('fn', contract[2]) if category == 'function' else contract[1].split(':', 1)
                    data = {'node': owner, 'action': action, 'params': nodes, 'body': None}
                    if category == 'function':
                        data['symbol'] = contract[1]
                    # Retain per-target metadata for dependency checks. The runtime
                    # selects by immutable target identity, never by guessed name.
                    target = contract[1]
                    data = node.data.setdefault('applications', {}).setdefault(target, data)
                    virtual = Node('call', node.start, node.end, data)
                    scope = {action: contract[1]} if category == 'function' else {}
                    current = self.named_target(virtual, types, env or {}, scope, readonly, piped)
                    self.call_effects.setdefault(node.id, set()).update(
                        self.call_effects.get(virtual.id, {'unknown'}))
            elif category == 'builtin':
                name = contract[1]
                if named:
                    self.issue(node, 'ARGUMENT_STYLE', '내장 함수는 위치 인자 (...)로 적용하세요.')
                    current = UNKNOWN
                elif name not in BUILTINS:
                    current = UNKNOWN
                else:
                    low, high = BUILTINS[name]
                    if not low <= len(types) <= high:
                        self.issue(node, 'ARITY', f'{name}은 인자 {low}~{high}개를 받습니다(받은 인자 {len(types)}개).')
                        current = UNKNOWN
                    else:
                        virtual = Node('pure_call', node.start, node.end, {'args': nodes})
                        frame = {'function': name, 'call': span(self.source, node), 'definition': None}
                        current = self.summary(('builtin', name, node.id, tuple(types)), node, frame,
                                               lambda: builtin_type(self, virtual, name, types, env, names, readonly),
                                               'builtin')
                        self.call_effects.setdefault(node.id, set()).update(self.effects or {'pure'})
            elif category == 'lambda':
                _, lid, captures, scope, locked, _ = contract
                body = self.lambda_nodes[lid]
                params = body.data['params']
                if named:
                    args = dict(types.fields)
                    virtual = Node(node.kind, node.start, node.end, {'open_arguments': types.open})
                    self.arguments(virtual, args, dict.fromkeys(params), next(iter(params), None), piped)
                    actual = [args.get(p, UNKNOWN) for p in params]
                else:
                    actual = types
                if len(params) != len(actual):
                    self.issue(node, 'ARITY', f'람다는 인자 {len(params)}개를 받습니다(받은 인자 {len(actual)}개).')
                    current = UNKNOWN
                else:
                    self.lambda_checked.add(lid)
                    frame = {'function': '<lambda>', 'call': span(self.source, node),
                             'definition': span(self.source, body)}
                    def analyze():
                        self.call_path.append(frame)
                        try:
                            return self.visit(body.data['body'], {**dict(captures), **dict(zip(params, actual))},
                                              dict(scope), frozenset(locked))
                        finally:
                            self.call_path.pop()
                    current = self.summary(('lambda', contract, tuple(actual)), node, frame, analyze, 'lambda')
            else:
                current = UNKNOWN
            result = join(result, current)
        return result
