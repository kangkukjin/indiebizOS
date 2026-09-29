"""액션별 구현-읽기 관문 (2026-09-29, 상상훈련 72회차 B72-2 밭 이관).

질문 하나: **이 액션의 구현이 읽는 인자를, 판본 2 실행 관문은 받아 주는가?**

왜 새 검사인가 — 형제 `validate_impl_reads`(08-29)가 같은 질문을 이미 물었는데 72회차의
`[self:finance]{counterparty, date}` 거절(UNKNOWN_ARGUMENT)을 못 잡았다. 사각지대가 두 겹이었다.
  ① **입력을 변수 이름으로 알아봤다**(`tool_input`/`ti`). `input_data`(finance·health)·
     `params`(음악·사진·게시판 등)로 받는 핸들러는 통째로 안 보였다.
  ② **패키지 합집합으로 판정했다**. 실행 관문(`ibl_param_vocab.allowed_param_keys`)은 그 액션
     도구의 선언으로 거절하는데, 빌드 관문은 패키지 전체 선언으로 재어 두 층이 같은 질문에
     다른 답을 냈다(09-18 검사기 조이기 이후 이 어긋남이 곧 실행 거절이 됐다).

그래서 이름이 아니라 **흐름**을 따른다: `_OP_DISPATCHERS[도구][op]` 함수의 첫 인자에서 출발해,
그 dict 가 같은 패키지 안의 함수로 넘어가면(위치·키워드 인자) 그 함수의 해당 인자까지 따라가며
문자열 키 읽기(`.get`·`.pop`·`[...]` Load·`"k" in d`)를 모은다. 허용 집합은 실행 관문과 **같은 함수**
`allowed_param_keys` 에 빌드의 스키마 스냅숏을 넘겨 계산한다(판정 기준 사본 없음).

범위(하한): dict 를 다른 이름에 다시 담거나(`d = dict(tool_input)`) 패키지 밖으로 넘긴 뒤의 읽기는
따라가지 않는다. `_` 접두 키는 배관이다. 함수층 배관은 형제 관문의 `IMPL_READ_ALLOW`(사유 필수)를 공유한다.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from iblbuild_derive import build_tool_index


def _module_index(pkg_dir: Path) -> dict[str, ast.Module]:
    mods: dict[str, ast.Module] = {}
    for py in sorted(pkg_dir.glob("*.py")):
        try:
            mods[py.stem] = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
    return mods


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _imports(tree: ast.Module, local: set[str]) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """패키지 안 모듈에서 가져온 이름: {별칭: (모듈, 함수)} · {모듈 별칭: 모듈}. 함수 안 import 포함."""
    names: dict[str, tuple[str, str]] = {}
    modules: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[-1] in local:
            for a in n.names:
                names[a.asname or a.name] = (n.module.split(".")[-1], a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[-1] in local:
                    modules[a.asname or a.name] = a.name.split(".")[-1]
    return names, modules


class _Reads:
    def __init__(self, mods: dict[str, ast.Module]):
        self.mods = mods
        self.funcs = {m: _functions(t) for m, t in mods.items()}
        self.imps = {m: _imports(t, set(mods)) for m, t in mods.items()}
        self.memo: dict[tuple[str, str, int], set[str]] = {}

    def _resolve(self, mod: str, func: ast.expr) -> tuple[str, str] | None:
        names, modules = self.imps[mod]
        if isinstance(func, ast.Name):
            if func.id in self.funcs[mod]:
                return mod, func.id
            if func.id in names and names[func.id][1] in self.funcs.get(names[func.id][0], {}):
                return names[func.id]
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            target = modules.get(func.value.id)
            if target and func.attr in self.funcs.get(target, {}):
                return target, func.attr
        return None

    def of_kwargs(self, mod: str, fname: str) -> set[str]:
        """`fn(**입력)` 규약: 이름 있는 인자 전부 + `**kwargs` dict 에서 읽는 키."""
        f = self.funcs[mod][fname]
        a = f.args
        out = {x.arg for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)} - {"self", "cls"}
        if a.kwarg is not None:
            name = a.kwarg.arg
            for n in ast.walk(f):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr in ("get", "pop") and isinstance(n.func.value, ast.Name)
                        and n.func.value.id == name and n.args and isinstance(n.args[0], ast.Constant)
                        and isinstance(n.args[0].value, str)):
                    out.add(n.args[0].value)
        return {k for k in out if not k.startswith("_")}

    @staticmethod
    def _keys_of(expr: ast.expr, loops: dict[str, set[str]]) -> set[str]:
        """키 자리의 식 → 문자열 키들: 리터럴이면 그 하나, 리터럴 튜플을 도는 루프 변수면 튜플 전부."""
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return {expr.value}
        if isinstance(expr, ast.Name):
            return loops.get(expr.id, set())
        return set()

    def _key_loops(self, mod: str, f: ast.AST) -> dict[str, set[str]]:
        """`for k in ("a", "b"): … d[k]` 규약 — 루프 변수 → 도는 문자열 리터럴 집합 (2026-09-29, 78회차 F78-3).

        건강 save 가 최상위 평탄 키(systolic·diastolic …)를 튜플을 돌며 읽어, 리터럴 키만 보던 이 관문이
        그 읽기를 못 봤다 — 가이드가 가르치는 `systolic` 이 판본 2 에서 UNKNOWN_ARGUMENT 였다.
        튜플은 루프 자리의 리터럴이거나, 같은 함수·모듈에서 리터럴로 한 번 묶인 이름이다."""
        def literal(node):
            if isinstance(node, (ast.Tuple, ast.List, ast.Set)) and node.elts and all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
                return {e.value for e in node.elts}
            return None
        named: dict[str, set[str]] = {}
        for scope in (self.mods[mod], f):
            for n in ast.walk(scope):
                if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                    keys = literal(n.value)
                    if keys:
                        named[n.targets[0].id] = keys
        loops: dict[str, set[str]] = {}
        for n in ast.walk(f):
            if isinstance(n, (ast.For, ast.comprehension)) and isinstance(n.target, ast.Name):
                keys = literal(n.iter) or (named.get(n.iter.id) if isinstance(n.iter, ast.Name) else None)
                if keys:
                    loops[n.target.id] = loops.get(n.target.id, set()) | keys
        return loops

    def of(self, mod: str, fname: str, index: int) -> set[str]:
        key = (mod, fname, index)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = set()                    # 재귀 차단
        f = self.funcs[mod][fname]
        params = list(f.args.posonlyargs) + list(f.args.args)
        if index >= len(params):
            return set()
        name = params[index].arg
        out: set[str] = set()
        loops = self._key_loops(mod, f)
        for n in ast.walk(f):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("get", "pop") and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == name and n.args):
                out |= self._keys_of(n.args[0], loops)
            elif (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == name
                    and isinstance(n.ctx, ast.Load)):
                out |= self._keys_of(n.slice, loops)
            elif (isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.In)
                    and isinstance(n.comparators[0], ast.Name) and n.comparators[0].id == name):
                out |= self._keys_of(n.left, loops)
            if isinstance(n, ast.Call):
                target = self._resolve(mod, n.func)
                if target is None:
                    continue
                tparams = [a.arg for a in list(self.funcs[target[0]][target[1]].args.posonlyargs)
                           + list(self.funcs[target[0]][target[1]].args.args)]
                for i, arg in enumerate(n.args):
                    if isinstance(arg, ast.Name) and arg.id == name:
                        out |= self.of(target[0], target[1], i)
                for kw in n.keywords:
                    if (kw.arg and isinstance(kw.value, ast.Name) and kw.value.id == name
                            and kw.arg in tparams):
                        out |= self.of(target[0], target[1], tparams.index(kw.arg))
        out = {k for k in out if k and not k.startswith("_")}
        self.memo[key] = out
        return out


def _dispatch_mode(tree: ast.Module):
    """디스패처가 op 함수에 입력을 넘기는 규약: ("pos", i) 또는 ("kw", None).

    `fn = _OP_DISPATCHERS[...]...` 로 묶인 이름의 호출 자리를 읽는다 — `fn(tool_input)`·
    `fn(bm, ti)`(business)·`fn({**tool_input, ...})`(system_essentials)·`func(**valid)`(cctv).
    """
    bound: set[str] = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "_OP_DISPATCHERS"
                                              for x in ast.walk(n.value))):
            bound |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in bound:
            if any(kw.arg is None for kw in n.keywords):
                return ("kw", None)
            for i, arg in enumerate(n.args):
                if isinstance(arg, ast.Dict) or (isinstance(arg, ast.Name) and arg.id not in ("context", "ctx", "bm", "core")):
                    return ("pos", i)
    return ("pos", 0)


def _dispatchers(tree: ast.Module) -> dict[str, dict[str, str]]:
    for node in tree.body:
        if (isinstance(node, (ast.Assign, ast.AnnAssign))
                and any(isinstance(t, ast.Name) and t.id == "_OP_DISPATCHERS"
                        for t in (node.targets if isinstance(node, ast.Assign) else [node.target]))
                and isinstance(node.value, ast.Dict)):
            out: dict[str, dict[str, str]] = {}
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Dict):
                    out[k.value] = {ok.value: fv.id for ok, fv in zip(v.keys, v.values)
                                    if isinstance(ok, ast.Constant) and isinstance(fv, ast.Name)}
            return out
    return {}


def validate_action_reads(data: dict, root: Path, allow: dict[str, set[str]] | None = None) -> list[str]:
    backend = Path(__file__).resolve().parents[1] / "backend"   # 판정 함수는 이 저장소의 실행 관문
    for sub in ("", "ibl", "base", "common"):
        p = str(backend / sub) if sub else str(backend)
        if p not in sys.path:
            sys.path.insert(0, p)
    from ibl_param_vocab import allowed_param_keys

    allow = allow or {}
    tool_index = build_tool_index(root)
    by_tool: dict[str, list[tuple[str, str, dict]]] = {}
    for node_name, node in (data.get("nodes", {}) or {}).items():
        for aname, cfg in ((node or {}).get("actions", {}) or {}).items():
            if isinstance(cfg, dict) and cfg.get("router") == "handler" and cfg.get("tool"):
                by_tool.setdefault(cfg["tool"], []).append((node_name, aname, cfg))

    issues: list[str] = []
    readers: dict[Path, tuple[_Reads, dict]] = {}
    for tool, actions in sorted(by_tool.items()):
        if tool not in tool_index:
            continue
        pkg_dir, tdef = tool_index[tool]
        if pkg_dir not in readers:
            mods = _module_index(pkg_dir)
            h = mods.get("handler")
            readers[pkg_dir] = (_Reads(mods), _dispatchers(h) if h else {}, _dispatch_mode(h) if h else ("pos", 0))
        reads, disp, mode = readers[pkg_dir]
        ops = disp.get(tool)
        if not ops:
            continue                              # 디스패처 없는 도구 = 형제 관문(패키지 단위)의 몫
        schema = ((tdef.get("input_schema") or {}).get("properties")) or {}
        for node_name, aname, cfg in actions:
            allowed = allowed_param_keys(node_name, aname, cfg, schema_keys=schema)
            if allowed is None:
                continue                          # open_params 등 — 실행 관문도 검사하지 않는다
            exposed = set((cfg.get("ops") or {}).get("values") or ops)
            allowed = allowed | allow.get(pkg_dir.name, set())
            for op, fname in sorted(ops.items()):
                if op not in exposed or fname not in reads.funcs["handler"]:
                    continue
                got = reads.of_kwargs("handler", fname) if mode[0] == "kw" else reads.of("handler", fname, mode[1])
                missing = sorted(got - allowed)
                if missing:
                    issues.append(
                        f"[{node_name}:{aname}]{{op:\"{op}\"}} ({pkg_dir.name}/{fname}): 구현이 읽는 인자 {missing} 가 "
                        f"선언에 없어 판본 2 실행 관문이 UNKNOWN_ARGUMENT 로 거절한다 — ibl_actions.yaml 의 "
                        f"params 에 타입을 선언하거나, 옛 이름 폴백이면 aliases 로 정본에 묶을 것"
                        f"(함수층 배관이면 IMPL_READ_ALLOW 에 사유와 함께)")
    return issues


if __name__ == "__main__":
    import yaml
    ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from iblbuild_params_check import IMPL_READ_ALLOW
    nodes = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    found = validate_action_reads(nodes, ROOT, IMPL_READ_ALLOW)
    for line in found:
        print(line)
    print(f"{len(found)}건")
