"""표시 칸 접기 관문 (2026-09-29, 상상훈련 76회차 F76-1·77회차 F77-1 밭 이관).

질문 하나 — 행의 표시 칸(`meta`·`summary`)에 접어 넣은 값이 **같은 행의 구조 칸에도** 있는가?
  77회차: 논문 5원천의 저자·연도·학술지·인용수, 국립중앙도서관의 저자·출판사·연도, 강의 목록의
  lecture_id, 노트북 소스의 stale 이 `" · ".join` 한 표시 문자열에만 있어, 연도순 정렬·저자 필터·
  ID 연결·stale 점검이 `split($x.meta," · ")[1]` 문자열 쪼개기가 됐다(T20 은 구조적으로 항상 0).
  76회차: 네이버 매물의 면적·층·거래유형이 meta 에만 있었다. 칸 규약(R7) — 표시 칸은 사람이 읽는
  요약이고, 프로그램이 쓸 값은 구조 칸이 정본이다.

판정: 패키지 .py 의 dict 리터럴(및 `변수["meta"] = …`)에서 표시 칸 값을 이루는 **조각**을 뽑는다
(`sep.join([...])`·`sep.join(x for x in [...] if x)`·목록 변수의 append·f-문자열·문자열 +).
조각마다 **데이터 뿌리**를 구한다 — `r.get("year")`·`r["year"]` 은 (r, year), 함수 안 대입은 따라가고
(`year = r.get("YR")` → (r, YR)), 호출·서식은 인자로 내려간다. 같은 dict 의 다른 칸(같은 함수에서
그 변수에 나중에 넣는 `rec["k"] = …`·`rec.update({...})` 포함)이 그 뿌리 하나라도 공유하면 보존된 것이다.
상수 조각(구분자·고정 문구)은 뿌리가 없어 대상 밖이다.

하한 관문이다: 함수 경계 밖의 대입·동적 조립은 따라가지 않는다. 검토한 예외는 `ALLOW` 에 사유와 함께.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

DISPLAY_KEYS = ("meta", "summary")

# 검토한 예외 — 키 = "패키지/파일.py:함수", 값 = 사유(필수). 새 항목은 "왜 구조 칸이 필요 없는가"를 적는다.
ALLOW: dict[str, str] = {}


def _const_key(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class _Scope:
    """한 함수의 대입 기록 — 이름 → 대입된 식들(append/extend/+= 포함)."""

    def __init__(self, fn):
        self.assign: dict[str, list] = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    self._bind(t, node.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
                self._bind(node.target, node.value)
            elif isinstance(node, (ast.For, ast.comprehension)):
                self._bind(node.target, node.iter)
            elif isinstance(node, ast.NamedExpr):
                self._bind(node.target, node.value)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and isinstance(node.func.value, ast.Name)
                  and node.func.attr in ("append", "extend", "insert") and node.args):
                self.assign.setdefault(node.func.value.id, []).append(node.args[-1])

    def _bind(self, target, value):
        if isinstance(target, ast.Name):
            self.assign.setdefault(target.id, []).append(value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind(elt, value)


def _roots(expr, scope: _Scope, seen=None, depth=0) -> set:
    """식의 데이터 뿌리 집합 — 상수 키 경로("journal.title") 또는 풀리지 않은 맨 이름("$x").

    기저 이름은 버린다 — 같은 원천 행이 함수 안에서 여러 별칭(r·row·it)으로 불려도 키 경로는 같다."""
    if seen is None:
        seen = frozenset()
    out: set = set()
    if expr is None or depth > 12 or isinstance(expr, ast.Constant):
        return out
    if isinstance(expr, ast.Name):
        values = scope.assign.get(expr.id)
        if not values or expr.id in seen:
            return {f"${expr.id}"} if not values else out
        for v in values:
            out |= _roots(v, scope, seen | {expr.id}, depth + 1)
        return out or {f"${expr.id}"}
    # r.get("k") · r["k"] → 기저 경로 + k
    key, base = None, None
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "get"
            and expr.args and _const_key(expr.args[0]) is not None):
        key, base = _const_key(expr.args[0]), expr.func.value
    elif isinstance(expr, ast.Subscript) and _const_key(expr.slice) is not None:
        key, base = _const_key(expr.slice), expr.value
    if base is not None:
        inner = {r for r in _roots(base, scope, seen, depth + 1) if not r.startswith("$")}
        return {f"{r}.{key}" for r in inner} | {key}
    if isinstance(expr, ast.Call):
        # 함수 이름은 값이 아니다 — 메서드면 받는 쪽(x.strip() 의 x)과 인자만.
        children = list(expr.args) + [k.value for k in expr.keywords]
        if isinstance(expr.func, ast.Attribute):
            children.append(expr.func.value)
    elif isinstance(expr, ast.IfExp):
        children = [expr.body, expr.orelse]          # 조건은 값이 아니다
    elif isinstance(expr, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        children = [expr.elt] + [g.iter for g in expr.generators]
    else:
        children = [c for c in ast.iter_child_nodes(expr) if isinstance(c, ast.expr)]
    for child in children:
        out |= _roots(child, scope, seen, depth + 1)
    return out


def _shares(roots: set, covered: set) -> bool:
    """키 경로가 같거나 한쪽이 다른 쪽의 꼬리(별칭 해소 깊이 차이)면 같은 값이다."""
    for r in roots:
        for c in covered:
            if r == c or (not r.startswith("$") and not c.startswith("$")
                          and (r.endswith("." + c) or c.endswith("." + r))):
                return True
    return False


def _parts(expr, scope: _Scope, depth=0) -> list:
    """표시 칸 값을 이루는 조각 식들."""
    if expr is None or depth > 6:
        return []
    if isinstance(expr, ast.Constant):
        return []
    if isinstance(expr, ast.JoinedStr):
        return [v.value for v in expr.values if isinstance(v, ast.FormattedValue)]
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        return _parts(expr.left, scope, depth + 1) + _parts(expr.right, scope, depth + 1)
    if isinstance(expr, ast.IfExp):
        return _parts(expr.body, scope, depth + 1) + _parts(expr.orelse, scope, depth + 1)
    if isinstance(expr, ast.BoolOp):
        out = []
        for v in expr.values:
            out += _parts(v, scope, depth + 1)
        return out
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "join"
            and isinstance(expr.func.value, ast.Constant) and expr.args):
        return _seq_parts(expr.args[0], scope, depth + 1)
    if isinstance(expr, ast.Name):
        out = []
        for v in scope.assign.get(expr.id, []):
            out += _parts(v, scope, depth + 1) or [v]
        return out
    return [expr]


def _seq_parts(seq, scope: _Scope, depth) -> list:
    if isinstance(seq, (ast.List, ast.Tuple)):
        out = []
        for e in seq.elts:
            out += _parts(e, scope, depth + 1) or ([] if isinstance(e, ast.Constant) else [e])
        return out
    if isinstance(seq, (ast.GeneratorExp, ast.ListComp)) and seq.generators:
        gen = seq.generators[0]
        if isinstance(seq.elt, ast.Name) and isinstance(gen.target, ast.Name) and seq.elt.id == gen.target.id:
            return _seq_parts(gen.iter, scope, depth + 1)
        return [seq]
    if isinstance(seq, ast.Call) and isinstance(seq.func, ast.Name) and seq.func.id == "filter" and len(seq.args) == 2:
        return _seq_parts(seq.args[1], scope, depth + 1)
    if isinstance(seq, ast.Name):
        out = []
        for v in scope.assign.get(seq.id, []):
            if isinstance(v, (ast.List, ast.Tuple, ast.GeneratorExp, ast.ListComp)):
                out += _seq_parts(v, scope, depth + 1)
            else:  # append(e) 조각
                out += _parts(v, scope, depth + 1) or ([] if isinstance(v, ast.Constant) else [v])
        return out
    return [seq]


def _later_values(fn, var: str) -> list:
    """같은 함수에서 변수 var 에 나중에 넣는 칸 값들 — rec["k"] = v · rec.update({...}) · rec.setdefault(k, v)."""
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == var
                        and _const_key(t.slice) not in DISPLAY_KEYS):
                    out.append(node.value)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and isinstance(node.func.value, ast.Name) and node.func.value.id == var):
            if node.func.attr == "update" and node.args and isinstance(node.args[0], ast.Dict):
                out += [v for k, v in zip(node.args[0].keys, node.args[0].values) if _const_key(k) not in DISPLAY_KEYS]
            elif node.func.attr == "setdefault" and len(node.args) == 2:
                out.append(node.args[1])
    return out


def _dict_owner(fn, dict_node) -> str | None:
    """dict 리터럴이 대입된 변수 이름(rec = {...})."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and node.value is dict_node:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    return t.id
    return None


def _functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _is_composition(expr, scope: _Scope, depth=0) -> bool:
    """여러 값을 한 문자열로 **합성**하는가 — join·f-문자열·문자열 +. 한 값의 투영(본문 그대로·자르기)은 접기가 아니다."""
    if depth > 4:
        return False
    if isinstance(expr, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in expr.values)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        return True
    if isinstance(expr, ast.IfExp):
        return _is_composition(expr.body, scope, depth + 1) or _is_composition(expr.orelse, scope, depth + 1)
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "join"
            and isinstance(expr.func.value, ast.Constant)):
        return True
    if isinstance(expr, ast.Name):
        return any(_is_composition(v, scope, depth + 1) for v in scope.assign.get(expr.id, []))
    return False


def _spread_read(part, spreads: set) -> bool:
    """`{**it, "meta": … it.get("k") …}` — 펼친 원천 행의 칸을 읽는 조각은 같은 행에 이미 실려 있다."""
    base = None
    if (isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute) and part.func.attr == "get"
            and part.args and _const_key(part.args[0]) is not None):
        base = part.func.value
    elif isinstance(part, ast.Subscript) and _const_key(part.slice) is not None:
        base = part.value
    return isinstance(base, ast.Name) and base.id in spreads


def _uncovered(display_expr, others: list, scope: _Scope, spreads: set = frozenset()) -> list[str]:
    covered: set = set()
    for v in others:
        covered |= _roots(v, scope)
    missing = []
    for part in _parts(display_expr, scope):
        if _spread_read(part, spreads):
            continue
        roots = _roots(part, scope)
        if roots and not _shares(roots, covered):
            missing.append(ast.unparse(part)[:60])
    return missing


def scan_file(path: Path, rel: str) -> list[tuple[int, str, str, list[str]]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    hits, seen = [], set()
    for fn in _functions(tree):
        scope = _Scope(fn)
        for node in ast.walk(fn):
            if not isinstance(node, ast.Dict) or id(node) in seen:
                continue
            keys = [_const_key(k) for k in node.keys]
            # 기록 행(카드 관습 title/meta/summary/url)만 — 봉투의 요약 문구는 행이 아니다.
            if "title" not in keys or not any(k in DISPLAY_KEYS for k in keys):
                continue
            seen.add(id(node))
            owner = _dict_owner(fn, node)
            base_others = [v for k, v in zip(keys, node.values) if k not in DISPLAY_KEYS and k is not None]
            spreads = {v.id for k, v in zip(node.keys, node.values) if k is None and isinstance(v, ast.Name)}
            if owner:
                base_others += _later_values(fn, owner)
            for k, v in zip(keys, node.values):
                if k not in DISPLAY_KEYS or not _is_composition(v, scope):
                    continue
                missing = _uncovered(v, base_others, scope, spreads)
                if missing:
                    hits.append((node.lineno, fn.name, k, missing))
    return hits


def validate_meta_fields(root: Path) -> tuple[list[str], int]:
    tools = root / "data" / "packages" / "installed" / "tools"
    issues, sites = [], 0
    for path in sorted(tools.rglob("*.py")):
        if "__pycache__" in path.parts or path.name.startswith("test_"):
            continue
        rel = str(path.relative_to(tools))
        for line, fn, key, missing in scan_file(path, rel):
            sites += 1
            if f"{rel}:{fn}" in ALLOW:
                continue
            issues.append(f"{rel}:{line} ({fn}) `{key}` 에만 접힌 값: {', '.join(missing)} "
                          f"— 같은 행의 구조 칸에도 싣거나(R7 칸 규약) ALLOW 에 사유를 적으세요")
    return issues, sites


def _self_test():
    import tempfile
    src = '''
def good(r):
    year = r.get("YR")
    rec = {"title": r["T"], "year": year, "meta": " · ".join(x for x in [r.get("A"), year] if x)}
    rec["authors"] = r.get("A")
    return rec

def bad(r):
    return {"title": r["T"], "meta": " · ".join(x for x in [r.get("A"), r.get("YR")] if x)}

def spread(it):
    return {**it, "title": it["t"], "meta": " · ".join(x for x in [it.get("org"), it.get("tbl")] if x)}

def fstr(w):
    c = w.get("cited_by_count")
    return {"title": w["t"], "meta": f"인용 {c:,}", "citations": c}
'''
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.py"
        p.write_text(src)
        hits = scan_file(p, "m.py")
    assert [(h[1], h[3]) for h in hits] == [("bad", ["r.get('A')", "r.get('YR')"])], hits
    print("self-test ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
        sys.exit(0)
    root = Path(__file__).resolve().parents[1]
    issues, sites = validate_meta_fields(root)
    for i in issues:
        print(" ", i)
    print(f"표시 칸 접기: {len(issues)}건 (예외 포함 적발 {sites}자리)")
    sys.exit(1 if issues else 0)
