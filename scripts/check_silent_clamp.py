#!/usr/bin/env python3
"""침묵 클램프 정적 검사 — 사용자가 요청한 개수를 조용히 깎는 자리 탐지.

왜: 사용자가 "25건 찾아줘"라고 했는데 코드가 `min(10, count)` 로 깎고
*깎았다는 말을 안 하면*, 모델도 사람도 그 결과를 "세상에 10건뿐"으로 읽는다.
빈손이 아니라 **틀린 충만함**이라 아무도 의심하지 않는다 — 파이프 침묵 실패
계열(docs/… P1~P19)과 같은 부류이고, 원인 진단이 가장 오래 걸리는 종류다.

2026-08-18 실측: `[sense:search_youtube]{count: 25}` 가 조용히 10건을 냈다.
더 중요한 건 재발 이력이다 — 같은 항목이 지목한 두 자리(search_youtube·
play_youtube) 중 **한 자리만 고쳐진 채 세션이 끝났고**, 다음 세션이 나머지를
발견했다. 인스턴스 수리로는 닫히지 않는 부류라는 실증이라, 부류를 가드로 닫는다.

무엇을 잡나: `min(<정수 리터럴>, <요청량>)` (양쪽 순서 모두).
  요청량 = limit/count/max_results/display/rows/per_page … (param 정본 어휘와 그 관습어)
  `min(8, len(jobs))`(워커 수)·`min(6, level)`(문서 레벨)처럼 요청량이 아닌 값,
  `min(2, len(x))`(표본 상한)은 대상이 아니다 — 오탐이 가드를 죽인다.

통과 조건(둘 중 하나):
  - 그 함수가 깎였다는 사실을 신고한다 — 본문에 `clamped`/`requested`/`clamp_message`.
    (정본 예시: data/packages/installed/tools/youtube/tool_youtube.py `SEARCH_COUNT_MAX`)
  - 줄 끝 또는 바로 윗줄의 `# clamp-ok: <사유>`. 사유 없는 벌거벗은 억제는 불가.

고치는 법: 상한을 상수로 올리고, 깎였으면 응답에 실어 보낸다.
    requested = int(limit or 5)
    limit = max(1, min(LIMIT_MAX, requested))
    ...
    if requested != limit:
        out['clamped'] = True; out['requested'] = requested
        out['message'] = f'요청 {requested}건 → 상한 {LIMIT_MAX}건으로 조정했습니다.'

BASELINE(동결 목록)은 2026-08-24 에 비웠다 — 예외 0. 새 침묵 클램프는 그 자리에서
고치거나 그 줄에 `# clamp-ok: <사유>` 를 달아 사유를 코드에 남긴다.

대상: backend/ + data/packages/installed/. pre-commit 훅에서 호출된다.

규칙 2 — 로컬 저장소의 기본 상한 (2026-09-29, 상상훈련 72회차 B72-3 밭 이관):
  `[self:finance]` 지출 조회가 SQL 기본 `LIMIT 200` 으로 자르고 그 부분 합계를 `total` 로 냈다.
  위 규칙(`min(리터럴, 요청량)`)도 68회차 절단 census(truncated 를 *내는* 생산자)도 이 형태를
  못 봤다 — **아무것도 신고하지 않는 기본값**이라서다. 같은 날 형제 `[self:health]` 가 기본 50행
  위에서 "총 N회"를 세고 있었다.
  판별선: 사용자 자신의 로컬 저장소(SQL)는 모집단을 알 수 있다 — 외부 API 검색의 "상위 N"
  과 달리 자른 목록이 전부로 읽히면 틀린 충만함이다. 그래서 SQL `LIMIT` 이 있는 함수에서
    · 요청량 인자의 양의 정수 기본값(`limit=50`)·`x.get("limit", N)`·`x.get("limit") or N`
    · SQL 문자열 안의 리터럴 `LIMIT N`(N>1)
  과, 같은 패키지의 그런 함수를 부르며 기본 상한을 거는 호출자를 잡는다.
  통과: 함수 본문이 신고한다(`truncated`·`has_more`·`total_count`·`clamped`·`next_offset`) 또는
  그 줄(def 줄 포함)·윗줄에 `# clamp-ok: <사유>`(순위 상위 N·렌더 상한·미라우팅 등).
  대상: data/packages/installed/tools + backend/drivers (IBL 결과를 내는 층).
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [ROOT / "backend", ROOT / "data" / "packages" / "installed"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", "build", "dist"}

ALLOW_COMMENT = "clamp-ok"

# 요청량 어휘 — check_param_canon 의 정본(limit)과 그 관습어들.
# 보수적으로: 개수를 뜻하는 것만. size/level/score/amount 처럼 다의적인 낱말은 뺀다.
REQUEST_NAMES = {
    "limit", "count", "num", "top_k", "topk", "max_results", "maxresults",
    "display", "per_page", "page_size", "pagesize", "rows", "max_items",
    "maxitems", "numofrows", "resultcount", "photo_limit", "n_results",
}

# 깎였다는 사실을 알리는 신호 — 이 중 하나가 함수 본문에 있으면 침묵이 아니다.
REPORT_MARKERS = ("clamped", "requested", "clamp_message")

# 2026-08-24 (#repair B6): 동결 목록을 **지웠다** — 예외 0.
#
# 43자리를 두 갈래로 청산했다:
#   · 7자리 = 우리가 정한 낮은 상한이라 실제로 사용자를 문다 → **정직 거절 또는 신고**
#     (radio 50 · 직방 50 · 네이버부동산 60 · 유튜브 큐 5 = 거절, memory 5 ·
#      네이버카페 20 · NAS 검색 10 = clamped/requested 를 봉투에 실어 신고)
#   · 36자리 = 원천 API 스펙 상한이거나 요청량이 아닌 안전 난간 → 그 줄에
#     `# clamp-ok: <사유>` 를 달아 **자리마다 사유가 코드에 남게** 했다.
#     (파일당 숫자만 얼려 두면 사유가 어디에도 없다 — 그게 동결의 진짜 문제였다.)
#
# ★목록을 다시 세우지 말 것. 새 침묵 클램프는 그 자리에서 고치거나 사유를 적는다.
BASELINE: dict = {}


def _names_in(node: ast.AST) -> set:
    """부분식에 등장하는 식별자·문자열 키를 모은다 (tool_input.get("limit") 포함)."""
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id.lower())
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr.lower())
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            found.add(sub.value.lower())
    return found


def _int_literal(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return node.value
    return None


# `# clamp-ok: <사유>` — 사유가 실제로 있어야 억제된다. 벌거벗은 `# clamp-ok` 는
# 억제하지 않는다(선언만 하고 검사하지 않으면 그 선언이 곧 구멍이 된다).
_ALLOW_RE = re.compile(re.escape(ALLOW_COMMENT) + r":\s*\S")


def _allowed_lines(src: str) -> set:
    """`# clamp-ok: 사유` 가 달린 줄 + 그 바로 다음 줄(주석을 위에 단 경우)."""
    ok = set()
    for i, line in enumerate(src.splitlines(), start=1):
        if _ALLOW_RE.search(line):
            ok.add(i)
            ok.add(i + 1)
    return ok


def scan_file(path: Path):
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    allowed = _allowed_lines(src)
    lines = src.splitlines()

    # 함수 범위 → 그 함수가 깎임을 신고하는지
    reporting_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            body = "\n".join(lines[node.lineno - 1:end]).lower()
            if any(m in body for m in REPORT_MARKERS):
                reporting_ranges.append((node.lineno, end, node.name))

    def _reports(lineno):
        return any(a <= lineno <= b for a, b, _ in reporting_ranges)

    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "min" and len(node.args) == 2):
            continue
        a, b = node.args
        lit, other = (_int_literal(a), b) if _int_literal(a) is not None else (_int_literal(b), a)
        if lit is None or lit < 1:
            continue
        hit = _names_in(other) & REQUEST_NAMES
        if not hit:
            continue
        if node.lineno in allowed or _reports(node.lineno):
            continue
        out.append((node.lineno, sorted(hit)[0], lit))
    return out


SQL_ROOTS = [ROOT / "data" / "packages" / "installed" / "tools", ROOT / "backend" / "drivers"]
SQL_REPORT_MARKERS = ("truncated", "has_more", "total_count", "clamped", "next_offset")
_SQL_LIMIT_LITERAL = re.compile(r"\bLIMIT\s+(\d+)\b")


def _positive(node) -> bool:
    return (isinstance(node, ast.Constant) and type(node.value) is int and node.value > 1)


def _default_caps(func) -> list:
    """(줄, 이름, 기본값) — 요청량 인자의 정수 기본값·.get(요청량, N)·.get(요청량) or N."""
    caps = []
    a = func.args
    pos = list(a.posonlyargs) + list(a.args)
    pairs = list(zip(pos[len(pos) - len(a.defaults):], a.defaults))
    pairs += [(x, d) for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None]
    for arg, d in pairs:
        if arg.arg.lower() in REQUEST_NAMES and _positive(d):
            caps.append((func.lineno, arg.arg, d.value))
    for n in ast.walk(func):
        get = None
        if isinstance(n, ast.Call) and len(n.args) > 1 and _positive(n.args[1]):
            get, val = n, n.args[1].value
        elif (isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or) and len(n.values) == 2
              and _positive(n.values[1]) and isinstance(n.values[0], ast.Call)):
            get, val = n.values[0], n.values[1].value
        if (get is not None and isinstance(get.func, ast.Attribute) and get.func.attr == "get"
                and get.args and isinstance(get.args[0], ast.Constant)
                and str(get.args[0].value).lower() in REQUEST_NAMES):
            caps.append((n.lineno, get.args[0].value, val))
    return caps


def _sql_limit_literals(func) -> list:
    out = []
    for n in ast.walk(func):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            for m in _SQL_LIMIT_LITERAL.finditer(n.value):
                if int(m.group(1)) > 1:
                    out.append((n.lineno, "LIMIT", int(m.group(1))))
    return out


def _has_sql_limit(func) -> bool:
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and "LIMIT" in n.value
               for n in ast.walk(func))


def scan_sql_defaults(pkg_files) -> list:
    """한 패키지(또는 드라이버 폴더)의 파일들 → [(rel, 줄, 이름, 값)]."""
    parsed = []
    for path in pkg_files:
        try:
            src = path.read_text(encoding="utf-8")
            parsed.append((path, src, ast.parse(src)))
        except (SyntaxError, UnicodeDecodeError):
            continue
    sql_funcs = set()                         # 신고하지 않는 로컬 저장소 조회(신고하는 것은 호출자를 면제)
    for _, src, tree in parsed:
        lines = src.splitlines()
        for f in ast.walk(tree):
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and _has_sql_limit(f):
                body = "\n".join(lines[f.lineno - 1:getattr(f, "end_lineno", f.lineno)])
                if not any(m in body for m in SQL_REPORT_MARKERS):
                    sql_funcs.add(f.name)
    out = []
    for path, src, tree in parsed:
        allowed = _allowed_lines(src)
        lines = src.splitlines()
        for f in ast.walk(tree):
            if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = "\n".join(lines[f.lineno - 1:getattr(f, "end_lineno", f.lineno)])
            if any(m in body for m in SQL_REPORT_MARKERS):
                continue
            if _has_sql_limit(f):
                hits = _default_caps(f) + _sql_limit_literals(f)
            elif any(isinstance(n, ast.Call) and (getattr(n.func, "id", None) in sql_funcs
                                                  or getattr(n.func, "attr", None) in sql_funcs)
                     for n in ast.walk(f)):
                hits = _default_caps(f)       # 기본 상한을 걸어 로컬 저장소 조회를 부르는 호출자
            else:
                continue
            for lineno, name, val in hits:
                if lineno in allowed or f.lineno in allowed:
                    continue
                rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
                out.append((str(rel), lineno, name, val, f.name))
    return out


def main_sql() -> list:
    found = []
    for root in SQL_ROOTS:
        if not root.exists():
            continue
        groups = [root] if root.name == "drivers" else sorted(p for p in root.iterdir() if p.is_dir())
        for g in groups:
            files = [p for p in sorted(g.rglob("*.py"))
                     if not any(part in SKIP_DIRS for part in p.parts) and not p.name.startswith("test_")]
            found += scan_sql_defaults(files)
    return found


def main() -> int:
    sql_hits = main_sql()
    if sql_hits:
        print(f"[FAIL] 로컬 저장소 기본 상한 {len(sql_hits)}건 — 자르고 알리지 않습니다(72회차 B72-3 부류):")
        for rel, lineno, name, val, fname in sql_hits:
            print(f"  {rel}:{lineno}  {fname}: {name}={val}")
        print()
        print("고치는 법:")
        print("  · 사용자 원장 조회는 숨은 기본 상한을 두지 말 것(limit=None — 기간·조건이 범위)")
        print("  · 화면·쪽 상한이 필요하면 같은 조건으로 모집단을 세어 total_count·truncated(·next_offset)를 실을 것")
        print("  · '최근 N' 창은 하나 더 떠 has_more 로 창 밖을 알릴 것")
        print("  · 순위 상위 N·렌더 상한·미라우팅처럼 정당하면 그 줄에 `# clamp-ok: <사유>`")
        return 1
    print("✓ 로컬 저장소 기본 상한 OK — 전부 신고하거나 사유를 남김")
    return _main_min()


def _main_min() -> int:
    per_file = {}
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            hits = scan_file(path)
            if hits:
                per_file[str(path.relative_to(ROOT))] = hits

    new, grown = [], []
    for rel, hits in sorted(per_file.items()):
        cap = BASELINE.get(rel)
        if cap is None:
            new.append((rel, hits))
        elif len(hits) > cap:
            grown.append((rel, hits, cap))

    if new or grown:
        total = sum(len(h) for _, h in new) + sum(len(h) for _, h, _ in grown)
        print(f"[FAIL] 침묵 클램프 {total}건 — 요청 개수를 깎고 알리지 않습니다:")
        for rel, hits in new:
            for lineno, name, lit in hits:
                print(f"  {rel}:{lineno}  min({lit}, …{name}…)  — 신규")
        for rel, hits, cap in grown:
            print(f"  {rel}: {len(hits)}건 — 래칫 상한 {cap} 초과(부채 파일은 더 자랄 수 없음)")
            for lineno, name, lit in hits:
                print(f"      {lineno}행  min({lit}, …{name}…)")
        print()
        print("고치는 법:")
        print("  · 상한을 상수로 올리고, 깎였으면 응답에 실어 보낼 것:")
        print("      requested = int(limit or 5); limit = max(1, min(LIMIT_MAX, requested))")
        print("      if requested != limit: out['clamped']=True; out['requested']=requested")
        print("  · 정본 예시: data/packages/installed/tools/youtube/tool_youtube.py (SEARCH_COUNT_MAX)")
        print("  · 진짜 예외면 그 줄에 `# clamp-ok: <사유>` (사유 필수)")
        return 1

    # 부채 청산 감지 — 줄었으면 BASELINE 을 낮추라고 안내(실패 아님, 재진입 봉인)
    for rel, cap in sorted(BASELINE.items()):
        actual = len(per_file.get(rel, []))
        if actual < cap:
            print(f"ℹ {rel} 이 {actual}건으로 내려옴 — BASELINE 을 {actual} 로 낮추세요(재진입 봉인)")

    print("✓ 침묵 클램프 OK — 예외 목록 0 (동결 부채 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
