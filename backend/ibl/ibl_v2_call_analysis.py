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
        self.analysis_stats = {'function_bodies': 0, 'function_reuses': 0}
        self.lambda_nodes = {}
        self.lambda_contracts = {}
        self.lambda_checked = set()
        self.lambda_active = set()
        self.analysis_cache_enabled = True

    def function(self, sid, args, call=None):
        # Registry/lexical definitions are immutable within this compiler. Full
        # structural types retain literals, captures and callable alternatives.
        key = (sid, tuple(sorted(args.items())), self.reachable)
        if sid in self.stack:
            return self._function(sid, args, call)
        cached = self.function_cache.get(key) if self.analysis_cache_enabled else None
        if cached is None:
            self.analysis_stats['function_bodies'] += 1
            outer = (self.issues, self.guards, self.warnings, self.effects,
                     self.used_actions, self.write_log, self.call_path)
            self.issues, self.guards, self.warnings = [], [], []
            self.effects, self.used_actions, self.write_log = set(), set(), set()
            self.call_path = []
            try:
                result = self._function(sid, args, call)
                diagnostics = []
                for items in (self.issues, self.guards, self.warnings):
                    compact = []
                    merge_diagnostics(compact, items)
                    # The first frame belongs to the invocation, not the body.
                    for item in compact:
                        item['call_path'] = item.get('call_path', [])[1:]
                    diagnostics.append(compact)
                cached = (result, self.effects, self.used_actions, self.write_log, diagnostics)
                if self.analysis_cache_enabled:
                    self.function_cache[key] = cached
            finally:
                (self.issues, self.guards, self.warnings, self.effects,
                 self.used_actions, self.write_log, self.call_path) = outer
        else:
            self.analysis_stats['function_reuses'] += 1
        result, effects, actions, writes, diagnostics = cached
        self.effects.update(effects)
        self.used_actions.update(actions)
        self.write_log.update(writes)
        if call is not None:
            self.call_effects.setdefault(call.id, set()).update(effects)
        definition = self.functions[sid]
        frame = {'function': definition.data['name'],
                 'call': span(self.source, call) if call else None,
                 'definition': span(self.source, definition)}
        for target, items in zip((self.issues, self.guards, self.warnings), diagnostics):
            merge_diagnostics(target, items, [*self.call_path, frame])
        return result

    def lambda_type(self, node, env, names, readonly):
        self.lambda_nodes[node.id] = node
        captures = tuple(sorted((k, env[k]) for k in free_names(node) if k in env))
        typ = Type('Callable', item=('lambda', node.id, captures, tuple(sorted(names.items())),
                                     tuple(sorted(readonly)), tuple(node.data['params'])))
        self.lambda_contracts[node.id] = typ
        return typ

    def apply_callable(self, node, typ, types, nodes, env=None, names=None, readonly=frozenset()):
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
            if contract[0] == 'builtin':
                name = contract[1]
                if name not in BUILTINS:
                    result = join(result, UNKNOWN)
                    continue
                low, high = BUILTINS[name]
                if not low <= len(types) <= high:
                    self.issue(node, 'ARITY', f'{name}은 인자 {low}~{high}개를 받습니다(받은 인자 {len(types)}개).')
                    result = join(result, UNKNOWN)
                    continue
                virtual = Node('pure_call', node.start, node.end, {'args': nodes})
                outer_effects, self.effects = self.effects, set()
                try:
                    current = builtin_type(self, virtual, name, types, env, names, readonly)
                    self.call_effects.setdefault(node.id, set()).update(self.effects or {'pure'})
                finally:
                    self.effects = outer_effects | self.effects
            elif contract[0] == 'lambda':
                _, lid, captures, scope, locked, _ = contract
                body = self.lambda_nodes[lid]
                params = body.data['params']
                if len(params) != len(types):
                    self.issue(node, 'ARITY', f'람다는 인자 {len(params)}개를 받습니다(받은 인자 {len(types)}개).')
                    current = UNKNOWN
                elif lid in self.lambda_active:
                    self.issue(node, 'RECURSION', '재귀 콜백은 지원하지 않습니다.')
                    current = UNKNOWN
                else:
                    self.lambda_checked.add(lid)
                    self.lambda_active.add(lid)
                    outer_effects, self.effects = self.effects, set()
                    try:
                        self.pure(body.data['body'])
                        current = self.visit(body.data['body'], {**dict(captures), **dict(zip(params, types))},
                                             dict(scope), frozenset(locked))
                        effects = self.effects
                        self.call_effects.setdefault(node.id, set()).update(effects or {'pure'})
                    finally:
                        self.effects = outer_effects | self.effects
                        self.lambda_active.remove(lid)
            else:
                current = UNKNOWN
            result = join(result, current)
        return result
