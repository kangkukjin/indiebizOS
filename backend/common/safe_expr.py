"""safe_expr.py — 한 줄 식 평가기(ast 화이트리스트) — [table:reduce] 의 step 식 (2026-08-22 M5).

data-ops `[table:compute]` 의 `_compute_compile` 과 같은 화이트리스트·같은 함수 집합. 패키지 핸들러를
엔진 층이 import 하면 층 역전이라 공용 층(common)에 한 벌 더 둔다 — 허용 목록이 갈라지지 않게
두 자리 모두 이 파일의 상수를 정본으로 본다 — compute(data-ops) 는 2026-08-22 정리로 이쪽을 import 해 재수출한다(화이트리스트 단일 소스).
"""
import ast as _ast
import math as _math
from typing import Any, Dict, List, Tuple

FUNCS: Dict[str, Any] = {"round": round, "abs": abs, "min": min, "max": max, "int": int,
                         "float": float, "len": len, "str": str, "sqrt": _math.sqrt, "log": _math.log}
NODES = (_ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Constant, _ast.Name, _ast.Load,
         _ast.Call, _ast.Compare, _ast.BoolOp, _ast.IfExp, _ast.Subscript, _ast.Tuple,
         _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.FloorDiv, _ast.Mod, _ast.Pow,
         _ast.USub, _ast.UAdd, _ast.Not, _ast.And, _ast.Or,
         _ast.Eq, _ast.NotEq, _ast.Lt, _ast.LtE, _ast.Gt, _ast.GtE)


def compile_expr(expr: str) -> Tuple[Any, List[str], List[str]]:
    """(code, 식별자 이름들, col("…") 열 이름들). 허용 밖 구문은 ValueError — 그 이상은 [self:script] 의 자리."""
    tree = _ast.parse(str(expr), mode="eval")
    for n in _ast.walk(tree):
        if not isinstance(n, NODES):
            raise ValueError(f"허용되지 않는 구문: {type(n).__name__} — 한 줄 산술·비교·조건식만. "
                             "상태가 dict 이거나 분기가 섞이면 [self:script] 로.")
        if isinstance(n, _ast.Call) and not (isinstance(n.func, _ast.Name) and n.func.id in (*FUNCS, "col")):
            raise ValueError("허용 함수: " + ", ".join(sorted(FUNCS)) + ", col")
        if isinstance(n, _ast.Name) and n.id.startswith("__"):
            raise ValueError("금지된 이름")
    names = sorted({n.id for n in _ast.walk(tree) if isinstance(n, _ast.Name)
                    and n.id not in FUNCS and n.id != "col"})
    cols = [str(n.args[0].value) for n in _ast.walk(tree) if isinstance(n, _ast.Call)
            and isinstance(n.func, _ast.Name) and n.func.id == "col" and n.args
            and isinstance(n.args[0], _ast.Constant)]
    return compile(tree, "<expr>", "eval"), names, cols


def as_num(v: Any):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s.endswith("%"):
            s = s[:-1]
        try:
            return float(s) if ("." in s or "e" in s.lower()) else int(s)
        except ValueError:
            return None
    return None


def eval_expr(code: Any, row: Dict[str, Any], extra: Dict[str, Any] = None) -> Any:
    scope = {k: (as_num(v) if as_num(v) is not None else v) for k, v in row.items()
             if isinstance(k, str) and k.isidentifier()}
    if extra:
        scope.update(extra)
    scope["col"] = lambda name: (as_num(row.get(name)) if as_num(row.get(name)) is not None else row.get(name))
    return eval(code, {"__builtins__": {}, **FUNCS}, scope)
