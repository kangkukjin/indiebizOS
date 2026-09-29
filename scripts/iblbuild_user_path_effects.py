"""사용자 경로 효과 관문 (2026-09-29, 상상훈련 74회차 B74-1·B74-2 밭 이관).

질문 둘 — 입력으로 받은 **경로 값**이 파일시스템 효과 원시에 닿는 자리를 본다.
  규칙 1(B74-2): 판본 2 가 **읽기**로 계약한 op 가 사용자 위치에 쓰거나 지우는가?
      `[self:read]` 가 pptx 원본 옆에 `<stem>_images/` 를 만들고(읽기 전용 폴더에선 읽기 자체가 실패),
      B72-5 는 없는 주체 조회가 행을 넣었다. 읽기 영수증 재사용·병렬 쓰기 검사가 그 쓰기를 모른다.
  규칙 2(B74-1): 사용자 위치를 **지우는** 자리는 사유가 적힌 곳뿐인가?
      `[self:copy]`/`[self:move]` 가 대상부터 `rmtree` 해 기존 백업을 영구 삭제했고, 겹친 경로에선
      원본까지 지웠다. 삭제는 delete 동사의 일이다 — 다른 자리는 여기 `EFFECT_ALLOW` 에 사유와 함께.

판정 기준은 사본을 두지 않는다: 읽기/쓰기는 판본 2 효과 계약을 만드는 **같은 함수**
(`ibl_ops.op_side_effect` — `ibl_v2_contracts.handler_contract` 가 쓰는 것).
형제 `iblbuild_side_effect_scan`(55회차)은 op 없는 액션의 **선언 유무**만 묻는다 —
`side_effect: false` 를 선언하면 더 보지 않아 B74-2 가 통과했다. 이 관문은 선언을 믿지 않고 흐름을 본다.

흐름(값 오염, 흐름 무감 고정점): 입력 dict 에서 꺼낸 값 = 사용자 **위치**(LOC). 대입·언팩·for·with·
경로 연산(`/`·join·Path·parent·resolve·f-문자열)·같은 패키지 함수 호출(위치·키워드 인자, 모듈 별칭
`_load_sibling("m")`·`import m`)·중첩 함수로 전파한다. 이름만 뽑은 값(`.name`·`.stem`·`basename`)과
해시·길이·불리언은 위치가 아니다 — `CACHE / Path(p).name` 은 캐시 안이다.
범위(하한): 반환값의 오염은 인자에서 보수적으로 추정하고, 패키지 밖·동적 디스패치는 따라가지 않는다.
시작점을 못 찾은 도구는 **미상**으로 세어 보이고 빌드는 막지 않는다.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from iblbuild_action_reads import _dispatch_mode
from iblbuild_derive import build_tool_index

from check_body_path_expansion import _PATH_KEYS   # 경로 입력 키의 한 벌(형제 관문 규칙 2 와 공유)

DICT, LOC, NAME = 3, 2, 1   # 입력 dict(경로 키를 꺼내면 LOC) · 사용자 위치 · 이름 조각

# 검토한 효과 자리 — 키 = "패키지/도구"(인라인 분기) 또는 "패키지/모듈.함수[.중첩]", 값 = 사유(필수).
# 규칙 1·2 공용. 새 항목은 "왜 사용자 위치가 아닌가/왜 지워도 되는가"를 적는다.
EFFECT_ALLOW: dict[str, str] = {
    "system_essentials/delete_path": "삭제 동사 자체([self:delete]) — 선언이 영구 삭제를 말한다.",
    "system_essentials/copy_ops.transfer_path.copy_file":
        "배타 생성('xb')한 자기 부분 파일만 실패 시 지우고, move 일 때만 복사 완료 뒤 원본을 지운다.",
    "system_essentials/copy_ops.transfer_path.copy_dir":
        "move 일 때만 자식을 다 옮긴 빈 원본 폴더를 rmdir(비어 있지 않으면 실패)한다.",
    "guest-helper/handler._finish_visual":
        "캡처는 내부 outputs/limb_screens/<손발> 에 쓴다 — 입력 target 은 경로가 아니라 손발 이름(경로 키 이름 겹침).",
    "guest-helper/handler._prune_screens": "같은 내부 캡처 폴더에서 screen_* 오래된 장만 정리한다.",
    "family-news/handler._fn_remove_photo":
        "판 저장소(_EDITIONS/<판>/photos) 안 자기 사본을, 판 데이터에 실제 있는 이름일 때만 지운다(remove_photo op).",
}

_NAME_ATTRS = {"name", "stem", "suffix", "suffixes"}
_NAME_FUNCS = {"basename"}
# 위치를 보존하는 연산 — 이 밖의 외부 호출 결과(문서 객체·읽은 내용·해시)는 위치가 아니다.
_PATH_OPS = {"Path", "PurePath", "PosixPath", "str", "fspath", "abspath", "realpath", "normpath", "expanduser",
             "expandvars", "join", "joinpath", "with_suffix", "with_name", "with_stem", "resolve", "absolute",
             "dirname", "relpath", "relative_to", "replace", "strip", "rstrip", "lstrip", "splitext", "split",
             "iterdir", "glob", "rglob", "listdir", "scandir", "walk", "sorted", "list", "tuple", "set",
             "reversed", "next", "iter", "enumerate", "zip", "filter", "min", "max", "format"}
_PATH_FRAGMENTS = ("path", "resolve", "expand", "stage")
_DELETE_CALLS = {("shutil", "rmtree"), ("os", "remove"), ("os", "unlink"), ("os", "rmdir"), ("os", "removedirs")}
_DELETE_METHODS = {"unlink", "rmdir"}
_WRITE_CALLS = {("os", "makedirs"): 0, ("os", "mkdir"): 0, ("shutil", "copy"): 1, ("shutil", "copy2"): 1,
                ("shutil", "copyfile"): 1, ("shutil", "copytree"): 1, ("os", "symlink"): 1, ("os", "link"): 1,
                ("shutil", "move"): 1, ("os", "rename"): 1, ("os", "replace"): 1}
_WRITE_METHODS = {"write_text", "write_bytes", "mkdir", "touch", "symlink_to", "hardlink_to"}
_SAVE_METHODS = {"save", "savefig", "to_csv", "to_excel", "to_json", "to_parquet", "write_pdf", "extractall"}
_WRITE_MODE = re.compile(r"[wax+]")


def _modules(pkg_dir: Path) -> dict[str, ast.Module]:
    out: dict[str, ast.Module] = {}
    for py in sorted(pkg_dir.glob("*.py")):
        try:
            out[py.stem] = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
    return out


def _sibling_module(call: ast.AST, mods) -> str | None:
    """`_load_sibling("m")`·`load_module("m")` 같은 모듈 적재 호출 → 모듈 이름."""
    if (isinstance(call, ast.Call) and call.args and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str) and call.args[0].value in mods):
        return call.args[0].value
    return None


class _Package:
    def __init__(self, mods: dict[str, ast.Module]):
        self.mods = mods
        self.funcs = {m: {n.name: n for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
                      for m, t in mods.items()}
        self.aliases: dict[str, dict[str, str]] = {}      # 모듈 → {별칭: 대상 모듈}
        self.names: dict[str, dict[str, tuple[str, str]]] = {}  # 모듈 → {이름: (모듈, 함수)}
        for m, tree in mods.items():
            al, nm = {}, {}
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    for a in n.names:
                        if a.name.split(".")[-1] in mods:
                            al[a.asname or a.name] = a.name.split(".")[-1]
                elif isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[-1] in mods:
                    for a in n.names:
                        nm[a.asname or a.name] = (n.module.split(".")[-1], a.name)
                elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                    target = _sibling_module(n.value, mods)
                    if target:
                        al[n.targets[0].id] = target
            self.aliases[m], self.names[m] = al, nm

    def resolve(self, mod: str, func: ast.expr) -> tuple[str, str] | None:
        if isinstance(func, ast.Name):
            if func.id in self.funcs[mod]:
                return mod, func.id
            hit = self.names[mod].get(func.id)
            if hit and hit[1] in self.funcs.get(hit[0], {}):
                return hit
        elif isinstance(func, ast.Attribute):
            target = (self.aliases[mod].get(func.value.id) if isinstance(func.value, ast.Name)
                      else _sibling_module(func.value, self.mods))
            if target and func.attr in self.funcs.get(target, {}):
                return target, func.attr
        return None


def _dotted(func: ast.expr) -> tuple[str, str] | None:
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id, func.attr
    return None


def _open_writes(call: ast.Call, mode_index: int) -> bool:
    mode = None
    if len(call.args) > mode_index and isinstance(call.args[mode_index], ast.Constant):
        mode = call.args[mode_index].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and bool(_WRITE_MODE.search(mode))


class _Flow:
    """한 함수(또는 인라인 분기 몸들)의 오염 고정점 + 효과 자리 수집."""

    def __init__(self, pkg: _Package, report):
        self.pkg, self.report = pkg, report
        self.done: set = set()
        self.mod: str | None = None
        self.branch_names: set = set()
        self.ret_memo: dict = {}

    def taint(self, e, env, mod=None) -> int:
        mod = mod or self.mod
        if e is None:
            return 0
        if isinstance(e, ast.Name):
            return env.get(e.id, 0)
        if isinstance(e, ast.Subscript):
            base = self.taint(e.value, env, mod)
            if base == DICT:
                key = e.slice
                return LOC if isinstance(key, ast.Constant) and key.value in _PATH_KEYS else 0
            return base
        if isinstance(e, ast.Attribute):
            base = self.taint(e.value, env, mod)
            if base == DICT:
                return 0
            return min(base, NAME) if e.attr in _NAME_ATTRS else base
        if isinstance(e, ast.Call):
            return self._call_taint(e, env, mod)
        if isinstance(e, ast.Dict):
            spread = [self.taint(v, env, mod) for k, v in zip(e.keys, e.values) if k is None]
            return DICT if DICT in spread else 0
        if isinstance(e, ast.BinOp):
            left, right = self.taint(e.left, env, mod), self.taint(e.right, env, mod)
            return LOC if LOC in (left, right) else NAME if NAME in (left, right) else 0
        if isinstance(e, (ast.Compare, ast.Constant, ast.Lambda)):
            return 0
        levels = [self.taint(c, env, mod) for c in ast.iter_child_nodes(e) if isinstance(c, ast.expr)]
        return max(levels, default=0)

    def _call_taint(self, e, env, mod) -> int:
        f = e.func
        fname = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        recv = self.taint(f.value, env, mod) if isinstance(f, ast.Attribute) else 0
        if recv == DICT and fname in ("get", "pop", "setdefault"):
            key = e.args[0] if e.args else None
            return LOC if isinstance(key, ast.Constant) and key.value in _PATH_KEYS else 0
        args = [self.taint(a, env, mod) for a in e.args] + [self.taint(k.value, env, mod) for k in e.keywords]
        target = self.pkg.resolve(mod, f) if mod else None
        if target:
            # 패키지 안 함수: 인자 오염을 매개변수에 묶고 그 함수의 return 식으로 잰다.
            fn = self.pkg.funcs[target[0]][target[1]]
            params = [a.arg for a in fn.args.args]
            bound = {params[i]: lv for i, lv in enumerate(args[:len(e.args)]) if i < len(params) and lv}
            bound.update({k.arg: lv for k, lv in zip(e.keywords, args[len(e.args):]) if k.arg in params and lv})
            return self.returns(target, fn, bound)
        levels = [x for x in args + [recv] if x != DICT]
        if fname in _NAME_FUNCS:
            return min(max(levels, default=0), NAME)
        if fname in _PATH_OPS or any(frag in fname.lower() for frag in _PATH_FRAGMENTS):
            return max(levels, default=0)
        return 0

    def fix(self, tree, env, nested):
        """흐름 무감 고정점 — 대입·언팩·for·with·중첩 함수 인자로 오염을 퍼뜨린다."""
        changed = True
        while changed:
            changed = False
            for n in ast.walk(tree):
                if isinstance(n, ast.Assign):
                    lv = self.taint(n.value, env)
                    changed |= any([self._bind(t, lv, env) for t in n.targets]) if lv else False
                elif isinstance(n, (ast.AugAssign, ast.AnnAssign)) and n.value is not None:
                    lv = self.taint(n.value, env)
                    changed |= self._bind(n.target, lv, env) if lv else False
                elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                    lv = self.taint(n.iter, env)
                    changed |= self._bind(n.target, lv, env) if lv else False
                elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                    lv = self.taint(n.context_expr, env)
                    changed |= self._bind(n.optional_vars, lv, env) if lv else False
                elif isinstance(n, ast.NamedExpr):
                    lv = self.taint(n.value, env)
                    changed |= self._bind(n.target, lv, env) if lv else False
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in nested:
                    params = [a.arg for a in nested[n.func.id].args.args]
                    for i, a in enumerate(n.args[:len(params)]):
                        lv = self.taint(a, env)
                        if lv and env.get(params[i], 0) < lv:
                            env[params[i]], changed = lv, True

    def returns(self, target, fn, bound) -> int:
        key = (target, tuple(sorted(bound.items())))
        if key in self.ret_memo:
            return self.ret_memo[key]
        self.ret_memo[key] = 0                       # 재귀 방어 — 진행 중이면 0 으로 본다
        outer, self.mod = self.mod, target[0]
        env = dict(bound)
        tree = ast.Module(body=fn.body, type_ignores=[])
        self.fix(tree, env, {})
        level = max((self.taint(n.value, env) for n in ast.walk(tree)
                     if isinstance(n, ast.Return) and n.value is not None), default=0)
        self.mod = outer
        self.ret_memo[key] = level
        return level

    @staticmethod
    def _bind(target, level, env) -> bool:
        changed = False
        for n in ast.walk(target):
            if isinstance(n, ast.Name) and env.get(n.id, 0) < level:
                env[n.id], changed = level, True
        return changed

    def run(self, mod: str, label: str, body: list, env: dict, depth: int = 0):
        """body 문장들(중첩 함수 포함)을 env 로 고정점까지 돌리고 효과 자리를 보고한다."""
        key = (mod, label, tuple(sorted(env.items())))
        if key in self.done or depth > 6:
            return
        self.done.add(key)
        outer, self.mod = self.mod, mod
        tree = ast.Module(body=body, type_ignores=[])
        nested = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        owner = {}
        for fn in nested.values():
            for n in ast.walk(fn):
                owner.setdefault(id(n), fn.name)   # 가장 바깥 중첩이 먼저 — 아래에서 안쪽으로 덮는다
        for fn in sorted(nested.values(), key=lambda f: -len(list(ast.walk(f)))):
            for n in ast.walk(fn):
                owner[id(n)] = fn.name
        self.fix(tree, env, nested)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                site = label + ("." + owner[id(n)] if id(n) in owner else "")
                self._sink(mod, site, n, env)
                if not (isinstance(n.func, ast.Name) and n.func.id in nested):
                    self._follow(mod, n, env, depth)
        self.mod = outer

    def _sink(self, mod, site, call, env):
        f, arg = call.func, (lambda i: call.args[i] if len(call.args) > i else None)
        dotted = _dotted(f)
        hits = []
        if dotted in _DELETE_CALLS and self.taint(arg(0), env) == LOC:
            hits.append(("delete", ".".join(dotted)))
        if dotted in _WRITE_CALLS and self.taint(arg(_WRITE_CALLS[dotted]), env) == LOC:
            hits.append(("write", ".".join(dotted)))
        if isinstance(f, ast.Name) and f.id == "open" and _open_writes(call, 1) and self.taint(arg(0), env) == LOC:
            hits.append(("write", "open(쓰기)"))
        if isinstance(f, ast.Attribute) and dotted not in _DELETE_CALLS and dotted not in _WRITE_CALLS:
            recv = self.taint(f.value, env)
            if f.attr in _DELETE_METHODS and recv == LOC:
                hits.append(("delete", f".{f.attr}()"))
            elif f.attr in _WRITE_METHODS and recv == LOC:
                hits.append(("write", f".{f.attr}()"))
            elif f.attr == "open" and recv == LOC and _open_writes(call, 0):
                hits.append(("write", ".open(쓰기)"))
            elif f.attr in _SAVE_METHODS and self.taint(arg(0), env) == LOC:
                hits.append(("write", f".{f.attr}(경로)"))
        for kind, prim in hits:
            self.report(kind, f"{mod}.{site}" if mod else site, prim, call.lineno)

    def _follow(self, mod, call, env, depth):
        f = call.func
        if (isinstance(f, ast.Call) and isinstance(f.func, ast.Name) and f.func.id == "getattr"
                and len(f.args) >= 2 and mod):
            # `getattr(형제모듈, tool_name)(…)` — 분기 이름이 곧 함수 이름인 규약. 이름이 상수면 그것,
            # 아니면 이 시작점이 도달한 분기 이름들 중 그 모듈에 있는 함수 전부.
            holder = f.args[0]
            target_mod = (self.pkg.aliases[mod].get(holder.id) if isinstance(holder, ast.Name)
                          else _sibling_module(holder, self.pkg.mods))
            funcs = self.pkg.funcs.get(target_mod or "", {})
            names = ([f.args[1].value] if isinstance(f.args[1], ast.Constant) else sorted(self.branch_names))
            for name in names:
                if name in funcs:
                    self._enter(target_mod, name, funcs[name], call, env, depth)
            return
        target = self.pkg.resolve(mod, call.func) if mod else None
        if target:
            self._enter(target[0], target[1], self.pkg.funcs[target[0]][target[1]], call, env, depth)

    def _enter(self, target_mod, name, fn, call, env, depth):
        params = [a.arg for a in fn.args.args]
        sub = {}
        for i, a in enumerate(call.args[:len(params)]):
            if (lv := self.taint(a, env)):
                sub[params[i]] = lv
        for kw in call.keywords:
            if kw.arg in params and (lv := self.taint(kw.value, env)):
                sub[kw.arg] = lv
        if sub:
            self.run(target_mod, name, fn.body, sub, depth + 1)


def _starts(pkg: _Package, tool: str, op: str | None):
    """(모듈, 표지, 몸 문장들, 입력 이름) — 디스패처 op 함수 · `def <tool>` · 인라인 `if tool_name == …` 분기."""
    handler = pkg.mods.get("handler")
    if handler is not None:
        for node in handler.body:
            if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_OP_DISPATCHERS"
                                                     for t in node.targets) and isinstance(node.value, ast.Dict)):
                for k, v in zip(node.value.keys, node.value.values):
                    if not (isinstance(k, ast.Constant) and k.value == tool and isinstance(v, ast.Dict)):
                        continue
                    for ok, fv in zip(v.keys, v.values):
                        if not (isinstance(ok, ast.Constant) and ok.value == op):
                            continue
                        if isinstance(fv, ast.Name) and fv.id in pkg.funcs["handler"]:
                            fn = pkg.funcs["handler"][fv.id]
                            mode = _dispatch_mode(handler)
                            i = mode[1] if mode[0] == "pos" else 0
                            params = [a.arg for a in fn.args.args]
                            return [("handler", fv.id, fn.body, params[i])] if len(params) > i else None
                        if (isinstance(fv, ast.Call) and len(fv.args) == 2
                                and all(isinstance(a, ast.Constant) for a in fv.args)):
                            m, f = fv.args[0].value, fv.args[1].value
                            fn = pkg.funcs.get(m, {}).get(f)
                            return [(m, f, fn.body, fn.args.args[0].arg)] if fn and fn.args.args else None
                        return None
    for m, funcs in pkg.funcs.items():
        if tool in funcs and funcs[tool].args.args:
            return [(m, tool, funcs[tool].body, funcs[tool].args.args[0].arg)]
    for m, funcs in pkg.funcs.items():
        for fn in funcs.values():
            branches = _branches(fn)
            if tool not in branches or not fn.args.args:
                continue
            names, prefixes = {tool}, set()
            for n in ast.walk(ast.Module(body=branches[tool], type_ignores=[])):
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "tool_name" for t in n.targets):
                    if isinstance(n.value, ast.Constant):
                        names.add(n.value.value)
                    elif isinstance(n.value, ast.JoinedStr) and n.value.values and isinstance(n.value.values[0], ast.Constant):
                        prefixes.add(n.value.values[0].value)
            reached = {name for name in branches if name in names or any(name.startswith(p) for p in prefixes)}
            body = [s for name in sorted(reached) for s in branches[name]]
            return [(m, tool, body, fn.args.args[0].arg, reached)]
    return None


def _branches(fn) -> dict[str, list]:
    out: dict[str, list] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name) \
                and n.test.left.id == "tool_name" and isinstance(n.test.ops[0], (ast.Eq, ast.In)):
            comp = n.test.comparators[0]
            consts = [comp] if isinstance(comp, ast.Constant) else list(getattr(comp, "elts", []))
            for c in consts:
                if isinstance(c, ast.Constant) and isinstance(c.value, str):
                    out.setdefault(c.value, []).extend(n.body)
    return out


def validate_user_path_effects(data: dict, root: Path) -> tuple[list[str], list[str]]:
    backend = Path(__file__).resolve().parents[1] / "backend"
    for sub in ("", "ibl", "base", "common"):
        p = str(backend / sub) if sub else str(backend)
        if p not in sys.path:
            sys.path.insert(0, p)
    from ibl_ops import op_side_effect, ops_block

    tool_index = build_tool_index(root)
    packages: dict[Path, _Package] = {}
    issues, unresolved = [], []
    for node_name, node in (data.get("nodes") or {}).items():
        for aname, cfg in ((node or {}).get("actions") or {}).items():
            if not isinstance(cfg, dict) or cfg.get("router") != "handler" or cfg.get("tool") not in tool_index:
                continue
            tool = cfg["tool"]
            pkg_dir = tool_index[tool][0]
            pkg = packages.setdefault(pkg_dir, _Package(_modules(pkg_dir)))
            ops = list((ops_block(cfg).get("values") or {}) or [None])
            for op in ops:
                starts = _starts(pkg, tool, op)
                q = f"[{node_name}:{aname}]" + (f"{{op:\"{op}\"}}" if op else "")
                if not starts:
                    unresolved.append(q)
                    continue
                reads_only = not op_side_effect(cfg, op)
                found: list[tuple[str, str, str, int]] = []
                flow = _Flow(pkg, lambda kind, site, prim, line: found.append((kind, site, prim, line)))
                for mod, label, body, param, *reached in starts:
                    flow.branch_names = set(reached[0]) if reached else set()
                    flow.run(mod, label, body, {param: DICT})
                for kind, site, prim, line in sorted(set(found)):
                    where = f"{pkg_dir.name}/{site}"
                    allowed = (EFFECT_ALLOW.get(where) or EFFECT_ALLOW.get(f"{pkg_dir.name}/{tool}")
                               or EFFECT_ALLOW.get(where.rsplit(".", 1)[0]))
                    if allowed:
                        continue
                    if reads_only:
                        issues.append(f"{q} 는 판본 2 가 읽기로 계약했는데 입력 경로에 {'쓴다' if kind == 'write' else '지운다'} — "
                                      f"{where}:{line} {prim}. 원본 옆이 아니라 파생 캐시(tempfile·outputs)에 쓰거나 "
                                      "명시 인자로만 쓰고, 정말 세계를 바꾸면 ops.side_effect 를 true 로 선언하라(검토한 내부 위치면 EFFECT_ALLOW 에 사유).")
                    elif kind == "delete":
                        issues.append(f"{q} 가 입력 경로를 지운다 — {where}:{line} {prim}. 사용자 위치 삭제는 delete 동사의 "
                                      "일이다(74회차 B74-1: copy 가 대상부터 rmtree 해 백업을 영구 삭제). 이름 충돌은 "
                                      "새 이름으로 피하고, 정말 필요한 자리면 EFFECT_ALLOW 에 사유와 함께 올려라.")
    return sorted(set(issues)), sorted(set(unresolved))


if __name__ == "__main__":
    import yaml
    ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    nodes = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    found, unknown = validate_user_path_effects(nodes, ROOT)
    for line in found:
        print(line)
    print(f"{len(found)}건 · 시작점 미상 {len(unknown)}")
