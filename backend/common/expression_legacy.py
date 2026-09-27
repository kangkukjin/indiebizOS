"""Legacy Python expression spelling -> common expression IR.

Only an input adapter: no Python compile/eval, tool calls, imports or attributes.
Historical coercions are explicit compatibility nodes, not new-language rules.
"""
import ast
import math
from common.expression_ir import Node, Fault
from common.expression_ops import BUILTINS

OLD_NAMES = {'round', 'abs', 'min', 'max', 'int', 'float', 'len', 'str', 'sqrt', 'log',
             'split', 'replace', 'strip', 'upper', 'lower', 'contains', 'join'}
NUMERIC = {'round', 'abs', 'min', 'max', 'int', 'float', 'sqrt', 'log'}
OPS = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', ast.FloorDiv: '//',
       ast.Mod: '%', ast.Pow: '**', ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<',
       ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>=', ast.In: 'in'}


class Translator:
    def __init__(self, source):
        self.source, self.names, self.cols = source, set(), []
        self.lines = source.splitlines(keepends=True)

    def make(self, source, kind, **data):
        line = max(0, getattr(source, 'lineno', 1) - 1)
        endline = max(0, getattr(source, 'end_lineno', 1) - 1)
        def position(index, column):
            return sum(map(len, self.lines[:index])) + len(self.lines[index].encode()[:column].decode())
        start = position(line, getattr(source, 'col_offset', 0))
        end = position(endline, getattr(source, 'end_col_offset', 0))
        return Node(kind, start, end, data)

    def observed(self, source):
        node = self.convert(source)
        if isinstance(source, (ast.Name, ast.Subscript)) or (isinstance(source, ast.Call) and isinstance(source.func, ast.Name) and source.func.id == 'col'):
            return self.make(source, 'compat', mode='number', value=node)
        return node

    def convert(self, node):
        make = lambda kind, **d: self.make(node, kind, **d)
        sub = self.convert
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (str, int, float, bool, type(None))):
                raise ValueError('지원하지 않는 상수입니다.')
            return make('literal', value=node.value)
        if isinstance(node, ast.Name):
            if node.id.startswith('__') or node.id in ('_semantic_compare', '_observe_number'):
                raise ValueError('금지된 이름')
            if node.id in ('true', 'false', 'null'):
                return make('literal', value={'true': True, 'false': False, 'null': None}[node.id])
            self.names.add(node.id)
            return make('ref', name=node.id)
        if isinstance(node, (ast.List, ast.Tuple)):
            return make('list', values=[sub(x) for x in node.elts], legacy_tuple=isinstance(node, ast.Tuple))
        if isinstance(node, ast.Dict):
            fields, entries = {}, []
            for k, v in zip(node.keys, node.values):
                if k is None:
                    entries.append((None, sub(v)))
                    continue
                key = k.id if isinstance(k, ast.Name) else k.value if isinstance(k, ast.Constant) else None
                if not isinstance(key, str) or key in fields:
                    raise ValueError('객체 키는 중복 없는 문자열 상수여야 합니다.')
                fields[key] = sub(v)
                entries.append((key, fields[key]))
            return make('record', fields=fields, **({'entries': entries} if any(k is None for k, _ in entries) else {}))
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                return make('slice', base=sub(node.value), lower=sub(node.slice.lower) if node.slice.lower else None,
                            upper=sub(node.slice.upper) if node.slice.upper else None,
                            stride=sub(node.slice.step) if node.slice.step else None)
            return make('index', base=sub(node.value), key=sub(node.slice))
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return make('binary', op=OPS[type(node.op)], left=self.observed(node.left), right=self.observed(node.right), legacy=True)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            return make('unary', op='not' if isinstance(node.op, ast.Not) else '-' if isinstance(node.op, ast.USub) else '+',
                        value=make('compat', mode='bool', value=sub(node.operand)) if isinstance(node.op, ast.Not) else self.observed(node.operand), legacy=True)
        if isinstance(node, ast.BoolOp):
            return make('compat_bool', op='and' if isinstance(node.op, ast.And) else 'or', values=[sub(x) for x in node.values])
        if isinstance(node, ast.IfExp):
            return make('conditional', condition=make('compat', mode='bool', value=sub(node.test)),
                        yes=sub(node.body), no=sub(node.orelse))
        if isinstance(node, ast.Compare) and all(type(op) in OPS for op in node.ops):
            return make('comparison_chain', values=[sub(node.left), *[sub(x) for x in node.comparators]],
                        operators=[OPS[type(op)] for op in node.ops])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if node.keywords:
                raise ValueError('기존 식의 함수 인자는 위치로 지정하세요.')
            if name == 'col' and len(node.args) == 1:
                if isinstance(node.args[0], ast.Constant):
                    self.cols.append(str(node.args[0].value))
                return make('compat_col', key=sub(node.args[0]))
            if name not in BUILTINS and name not in OLD_NAMES:
                raise ValueError('허용 함수: ' + ', '.join(sorted(BUILTINS.keys() | OLD_NAMES)))
            args = [self.observed(a) if name in NUMERIC else sub(a) for a in node.args]
            if name in OLD_NAMES:
                # Explicit historical conversion, including str(None), remains
                # in the legacy input adapter. The value operation is shared.
                return make('compat_call', name=name, args=args)
            lo, hi = BUILTINS[name]
            if not lo <= len(args) <= hi:
                raise ValueError(f'{name}: 인자 수는 {lo}~{hi}입니다.')
            return make('pure_call', fn=make('builtin', name=name), args=args)
        raise ValueError('허용되지 않는 구문: ' + type(node).__name__)


def compile_legacy(source):
    source = str(source)
    translator = Translator(source)
    tree = translator.convert(ast.parse(source, mode='eval').body)
    return tree, sorted(translator.names), translator.cols


def compatibility_call(name, args, tick):
    """Boundary-only spelling/coercion adapters; string operations stay shared."""
    from common.expression_ops import pure_call
    from common.value_semantics import text_match
    if name == 'str':
        return str(*args)
    if name in ('int', 'float', 'sqrt', 'log'):
        return {'int': int, 'float': float, 'sqrt': math.sqrt, 'log': math.log}[name](*args)
    if name in ('round', 'abs', 'min', 'max', 'len'):
        if name in ('min', 'max') and len(args) == 1 and isinstance(args[0], (list, tuple)):
            for _ in args[0]:
                tick()
        return {'round': round, 'abs': abs, 'min': min, 'max': max, 'len': len}[name](*args)
    if name == 'contains':
        return text_match('contains', *args)
    adapted = list(args)
    if adapted:
        adapted[0] = str(adapted[0])
    if name == 'replace':
        adapted[1:3] = [str(x) for x in adapted[1:3]]
    if name == 'join' and len(adapted) == 2:
        parts = []
        for part in adapted[1]:
            tick()
            parts.append(str(part))
        adapted[1] = parts
    return pure_call(name, adapted, tick=tick)
