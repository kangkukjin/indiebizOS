"""safe_expr.py — 한 줄 식 평가기(ast 화이트리스트) — [table:reduce] 의 step 식 (2026-08-22 M5).

data-ops `[table:compute]` 의 `_compute_compile` 과 같은 화이트리스트·같은 함수 집합. 패키지 핸들러를
엔진 층이 import 하면 층 역전이라 공용 층(common)에 한 벌 더 둔다 — 허용 목록이 갈라지지 않게
두 자리 모두 이 파일의 상수를 정본으로 본다 — compute(data-ops) 는 2026-08-22 정리로 이쪽을 import 해 재수출한다(화이트리스트 단일 소스).
"""
import ast as _ast
import math as _math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

FUNCS: Dict[str, Any] = {"round": round, "abs": abs, "min": min, "max": max, "int": int,
                         "float": float, "len": len, "str": str, "sqrt": _math.sqrt, "log": _math.log,
                         # ★문자열 함수 (언어 개정 2026-08-27, 사용자 판정): 지역명 추출 같은
                         #   결정론 가공이 AI 한 칸(비용·비결정)으로 우회되던 것을 연다.
                         #   메서드가 아니라 함수형 — 이 식 언어의 기존 문법 그대로.
                         #   split(s, sep)[0] 꼴은 Subscript 가 이미 NODES 에 있어 그대로 된다.
                         "split": lambda s, sep=None: str(s).split(sep if sep is not None else None),
                         "replace": lambda s, a, b: str(s).replace(str(a), str(b)),
                         "strip": lambda s, chars=None: str(s).strip(chars),
                         "upper": lambda s: str(s).upper(),
                         "lower": lambda s: str(s).lower(),
                         "contains": lambda s, sub: _contains(s, sub),
                         "join": lambda sep, parts: str(sep).join(str(p) for p in parts)}


def _contains(s, sub):
    """contains 는 조건 언어와 같은 한 벌 판정(value_semantics.text_match, B46-6) —
    한 낱말이 식과 조건에서 다른 판결을 내면 안 된다. 지연 임포트는 아래
    _semantic_compare 와 같은 관례."""
    from common.value_semantics import text_match
    return text_match("contains", s, sub)
NODES = (_ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Constant, _ast.Name, _ast.Load,
         _ast.Call, _ast.Compare, _ast.BoolOp, _ast.IfExp, _ast.Subscript, _ast.Tuple,
         _ast.Dict, _ast.List,
         _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.FloorDiv, _ast.Mod, _ast.Pow,
         _ast.USub, _ast.UAdd, _ast.Not, _ast.And, _ast.Or,
         _ast.Eq, _ast.NotEq, _ast.Lt, _ast.LtE, _ast.Gt, _ast.GtE)


_CMP_NAME = "_semantic_compare"
_CMP_OPS = {_ast.Eq: "==", _ast.NotEq: "!=", _ast.Lt: "<", _ast.LtE: "<=",
            _ast.Gt: ">", _ast.GtE: ">="}


def _semantic_compare(left: Any, pairs) -> bool:
    """식 안의 비교도 조건 언어와 같은 한 벌 판정 (2026-08-27 표면 동형성).

    파이썬 원시 비교는 "Seoul"=="seoul" 을 거짓, 혼합 타입 순서를 TypeError 로 읽어
    같은 몸의 filter/블록 술어와 다른 선고를 냈다(B46-6 과 같은 속). 동등=values_equal,
    순서=compare_order — 판정 불능은 조용한 False 가 아니라 ValueError(그 행 None+신고,
    compute 의 기존 형 오류 경로와 같은 봉투).
    """
    from common.value_semantics import compare_order, values_equal
    cur = left
    for op, right in pairs:
        if op == "==":
            ok = values_equal(cur, right)
        elif op == "!=":
            ok = not values_equal(cur, right)
        else:
            order = compare_order(cur, right)
            if order is None:
                raise ValueError(
                    f"크기 비교({op}) 불가 — {type(cur).__name__} 와 {type(right).__name__} 은 "
                    "숫자·날짜(ISO 8601)·문자열 중 같은 종류여야 합니다")
            ok = {"<": order < 0, "<=": order <= 0, ">": order > 0, ">=": order >= 0}[op]
        if not ok:
            return False
        cur = right
    return True


class _CompareRewriter(_ast.NodeTransformer):
    """Compare 노드를 한 벌 판정 호출로 바꾼다 — 검증 통과한 원본 트리에만 적용."""

    def visit_Compare(self, node):
        self.generic_visit(node)
        pairs = _ast.List(elts=[
            _ast.Tuple(elts=[_ast.Constant(value=_CMP_OPS[type(op)]), comp],
                       ctx=_ast.Load())
            for op, comp in zip(node.ops, node.comparators)], ctx=_ast.Load())
        return _ast.Call(func=_ast.Name(id=_CMP_NAME, ctx=_ast.Load()),
                         args=[node.left, pairs], keywords=[])


def compile_expr(expr: str) -> Tuple[Any, List[str], List[str]]:
    """(code, 식별자 이름들, col("…") 열 이름들). 허용 밖 구문은 ValueError — 그 이상은 [self:script] 의 자리."""
    tree = _ast.parse(str(expr), mode="eval")
    for n in _ast.walk(tree):
        if not isinstance(n, NODES):
            if isinstance(n, (_ast.In, _ast.NotIn)):
                raise ValueError("허용되지 않는 구문: " + type(n).__name__ +
                                 " — 문자열 포함 검사는 contains(열, 문자열), 부정은 not contains(열, 문자열). "
                                 "목록 소속 검사는 [table:filter]{where:{field:..., op:\"in\", value:[...]}} 로.")
            raise ValueError(f"허용되지 않는 구문: {type(n).__name__} — 한 줄 식과 객체·목록 구성만. "
                             "컴프리헨션·임의 호출·속성 접근은 지원하지 않습니다.")
        if isinstance(n, _ast.Dict) and any(
                not isinstance(k, _ast.Constant) or not isinstance(k.value, str) for k in n.keys):
            raise ValueError("객체 키는 문자열 상수여야 합니다(펼침·동적 키 불가).")
        if isinstance(n, _ast.Dict):
            keys = [k.value for k in n.keys]
            if len(keys) != len(set(keys)):
                raise ValueError("객체에 중복된 키가 있습니다.")
        if isinstance(n, _ast.Call) and not (isinstance(n.func, _ast.Name) and n.func.id in (*FUNCS, "col")):
            raise ValueError("허용 함수: " + ", ".join(sorted(FUNCS)) + ", col")
        if isinstance(n, _ast.Name) and n.id.startswith("__"):
            raise ValueError("금지된 이름")
    names = sorted({n.id for n in _ast.walk(tree) if isinstance(n, _ast.Name)
                    and n.id not in FUNCS and n.id != "col"})
    cols = [str(n.args[0].value) for n in _ast.walk(tree) if isinstance(n, _ast.Call)
            and isinstance(n.func, _ast.Name) and n.func.id == "col" and n.args
            and isinstance(n.args[0], _ast.Constant)]
    # 비교 의미론 위임은 검증 **후** 재작성 — 사용자 식이 _semantic_compare 를 직접
    # 부를 수는 없다(화이트리스트가 원본 트리에서 이미 막았다).
    tree = _ast.fix_missing_locations(_CompareRewriter().visit(tree))
    return compile(tree, "<expr>", "eval"), names, cols


def as_num(v: Any):
    """호환 이름 — 숫자 관측의 뜻은 common.value_semantics 한 벌이다.

    이 자리의 사설 판은 float NaN/Infinity 를 관측으로 통과시켜 compute/reduce 가
    조건·정렬 표면과 다른 수 체계를 살았다(44회차 수리의 사각).
    """
    from common.value_semantics import numeric_value
    return numeric_value(v)


def eval_expr(code: Any, row: Dict[str, Any], extra: Dict[str, Any] = None,
              *, preserve_values: bool = False) -> Any:
    scope = {k: (as_num(v) if not preserve_values and as_num(v) is not None else v) for k, v in row.items()
             if isinstance(k, str) and k.isidentifier() and k != _CMP_NAME}
    if extra:
        scope.update(extra)
    scope["col"] = lambda name: (as_num(row.get(name)) if not preserve_values and as_num(row.get(name)) is not None else row.get(name))
    # 유한 결과 관문 — 1e308*2 같은 오버플로가 Infinity 로 통화에 실려 하류 계산·분기·
    # 저장으로 전염되기 전에 여기서 ValueError 로 끊는다(compute/reduce/assign 공유).
    from common.value_semantics import require_finite_numbers
    return require_finite_numbers(eval(
        code, {"__builtins__": {}, **FUNCS, _CMP_NAME: _semantic_compare}, scope))


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
    # 투영은 복사·재구성이다. "007" 같은 식별자를 숫자로 바꾸지 않는다.
    # 계산할 문자열 숫자는 int/float로 명시 변환한다. compute의 기존 수치 관측은 불변.
    if isinstance(plan, ProjectionExpr):
        return eval_expr(plan.code, row, preserve_values=True)
    if isinstance(plan, dict):
        return {k: eval_projection(v, row) for k, v in plan.items()}
    if isinstance(plan, list):
        return [eval_projection(v, row) for v in plan]
    return plan
