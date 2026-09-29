"""선언-읽기 관문 (2026-09-29, 상상훈련 73회차 B73-2 밭 이관).

질문 하나: **이 액션이 선언한 인자를, 구현은 한 번이라도 읽는가?**

형제 `iblbuild_action_reads`(72회차 B72-2)는 "구현이 읽는 인자 ⊆ 판본 2 허용 집합"을 본다.
이 관문은 그 **반대 방향**이다. 73회차 `[table:chart]{x, y}` 는 선언됐고(판본 2·옛 검사 모두 통과)
코퍼스가 가르쳤지만 핸들러가 한 번도 읽지 않아, 29항목·11시리즈 쓰레기 차트가 success 였다.
72회차 `[self:finance]{category}` 무시(B72-4)도 같은 속이다. 선언된 인자가 조용히 버려지면
모델은 틀린 결과를 성공으로 받는다.

판정은 **흐름을 끝까지 본 액션만** 한다. 역방향은 "읽기 전부"를 알아야 성립하므로, 입력 dict 가
추적할 수 없는 곳(패키지 밖 함수에 통째로·동적 키·반복·반환)으로 새면 그 액션은 판정하지 않고
"판정 불가"로 센다(오탐으로 수리를 강요하지 않는다). 따라가는 흐름:
  · 문자열 키 읽기 `.get/.pop/.setdefault("k")`·`d["k"]`·`"k" in d`
  · 같은 패키지 함수로 넘김(위치·키워드·`**d`·`{**d, …}`), `load_module("모듈").함수(d)` 포함
  · 입력 dict 와 함께 넘긴 문자열 상수(`_arg(ti, "ticker", "symbol")` 별칭 도우미 규약)
  · 단순 별칭 `x = d` · `x = d or {}` · `x = dict(d)` · `x = {**d, …}`
진입점: 디스패처 도구는 `_OP_DISPATCHERS` 의 op 함수(액션 단위), 디스패처 없는 도구는 핸들러
`execute` 의 입력(패키지 단위 합집합 — 더 약하지만 차트 x·y 는 이 층에서 잡힌다).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from iblbuild_action_reads import _Reads, _dispatch_mode, _dispatchers, _module_index
from iblbuild_derive import build_tool_index

# 선언됐지만 핸들러가 아니라 IBL 층이 소비하는 키 — 새 항목은 사유 필수.
DECLARED_UNREAD_ALLOW: dict[str, dict[str, str]] = {
    "self:memory": {
        "keywords": "save 는 자동 선별 정책(실행자 본문 비저장)이라 content 와 함께 의도적으로 버리고 "
                    "saved:false·정책 안내로 정직하게 답한다. 옛 save 문장이 인자 거절 대신 그 안내를 받도록 선언 유지.",
    },
}

# 입력 dict 를 넘겨도 키를 읽지 않는 내장 호출(판정 불가로 떨어뜨리지 않는다).
_INERT_CALLS = {"isinstance", "len", "bool", "type", "id", "print", "repr", "hasattr"}


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def _const(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class _Flow(_Reads):
    """(읽은 키, 흐름 완결 여부)."""

    def __init__(self, mods):
        super().__init__(mods)
        self.flow_memo: dict[tuple[str, str, int | str], tuple[set[str], bool]] = {}
        self.parent_maps = {m: _parents(t) for m, t in mods.items()}
        self.escapes: list[tuple[str, int, str]] = []   # 판정 불가 사유(모듈, 줄, 형태) — 진단용
        # 형제 모듈 적재 별칭(`_office = _load_sibling("office_ops")`)·함수 별칭(`f = _docs.f`)·디스패치 표
        self.mod_alias: dict[str, dict[str, str]] = {}
        self.fn_alias: dict[str, dict[str, tuple[str, str]]] = {}
        self.tables: dict[str, dict[str, ast.Dict]] = {}
        for m, tree in mods.items():
            ma = self.mod_alias.setdefault(m, {})
            for n in ast.walk(tree):
                if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                        and isinstance(n.value, ast.Call)):
                    hit = next((_const(a) for a in n.value.args if _const(a) in mods), None)
                    if hit:
                        ma[n.targets[0].id] = hit
            self.tables[m] = {t.id: n.value for n in tree.body if isinstance(n, ast.Assign)
                              and isinstance(n.value, ast.Dict) for t in n.targets if isinstance(t, ast.Name)}
        for m, tree in mods.items():
            fa = self.fn_alias.setdefault(m, {})
            for n in tree.body:
                if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                        and isinstance(n.value, ast.Attribute) and isinstance(n.value.value, ast.Name)):
                    target = self.mod_alias[m].get(n.value.value.id)
                    if target and n.value.attr in self.funcs.get(target, {}):
                        fa[n.targets[0].id] = (target, n.value.attr)

    def _table_targets(self, mod: str, expr: ast.expr) -> list[tuple[str, str]] | None:
        """`T[k]`·`T[a][b]`·`T.get(k, 기본)`·`T[a].get(k)` — 모듈 수준 디스패치 표의 값 전부."""
        default = None
        if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "get"):
            default = expr.args[1] if len(expr.args) > 1 else None
            expr = expr.func.value
        while isinstance(expr, ast.Subscript):
            expr = expr.value
        if not (isinstance(expr, ast.Name) and expr.id in self.tables[mod]):
            return None
        out: list[tuple[str, str]] = []
        stack = [self.tables[mod][expr.id]] + ([default] if default is not None else [])
        while stack:
            v = stack.pop()
            if isinstance(v, ast.Dict):
                stack.extend(v.values)
            elif isinstance(v, (ast.Name, ast.Attribute)):
                hit = self._resolve_any(mod, v, tables=False)
                if hit is None:
                    return None
                out.append(hit)
            elif not (isinstance(v, ast.Constant) and v.value is None):
                return None
        return out

    def _callees(self, mod: str, func: ast.expr, scope: ast.AST) -> list[tuple[str, str]] | None:
        hit = self._resolve_any(mod, func)
        if hit:
            return [hit]
        via = self._table_targets(mod, func)
        if via is not None:
            return via
        if isinstance(func, ast.Name):                # fn = T.get(op) … fn(d)
            for n in ast.walk(scope):
                if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                        and n.targets[0].id == func.id):
                    via = self._table_targets(mod, n.value)
                    if via is not None:
                        return via
        return None

    def _resolve_any(self, mod: str, func: ast.expr, tables: bool = True) -> tuple[str, str] | None:
        hit = self._resolve(mod, func)
        if hit:
            return hit
        if isinstance(func, ast.Name) and func.id in self.fn_alias.get(mod, {}):
            return self.fn_alias[mod][func.id]
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            target = self.mod_alias.get(mod, {}).get(func.value.id)
            if target and func.attr in self.funcs.get(target, {}):
                return target, func.attr
        # load_module("tool_x").fn(...) · _load("tool_x").fn(...) — 패키지 안 모듈 이름 상수
        if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call) and func.value.args
                and _const(func.value.args[0]) in self.funcs
                and func.attr in self.funcs[_const(func.value.args[0])]):
            return _const(func.value.args[0]), func.attr
        return None

    @staticmethod
    def _keys(expr: ast.expr, parents: dict) -> set[str] | None:
        """상수 키, 또는 상수 튜플·목록을 도는 반복 변수(`for k in ("a", "b"): d.get(k)`)."""
        k = _const(expr)
        if k is not None:
            return {k}
        if isinstance(expr, ast.Name):
            up = parents.get(id(expr))
            while up is not None:
                if (isinstance(up, (ast.For, ast.comprehension)) and isinstance(up.target, ast.Name)
                        and up.target.id == expr.id and isinstance(up.iter, (ast.Tuple, ast.List))
                        and all(_const(e) is not None for e in up.iter.elts)):
                    return {_const(e) for e in up.iter.elts}
                up = parents.get(id(up))
        return None

    def _use(self, mod: str, n: ast.Name, parents: dict) -> tuple[set[str], bool, str]:
        """입력 dict 이름 한 번의 쓰임 → (읽은 키, 흐름 완결, 새는 형태)."""
        p = parents.get(id(n))
        gp = parents.get(id(p)) if p is not None else None
        if isinstance(p, ast.Attribute):
            if p.attr in ("get", "pop", "setdefault") and isinstance(gp, ast.Call) and gp.func is p:
                keys = self._keys(gp.args[0], parents) if gp.args else None
                return (keys, True, "") if keys is not None else (set(), False, "동적 키 .get")
            if p.attr == "update":
                return set(), True, ""
            return set(), False, f".{p.attr}"            # items()/keys()/copy() — 키를 통째로 본다
        if isinstance(p, ast.Subscript) and p.value is n:
            if not isinstance(p.ctx, ast.Load):
                return set(), True, ""
            keys = self._keys(p.slice, parents)
            return (keys, True, "") if keys is not None else (set(), False, "동적 키 []")
        if isinstance(p, ast.Compare) and n in p.comparators:
            k = _const(p.left)
            return ({k}, True, "") if k is not None else (set(), False, "동적 in")
        if isinstance(p, (ast.Assign, ast.BoolOp, ast.If, ast.IfExp, ast.UnaryOp, ast.Compare)):
            return set(), True, ""                      # 별칭(위에서 닫음)·진리값 검사
        if isinstance(p, ast.Dict):
            if not isinstance(gp, ast.Call):
                return set(), isinstance(gp, ast.Assign), "{**d} 값"
            call, arg = gp, p
        elif isinstance(p, ast.Call) and p.func is not n:
            call, arg = p, n
        elif isinstance(p, ast.keyword):
            call, arg = gp, p
        elif isinstance(p, (ast.Return, ast.Yield, ast.For, ast.comprehension, ast.JoinedStr,
                            ast.FormattedValue, ast.List, ast.Tuple, ast.Starred)):
            return set(), False, type(p).__name__
        else:
            return set(), True, ""
        if isinstance(call.func, ast.Name) and call.func.id in _INERT_CALLS:
            return set(), True, ""
        if (isinstance(call.func, ast.Name) and call.func.id == "dict" and len(call.args) == 1
                and isinstance(parents.get(id(call)), ast.Assign)):
            return set(), True, ""                      # d2 = dict(d) — 별칭(위에서 닫음)
        consts = {c for c in (_const(a) for a in call.args) if c and not c.startswith("_")}
        scope = parents.get(id(call))
        while scope is not None and not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = parents.get(id(scope))
        targets = self._callees(mod, call.func, scope if scope is not None else call)
        if not targets:
            return consts, False, f"패키지 밖 호출 {ast.unparse(call.func)[:40]}"
        reads, complete = set(consts), True
        for target in targets:
            tf = self.funcs[target[0]][target[1]]
            tparams = [a.arg for a in list(tf.args.posonlyargs) + list(tf.args.args)]
            if isinstance(arg, ast.keyword):
                if arg.arg is None:
                    got, ok = self.flow(target[0], target[1], "**")
                elif arg.arg in tparams:
                    got, ok = self.flow(target[0], target[1], tparams.index(arg.arg))
                else:
                    got, ok = set(), False
            else:
                got, ok = self.flow(target[0], target[1], call.args.index(arg))
            reads |= got
            complete &= ok
        return reads, complete, "" if complete else f"→ {ast.unparse(call.func)[:40]}"

    def flow(self, mod: str, fname: str, index: int | str) -> tuple[set[str], bool]:
        """index=정수(위치 인자) · "**"(키워드 전개로 받음)."""
        key = (mod, fname, index)
        if key in self.flow_memo:
            return self.flow_memo[key]
        self.flow_memo[key] = (set(), True)       # 재귀 차단
        f = self.funcs[mod][fname]
        params = [a.arg for a in list(f.args.posonlyargs) + list(f.args.args)]
        if index == "**":
            reads = {a for a in params + [a.arg for a in f.args.kwonlyargs]} - {"self", "cls"}
            names = {f.args.kwarg.arg} if f.args.kwarg else set()
        else:
            if index >= len(params):
                self.flow_memo[key] = (set(), True)
                return self.flow_memo[key]
            reads, names = set(), {params[index]}
        complete = True
        parents = self.parent_maps[mod]
        # 별칭 닫힘: x = d · x = d or {} · x = dict(d) · x = {**d, ...}
        changed = True
        while changed:
            changed = False
            for n in ast.walk(f):
                if not (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)):
                    continue
                v, target = n.value, n.targets[0].id
                src = (isinstance(v, ast.Name) and v.id in names
                       or isinstance(v, ast.BoolOp) and any(isinstance(x, ast.Name) and x.id in names for x in v.values)
                       or isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "dict"
                       and len(v.args) == 1 and isinstance(v.args[0], ast.Name) and v.args[0].id in names
                       or isinstance(v, ast.Dict) and any(k is None and isinstance(x, ast.Name) and x.id in names
                                                          for k, x in zip(v.keys, v.values)))
                if src and target not in names:
                    names.add(target)
                    changed = True
        for n in ast.walk(f):
            if isinstance(n, ast.Name) and n.id in names and isinstance(n.ctx, ast.Load):
                got, ok, why = self._use(mod, n, parents)
                reads |= got
                if not ok:
                    complete = False
                    self.escapes.append((f"{mod}.{fname}", n.lineno, why))
        out = ({k for k in reads if k and not k.startswith("_")}, complete)
        self.flow_memo[key] = out
        return out


def _entry(tree: ast.Module) -> str | None:
    for name in ("execute", "execute_tool", "_execute"):
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name for n in tree.body):
            return name
    return None


def validate_declared_reads(data: dict, root: Path,
                            allow: dict[str, dict[str, str]] | None = None) -> tuple[list[str], dict]:
    """(issues, 통계). 선언 params 중 흐름이 완결된 구현이 한 번도 읽지 않는 키 = 오류."""
    allow = DECLARED_UNREAD_ALLOW if allow is None else allow
    tool_index = build_tool_index(root)
    flows: dict[Path, tuple[_Flow, dict, tuple, str | None]] = {}
    issues: list[str] = []
    stats = {"checked": 0, "undecidable": 0}
    for node_name, node in sorted((data.get("nodes", {}) or {}).items()):
        for aname, cfg in sorted(((node or {}).get("actions", {}) or {}).items()):
            if not (isinstance(cfg, dict) and cfg.get("router") == "handler" and cfg.get("tool")):
                continue
            declared = set(cfg.get("params") or {})
            if not declared or cfg["tool"] not in tool_index:
                continue
            pkg_dir, _ = tool_index[cfg["tool"]]
            if pkg_dir not in flows:
                mods = _module_index(pkg_dir)
                h = mods.get("handler")
                flows[pkg_dir] = (_Flow(mods), _dispatchers(h) if h else {},
                                  _dispatch_mode(h) if h else ("pos", 0), _entry(h) if h else None)
            fl, disp, mode, entry = flows[pkg_dir]
            ops = disp.get(cfg["tool"])
            got, complete = set(), True
            if ops:
                exposed = set((cfg.get("ops") or {}).get("values") or ops)
                for op, fname in ops.items():
                    if op not in exposed:
                        continue
                    if fname not in fl.funcs["handler"]:
                        complete = False          # 다른 모듈에서 대입된 op 함수 — 흐름을 못 본다
                        continue
                    r, ok = fl.flow("handler", fname, "**" if mode[0] == "kw" else mode[1])
                    got |= r
                    complete &= ok
                if entry:
                    # 디스패치 전 공통 전처리(site_id 해소·path 있는 파일 갈래 등)도 그 액션의 읽기다.
                    # 진입점은 op 함수를 동적으로 부르므로 완결성은 op 함수 쪽으로만 판정한다.
                    got |= fl.flow("handler", entry, 0)[0]
            elif entry:
                got, complete = fl.flow("handler", entry, 0)
            else:
                complete = False
            if not complete:
                stats["undecidable"] += 1
                continue
            stats["checked"] += 1
            excused = allow.get(f"{node_name}:{aname}", {})
            missing = sorted(declared - got - set(excused))
            if missing:
                issues.append(
                    f"[{node_name}:{aname}] ({pkg_dir.name}): 선언된 인자 {missing} 를 구현이 한 번도 읽지 않는다 — "
                    f"판본 2 가 받아 주고 결과는 그 인자를 무시한 채 성공한다. 구현하거나, 은퇴 낱말이면 "
                    f"선언에서 빼고 retired_contracts 에 등록할 것(IBL 층이 소비하는 키면 DECLARED_UNREAD_ALLOW 에 사유와 함께)")
    return issues, stats


if __name__ == "__main__":
    import yaml
    ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    nodes = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    found, st = validate_declared_reads(nodes, ROOT)
    for line in found:
        print(line)
    print(f"{len(found)}건 · 판정 {st['checked']} · 판정 불가 {st['undecidable']}")
