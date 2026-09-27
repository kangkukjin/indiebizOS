"""Compatibility API for legacy expression spelling.

Python AST is translated into the shared expression IR; no compile/eval engine
remains here. New IBL programs use the common parser directly.
"""
from dataclasses import dataclass
from typing import Any, List
from common.expression_legacy import compile_legacy, OLD_NAMES
from common.expression_ops import BUILTINS
from common.expression_eval import ValueEvaluator, Binding
from common.expression_ir import Fault

# Consumers use membership to avoid treating function names as row fields.
FUNCS = dict.fromkeys(BUILTINS.keys() | OLD_NAMES)


def compile_expr(expr):
    return compile_legacy(expr)


def as_num(value):
    from common.value_semantics import numeric_value
    return numeric_value(value)


def eval_expr(code, row, extra=None, *, preserve_values=False):
    from common.value_semantics import require_finite_numbers
    values = {**row, **(extra or {})}
    env = {k: Binding(v) for k, v in values.items() if isinstance(k, str)}
    evaluator = ValueEvaluator(row)
    try:
        return require_finite_numbers(evaluator.eval(code, env).value)
    except Fault as exc:
        raise ValueError(f"{exc.code}: {exc}") from exc


@dataclass
class ProjectionExpr:
    code: Any
    names: List[str]
    cols: List[str]


def compile_projection(spec):
    """선언된 객체·목록 모양을 유지하고 잎의 한 줄 식만 컴파일한다."""
    if isinstance(spec, dict):
        if any(not isinstance(k, str) for k in spec):
            raise ValueError('투영의 키는 문자열이어야 합니다.')
        return {k: compile_projection(v) for k, v in spec.items()}
    if isinstance(spec, list):
        return [compile_projection(v) for v in spec]
    if isinstance(spec, str):
        return ProjectionExpr(*compile_expr(spec))
    if spec is None or isinstance(spec, (int, float, bool)):
        return spec
    raise ValueError('투영에는 객체·목록·한 줄 식·JSON 값만 쓸 수 있습니다.')


def projection_fields(plan):
    if isinstance(plan, ProjectionExpr):
        return set(plan.names) | set(plan.cols)
    if isinstance(plan, (dict, list)):
        vals = plan.values() if isinstance(plan, dict) else plan
        return set().union(*(projection_fields(v) for v in vals))
    return set()


def eval_projection(plan, row):
    # 복사·문자열 함수는 원형, 산술의 숫자 관측은 assign/compute/reduce와 같다.
    if isinstance(plan, ProjectionExpr):
        return eval_expr(plan.code, row, preserve_values=True)
    if isinstance(plan, dict):
        return {k: eval_projection(v, row) for k, v in plan.items()}
    if isinstance(plan, list):
        return [eval_projection(v, row) for v in plan]
    return plan
