#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""부작용 정직성 관문 — 구현이 세계를 바꾸는데 선언이 '읽기'인 액션을 빌드에서 막는다 (2026-09-06, 55회차 B55-1).

왜: `ibl_safety` 는 부작용을 `returns: effect` 에서 파생하고, "데이터를 돌려주지만 세계를 바꾸는"
액션은 src yaml 에 `side_effect: true` 로 **선언**하라고 스스로 적어 뒀다(카메라·마이크 선례).
house-designer 의 `arch_create`·`arch_modify` 가 그 선언 없이 `returns: scalar` 로 살아 있었고,
조종실 dry-run 이 "read" 를 켜고 훈련 회차가 그 라벨을 믿고 설계 파일 3개를 만들었다.
소비자 = 조종실 dry-run 안전 라벨 · `ibl_health_check` read-only 게이팅 · 훈련 규약의 판단 근거.

무엇을 보나: `validate_side_effect_declaration`(op 분기 액션)이 못 보는 축 — **op 가 없는**
handler 라우터 액션의 **구현 자체**. 이름 목록으로 추측하지 않는다(그 검사가 기각한 길). 대신
구현-읽기 감사(`validate_impl_reads`)와 같은 앵커 = 코드: 도구 함수에서 도달 가능한 호출 중
파일·디스크·원장·외부를 바꾸는 **쓰기 원시**(open 'w' · write_text · makedirs · shutil ·
INSERT/UPDATE/DELETE · requests.post …)가 있으면, 그 액션은 `side_effect: true|false` 를
**말로** 선언해야 한다. false 도 선언이다(캐시만 쓰는 읽기 액션은 그렇게 말하면 통과) —
낱말 목록이 아니라 아는 사람이 아는 것을 적게 하는 구조(2026-07-28 가드와 같은 결).

해소 못 한 도구(dispatch 모양이 낯설어 함수를 못 찾음)는 **미상**으로 세어 빌드 출력에 보인다 —
조용히 통과시키지 않되 빌드를 막지도 않는다(모르는 것을 아는 척하지 않는다).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from iblbuild_derive import build_tool_index

# 쓰기 원시 — 코드의 이름(몸의 명사)이지 어휘 이름이 아니다.
_WRITE_ATTRS = {
    "write_text", "write_bytes", "mkdir", "unlink", "rmdir", "touch",
    "makedirs", "rmtree", "copy2", "copyfile", "copytree", "move",
    "post", "put", "patch", "delete", "commit", "executemany",
    "save", "dump", "write",  # json.dump / img.save / f.write — 파일 객체가 아니어도 쓰기 의도
}
# 자료형과 이름이 겹치는 원시(str.replace · list.remove · dict.copy · list.append)는 수신자가
# os/shutil 일 때만 쓰기로 센다 — 첫 census 에서 이 넷이 오탐 15건 전부였다.
_OS_ONLY_ATTRS = {"replace", "remove", "rename", "copy"}
_WRITE_NAME_RE = re.compile(r"(^|_)(save|write|store|persist|delete|remove|insert|upsert|create|modify)(_|$)", re.I)
_SQL_WRITE_RE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER)\b", re.I)
_OPEN_WRITE_MODE = re.compile(r"[wax+]")


def _files_of(pkg_dir: Path) -> list[Path]:
    files = sorted(p for p in pkg_dir.glob("*.py") if not p.name.startswith("_"))
    if (pkg_dir / "tools").is_dir():
        files += sorted((pkg_dir / "tools").glob("*.py"))
    return [f for f in files if f.is_file()]


def _parse_all(pkg_dir: Path) -> dict[str, ast.FunctionDef]:
    """패키지 전 파일의 최상위 함수 {이름: 노드}(이름 충돌은 먼저 온 파일이 이김 — 호출 추적용 근사)."""
    funcs: dict[str, ast.FunctionDef] = {}
    for f in _files_of(pkg_dir):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name not in funcs:
                funcs[node.name] = node
    return funcs


def _first_call_name(node: ast.AST, funcs: dict) -> str | None:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in funcs:
            return sub.func.id
    return None


def resolve_tool_start(pkg_dir: Path, tool_name: str, funcs: dict | None = None) -> ast.AST | None:
    """도구 이름 → 구현 시작 노드. ① `def <tool>` ② 맵 리터럴 `"tool": func` ③ if-체인
    `if tool_name == "tool": <몸>` — 몸이 지역 함수를 부르든 인라인이든 **그 몸 자체**가 시작점.
    셋 다 아니면 None(미상)."""
    funcs = funcs if funcs is not None else _parse_all(pkg_dir)
    if tool_name in funcs:
        return funcs[tool_name]
    for f in _files_of(pkg_dir):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value == tool_name and isinstance(v, ast.Name) and v.id in funcs:
                        return funcs[v.id]
            elif isinstance(node, ast.If):
                test = node.test
                hits = [c for c in ast.walk(test) if isinstance(c, ast.Constant) and c.value == tool_name]
                if hits and isinstance(test, (ast.Compare, ast.BoolOp)):
                    return ast.Module(body=node.body, type_ignores=[])
    return None


def resolve_tool_function(pkg_dir: Path, tool_name: str, funcs: dict | None = None) -> str | None:
    """(호환) 시작 노드가 이름 있는 함수면 그 이름, 인라인 몸이면 "<inline>", 미상이면 None."""
    node = resolve_tool_start(pkg_dir, tool_name, funcs)
    if node is None:
        return None
    return node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "<inline>"


def _write_primitives(fn: ast.AST) -> list[str]:
    """함수 몸 하나의 쓰기 원시(직접 호출만)."""
    out: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name):
            if f.id == "open":
                mode = None
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value)
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value)
                if mode and _OPEN_WRITE_MODE.search(mode):
                    out.append(f"open(mode={mode!r})")
            elif _WRITE_NAME_RE.search(f.id):
                out.append(f"{f.id}()")
        elif isinstance(f, ast.Attribute):
            if f.attr in _OS_ONLY_ATTRS:
                if isinstance(f.value, ast.Name) and f.value.id in ("os", "shutil"):
                    out.append(f"{f.value.id}.{f.attr}()")
            elif f.attr in _WRITE_ATTRS:
                out.append(f".{f.attr}()")
            elif f.attr in ("execute",) and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str) and _SQL_WRITE_RE.match(node.args[0].value):
                out.append("execute(SQL write)")
            elif _WRITE_NAME_RE.search(f.attr):
                out.append(f".{f.attr}()")
    return out


def write_primitives_of(pkg_dir: Path, tool_name: str, max_depth: int = 4) -> tuple[bool, list[str]]:
    """(해소 여부, 시작 노드에서 도달 가능한 쓰기 원시 목록). 같은 패키지의 지역 함수 호출
    (`f()` · `mod.f()` 의 f 가 패키지 최상위 함수면)을 깊이 max_depth 까지 따른다."""
    funcs = _parse_all(pkg_dir)
    start = resolve_tool_start(pkg_dir, tool_name, funcs)
    if start is None:
        return False, []
    seen: set[str] = set()
    prims: list[str] = []
    frontier: list[tuple[str, ast.AST, int]] = [(getattr(start, "name", "<inline>"), start, 0)]
    while frontier:
        name, node, depth = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        for p in _write_primitives(node):
            tag = f"{name}:{p}"
            if tag not in prims:
                prims.append(tag)
        if depth < max_depth:
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                callee = None
                if isinstance(sub.func, ast.Name):
                    callee = sub.func.id
                elif isinstance(sub.func, ast.Attribute):
                    callee = sub.func.attr
                if callee and callee in funcs and callee not in seen:
                    frontier.append((callee, funcs[callee], depth + 1))
    return True, prims


def validate_side_effect_honesty(data: dict, root: Path) -> tuple[list[str], list[str]]:
    """반환: (빌드 실패 사유 목록, 미상 목록). 대상 = router:handler · returns ∈ {scalar, items} ·
    `side_effect` 불리언 선언 없음 · op 별 선언(`ops.side_effect`)도 없음."""
    tool_index = build_tool_index(root)
    issues: list[str] = []
    unresolved: list[str] = []
    for node_name, node_def in (data.get("nodes") or {}).items():
        for action_name, adef in ((node_def or {}).get("actions") or {}).items():
            if not isinstance(adef, dict) or adef.get("router") != "handler":
                continue
            if adef.get("returns") not in ("scalar", "items"):
                continue
            if isinstance(adef.get("side_effect"), bool):
                continue
            if isinstance(((adef.get("ops") or {}).get("side_effect")), dict):
                continue
            tool = adef.get("tool")
            ent = tool_index.get(tool or "")
            if not ent:
                continue
            pkg_dir = ent[0]
            resolved, prims = write_primitives_of(pkg_dir, tool)
            q = f"{node_name}:{action_name}"
            if not resolved:
                unresolved.append(f"{q} (tool={tool}, pkg={pkg_dir.name})")
                continue
            if prims:
                issues.append(
                    f"부작용-정직성: [{q}] 는 returns:{adef.get('returns')} 인데 구현({pkg_dir.name}/{tool})이 "
                    f"쓰기 원시를 부른다 — {prims[:4]}{' …' if len(prims) > 4 else ''}. "
                    "조종실 dry-run 이 'read' 로 표시해 확인 없이 실행된다. src yaml 에 `side_effect: true` "
                    "(세계를 바꾸면) 또는 `side_effect: false`(캐시·로그만 쓰는 읽기면, 사유 주석과 함께) 를 선언하라."
                )
    return issues, unresolved
