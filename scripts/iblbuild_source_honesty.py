"""원천 정직 관문 두 개 (2026-09-29, 상상훈련 79회차 B79-3 밭 이관).

① 구조 미발견 ≠ 0건 (validate_source_miss)
  `[sense:used]{source:"danggeun"}` 는 당근 페이지가 바뀌어 JSON-LD ItemList 를 못 찾자
  `{total:0, items:[], note:"결과 없음 또는 페이지 구조 변경"}` 을 success 로 냈다 — "매물 없음"과
  "긁기 고장"을 한 문장에 접었다. `shopping.md` 가 옛 `site:"used"` 를 은퇴시킨 사유("except: pass 라
  실패가 침묵")가 후계 어휘에서 그대로 재발했다. 자리마다 고치면 새는 부류라(pitfall hand-picked-sweep)
  생산자 코드에서 두 모양을 기계로 센다:
    R1  성공 봉투(success:False·error 없음)인 dict 리터럴 return 에 빈 목록 칸(items·records·data…)이 있고
        같은 dict 의 문자열이 구조 미발견을 말한다("구조"·"미발견"·"파싱"·"structure"…) — 스스로 고장을
        알면서 0건 성공으로 내는 자리.
    R2  외부 원천을 부르는 함수(requests/httpx/urlopen/api_call/chrome_get/Playwright goto…)의 except 가
        빈 목록 또는 빈 목록 칸 dict(오류 칸 없음)를 return — 원천 실패·타임아웃·선택자 미발견을 0건으로 삼킨다.
  통과: 실패 봉투(success:False + error/error_type)로 올리거나, 정말 폴백 재료라면 그 줄(또는 윗줄)에
  `# empty-ok: <사유>`(예: 호출자가 다른 원천으로 폴백하고 둘 다 비면 실패로 올린다). 사유 없는 억제는 불가.
  하한 관문이다 — 함수 경계 밖에서 조립되는 빈 성공(파서가 None 을 돌려주고 호출자가 [] 로 바꾸는 식)은 못 본다.

② 원천 변이 축 fixture (validate_source_axes)
  `sense:used` 의 fixture 는 bunjang 하나라 당근 경로는 자가점검(건강 점검·관측 스윕)에 한 번도 안 닿았다.
  도구 스키마가 `source` enum(값 둘 이상)을 선언한 액션은 **원천마다** 실행 예시를 가져야 한다 —
  액션 fixture(source 생략이면 스키마 기본값) 또는 `shape_variants: {source=값: '<코드>'}`.
  주간 정직성 스윕(honesty_invariants_sweep 불변식 G)과 관측 스윕이 변이 축을 돌리므로 원천이 조용히 비면
  드러난다(일일 건강 점검은 액션 fixture 만 — 외부 API 를 매일 더 두드리지 않는다).
  기기·자격 의존으로 무인 실행이 불가능한 원천은 SOURCE_AXIS_EXEMPT 에 사유와 함께.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

PKG_ROOT = ("data", "packages", "installed", "tools")
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", "build", "dist"}

COLLECTION_KEYS = {"items", "records", "data", "results", "list", "documents", "products",
                   "rows", "restaurants", "cctvs", "webcams"}
MISS_WORDS = ("구조", "미발견", "파싱", "parse", "structure", "형식 변경", "selector", "선택자")
ALLOW_RE = re.compile(r"empty-ok:\s*\S")

# 외부 원천 호출의 표지 — 함수 이름(맨 호출) 또는 속성 호출.
NET_FUNCS = {"urlopen", "api_call", "api_call_raw", "chrome_get", "_get", "_fetch", "_http_get",
             "_call_api", "_request"}
NET_BASES = {"requests", "httpx", "session", "client", "urllib"}
NET_ATTRS = {"goto", "wait_for_selector", "urlopen"}

# 원천 변이 축 면제 — 키 "node:action@source=값", 값 = 사유(필수).
SOURCE_AXIS_EXEMPT: dict[str, str] = {
    "self:photo@source=usb": "USB 로 연결된 폰이 있어야만 도는 원천 — 무인 점검에서 기기 부재는 결함이 아니다",
}


def _allowed(lines: list[str], lineno: int) -> bool:
    here = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    above = lines[lineno - 2] if lineno >= 2 else ""
    return bool(ALLOW_RE.search(here) or ALLOW_RE.search(above))


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def _empty_success_dict(node) -> bool:
    """오류 칸 없는 dict 리터럴 + 빈 목록 칸."""
    if not isinstance(node, ast.Dict):
        return False
    fields = {_const(k): v for k, v in zip(node.keys, node.values) if isinstance(_const(k), str)}
    if _const(fields.get("success")) is False or "error" in fields or "error_type" in fields:
        return False
    return any(k in COLLECTION_KEYS and isinstance(v, ast.List) and not v.elts for k, v in fields.items())


def _empty_value(node) -> bool:
    return (isinstance(node, ast.List) and not node.elts) or _empty_success_dict(node)


def _calls_network(fn) -> bool:
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id in NET_FUNCS:
            return True
        if isinstance(f, ast.Attribute):
            if f.attr in NET_ATTRS or f.attr in NET_FUNCS:
                return True
            base = f.value
            if isinstance(base, ast.Attribute):
                base = base.value      # urllib.request.urlopen · self.session.get
            if isinstance(base, ast.Name) and base.id in NET_BASES and f.attr in ("get", "post", "request"):
                return True
    return False


def scan_source_miss(path: Path) -> list[tuple[int, str]]:
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    lines = src.splitlines()
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and _empty_success_dict(node.value):
            text = ast.unparse(node.value)
            if any(w in text for w in MISS_WORDS) and not _allowed(lines, node.lineno):
                out.append((node.lineno, "R1 구조 미발견을 말하는 0건 성공"))
    seen = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _calls_network(fn):
            continue
        for handler in ast.walk(fn):
            if not isinstance(handler, ast.ExceptHandler):
                continue
            for stmt in handler.body:
                if (isinstance(stmt, ast.Return) and _empty_value(stmt.value)
                        and stmt.lineno not in seen and not _allowed(lines, stmt.lineno)):
                    seen.add(stmt.lineno)
                    out.append((stmt.lineno, f"R2 {fn.name}: 원천 실패를 빈 결과로 삼킴"))
    return sorted(out)


def validate_source_miss(root: Path) -> list[str]:
    issues: list[str] = []
    base = root.joinpath(*PKG_ROOT)
    if not base.is_dir():
        return issues
    for path in sorted(base.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts) or path.name.startswith("test_"):
            continue
        for lineno, why in scan_source_miss(path):
            issues.append(f"{path.relative_to(root).as_posix()}:{lineno} {why} — 실패 봉투"
                          f"(success:False·error_type)로 올리거나 폴백 재료면 `# empty-ok: <사유>`")
    return issues


def _source_of(code: str):
    m = re.search(r'\bsource\s*:\s*["\']([\w-]+)["\']', code or "")
    return m.group(1) if m else None


def validate_source_axes(data: dict, root: Path) -> list[str]:
    """source enum 을 선언한 액션의 원천마다 실행 예시(fixture 또는 shape_variants)가 있는가."""
    from iblbuild_derive import build_tool_index

    tool_index = build_tool_index(root)
    issues: list[str] = []
    for node_name, node in ((data or {}).get("nodes") or {}).items():
        for action_name, action in ((node or {}).get("actions") or {}).items():
            if not isinstance(action, dict) or action.get("router") != "handler":
                continue
            entry = tool_index.get(action.get("tool"))
            if not entry:
                continue
            prop = (((entry[1].get("input_schema") or {}).get("properties") or {}).get("source") or {})
            enum = [v for v in (prop.get("enum") or []) if isinstance(v, str)]
            if len(enum) < 2:
                continue
            qualified = f"{node_name}:{action_name}"
            covered = set()
            codes = [action.get("fixture")] + list(((action.get("ops") or {}).get("fixture") or {}).values())
            for code in codes:
                if isinstance(code, str):
                    covered.add(_source_of(code) or prop.get("default"))
            for label in (action.get("shape_variants") or {}):
                param, _, value = str(label).partition("=")
                if param == "source":
                    covered.add(value)
            for value in enum:
                key = f"{qualified}@source={value}"
                if value in covered or key in SOURCE_AXIS_EXEMPT:
                    continue
                issues.append(
                    f"{qualified}: source={value} 실행 예시 없음 — 원천이 조용히 비거나 바뀌어도 자가점검에 "
                    f"안 닿는다. 액션 정의에 `shape_variants: {{source={value}: '[{qualified}]{{source: \"{value}\", …}}'}}`"
                    f" (무인 실행 불가 원천이면 iblbuild_source_honesty.SOURCE_AXIS_EXEMPT 에 사유)")
    return issues
