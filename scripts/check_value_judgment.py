#!/usr/bin/env python3
"""사설 값 판정 정적 검사 — 값의 동등·순서·포함을 私설로 판정하는 자리 탐지.

왜: 값의 뜻(동등성·순서·텍스트 매칭·멤버십)의 정본은 common/value_semantics.py
한 벌이다(45회차 후속 단일 소유권). 그런데 그 공통화는 **그때까지 발견된 판정만**
옮겼고, 발견 자체는 상상훈련이 칸을 파야 나왔다 — 그래서 같은 속(사설 값 판정)의
새 종이 43→44→45→46회차 4회 연속 태어났다(B43-1 백분율 · B44 비유한수 ·
B45-1 혼합 타입 · B46-1~7 텍스트 매칭/멤버십/관계 키). 부류 스윕은 사람이 고른
grep 이 아니라 관문이 먼저다(2026-08-24 교리) — 이 파일이 그 관문이다.
발견을 기다리지 않고 **탄생을 커밋 전에 차단한다**.

무엇을 잡나 (AST):
  [A] 사설 텍스트 정규화 매칭 — `.lower()`/`.casefold()` 결과가 비교·포함·
      startswith/endswith 의 피연산자인데, **반대편이 코드 소유 상수가 아닌** 자리.
      `scheme.lower() == "https"`(프로토콜 어휘 대조)는 대상이 아니다 — 우변이
      리터럴/상수집합이면 양쪽 다 코드가 소유하므로 값 판정이 아니라 분기다.
      `str(a).lower() in str(b).lower()`(옛 where_dsl B46-1)가 정확히 이 모양이다.
  [B] 조건 표면 모듈의 원시 판정 — 값 판정이 직업인 모듈(아래 SURFACE_FILES)에서
      비리터럴 두 피연산자의 ==/!=/</>/in 비교. 이 모듈들의 판정은 전부
      common.value_semantics 위임이어야 한다. 구조 검사(`f in r` 필드 실존,
      `op in _OPS` 어휘 분기)는 오탐 억제 규칙으로 거른다(아래).
      ★SURFACE_FILES 는 사람이 관리하는 명단이다 — 새 조건 언어 해석기를 만들면
      여기 등록할 것. 등록을 잊어도 규칙 [A]는 전역이라 사설 정규화 매칭의 탄생은
      잡히지만, 정규화 없는 원시 비교(B46-6 부류)는 명단 밖에서 샐 수 있다
      (수용된 잔여 — 판정 심볼 소비자를 자동 편입시키면 한 벌 채택이 벌칙이 되는
      역유인이라 택하지 않았다).

통과 조건(둘 중 하나):
  - common.value_semantics 로 위임한다 (values_equal/compare_order/text_match/
    list_membership/regex_text/…).
  - 그 줄 또는 바로 윗줄에 `# vj-ok: <사유>`. 사유 없는 억제는 불가.
    (예: `url.lower()` 스킴 정규화, 파일 확장자, HTTP 헤더 — 기계 식별자는
     ASCII lower 가 스펙이므로 값 판정이 아니다. 사유를 자리마다 코드에 남긴다.)

BASELINE 동결 목록은 처음부터 두지 않는다 — silent_clamp 가 2026-08-24 에 배운 것:
파일당 숫자를 얼리면 사유가 어디에도 없다. 예외는 자리마다 vj-ok 사유로만.

대상: backend/ + data/packages/installed/. pre-commit 훅에서 호출된다.
사용: 기본 = 관문 모드(위반 시 exit 1) · `--census` = 전수 보고(분류 작업용).
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [ROOT / "backend", ROOT / "data" / "packages" / "installed"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", "build", "dist"}

ALLOW_COMMENT = "vj-ok"

# 값의 뜻을 소유한 정본 — 이 파일 자신은 검사 대상이 아니다.
OWNER_FILES = {"backend/common/value_semantics.py"}

# 조건 표면 모듈 — 값 판정이 직업인 자리(규칙 [B] 적용 + 위임 의무).
# common.value_semantics 의 판정 심볼을 import 하는 모듈은 여기 등록돼야 한다.
SURFACE_FILES = {
    "backend/ibl/ibl_predicates.py",
    "backend/ibl/api_transforms.py",
    "backend/cognition/goal_evaluator.py",
    "backend/cognition/agent_goals.py",
    "backend/ibl/ibl_parser.py",
    "backend/common/safe_expr.py",
    "backend/common/row_conditions.py",
    "data/packages/installed/tools/data-ops/handler.py",
    "data/packages/installed/tools/data-ops/group_keys.py",
    "data/packages/installed/tools/data-ops/dataops_value_semantics.py",
}

# 정본 판정 심볼 — 비교식이 이걸 호출하면 위임이다(통과).
JUDGMENT_SYMBOLS = {
    "values_equal", "compare_order", "order_matches", "text_match",
    "negative_text_match", "list_membership", "regex_text",
    "group_identity", "relation_identity", "structural_equal",
}

NORM_METHODS = {"lower", "casefold"}
MATCH_METHODS = {"startswith", "endswith", "find", "index", "count"}
CMP_OPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)


def _is_norm_call(node) -> bool:
    """X.lower() / X.casefold() 호출인가."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in NORM_METHODS and not node.args)


def _contains_norm_call(node) -> bool:
    return any(_is_norm_call(sub) for sub in ast.walk(node))


def _is_code_owned(node) -> bool:
    """코드가 소유한 상수인가 — 리터럴, 리터럴 컬렉션, ALL_CAPS 상수 이름.

    이 판정이 관대하면 가드가 새고 엄격하면 오탐이 가드를 죽인다. ALL_CAPS 는
    이 저장소의 상수 관례(_OPS·_ORDER_OPS·REQUEST_NAMES)라 코드 소유로 본다.
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_code_owned(el) for el in node.elts)
    if isinstance(node, ast.Dict):
        return all(_is_code_owned(k) for k in node.keys if k is not None) and \
            all(_is_code_owned(v) for v in node.values)
    if isinstance(node, ast.Starred):
        return _is_code_owned(node.value)
    if isinstance(node, ast.Name):
        bare = node.id.lstrip("_")
        return bool(bare) and bare == bare.upper()
    if isinstance(node, ast.Attribute):
        bare = node.attr.lstrip("_")
        return bool(bare) and bare == bare.upper()
    if _is_norm_call(node):  # "abc".lower() 류 — 리터럴에 정규화만 얹은 것
        return _is_code_owned(node.func.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        # str("x")·tuple(SET) 처럼 상수를 감싼 것만 — 인자 전부 코드 소유일 때
        return bool(node.args) and all(_is_code_owned(a) for a in node.args)
    return False


def _structural_probe(node: ast.Compare) -> bool:
    """오탐 억제 — 값 판정이 아니라 구조·존재 검사인 비교.

    · `x in d` 꼴의 실존·등록부 검사: 우변이 **평범한 컨테이너 변수(Name/Attribute)**
      인 in 은 존재 검사로 본다(`f in r`·`k in seen`·`name in self.vars`).
      값 vs 값 멤버십의 실제 결함 모양(B46-5·B46-6)은 우변이 param 접근
      (`condition["in"]` 첨자·호출)이라 여기 안 걸린다. 좌변이 지역 변수인
      `a in b` 는 이 억제에 가려질 수 있다 — 수용된 잔여(문서화).
    · 렉서 문자·계수 비교: 등장하는 이름이 전부 2자 이하(i·n·c·q·ch)이고
      호출·첨자·속성이 없는 비교.
    · `is None` / `is not None` · len()·isinstance()·type() 이 낀 비교.
    """
    ops_are_in = all(isinstance(o, (ast.In, ast.NotIn)) for o in node.ops)
    if ops_are_in and node.comparators and \
            all(isinstance(c, (ast.Name, ast.Attribute)) for c in node.comparators):
        return True
    names, complex_node = [], False
    for sub in [node.left, *node.comparators]:
        for inner in ast.walk(sub):
            if isinstance(inner, ast.Name):
                names.append(inner.id)
            elif isinstance(inner, (ast.Call, ast.Subscript, ast.Attribute)):
                complex_node = True
    if names and not complex_node and all(len(n) <= 2 for n in names):
        return True
    for sub in [node.left, *node.comparators]:
        for inner in ast.walk(sub):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) \
                    and inner.func.id in ("len", "isinstance", "type", "id", "hash",
                                          "getattr", "hasattr"):
                return True
    return False


def _line_allowed(lines, lineno) -> bool:
    """그 줄 또는 바로 윗줄의 `# vj-ok: <사유>` — 사유 없는 억제는 불가."""
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines):
            text = lines[idx]
            if ALLOW_COMMENT in text:
                after = text.split(ALLOW_COMMENT, 1)[1].lstrip(": ").strip()
                if after:
                    return True
    return False


def _delegates(node) -> bool:
    """비교식 안에서 정본 심볼을 호출하면 위임이다."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else "")
            if name in JUDGMENT_SYMBOLS or name.lstrip("_") in JUDGMENT_SYMBOLS:
                return True
    return False


def _scan_file(path: Path, rel: str, census: bool):
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()
    hits = []
    is_surface = rel in SURFACE_FILES

    def report(node, rule, what):
        if _line_allowed(lines, node.lineno):
            return
        if _delegates(node):
            return
        snippet = lines[node.lineno - 1].strip() if node.lineno - 1 < len(lines) else ""
        hits.append((rel, node.lineno, rule, what, snippet[:110]))

    # assert 문 안의 비교는 자기 점검이지 값 판정이 아니다.
    in_assert = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            for sub in ast.walk(node):
                in_assert.add(id(sub))

    for node in ast.walk(tree):
        if id(node) in in_assert:
            continue
        # [A] 정규화 매칭 — 비교/포함의 피연산자에 .lower()/.casefold()
        if isinstance(node, ast.Compare) and _contains_norm_call(node):
            others = [c for c in [node.left, *node.comparators]
                      if not _contains_norm_call(c)]
            both_normed = not others  # 양쪽 다 정규화 — 값 vs 값 매칭의 전형
            vs_constant = others and all(_is_code_owned(o) for o in others)
            if both_normed or not vs_constant:
                report(node, "A", "사설 정규화 비교(.lower/.casefold) — text_match/values_equal 로")
        # [A'] X.lower().startswith(Y) 류 — 메서드형 매칭
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in MATCH_METHODS and _is_norm_call(node.func.value):
            if node.args and not all(_is_code_owned(a) for a in node.args):
                report(node, "A", f"사설 정규화 {node.func.attr}() — text_match 로")
        # [B] 조건 표면의 원시 비교 — 비리터럴 vs 비리터럴
        if is_surface and isinstance(node, ast.Compare):
            if any(isinstance(o, CMP_OPS) for o in node.ops):
                operands = [node.left, *node.comparators]
                if not any(_is_code_owned(o) for o in operands) \
                        and not any(isinstance(o, (ast.Is, ast.IsNot)) for o in node.ops) \
                        and not _structural_probe(node):
                    what = "조건 표면의 원시 비교 — values_equal/compare_order/list_membership 로"
                    report(node, "B", what)
    return hits


def main() -> int:
    census = "--census" in sys.argv
    all_hits = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            name = path.name
            if name.startswith("test_") or name == "conftest.py":
                continue
            rel = str(path.relative_to(ROOT))
            if rel in OWNER_FILES:
                continue
            all_hits.extend(_scan_file(path, rel, census))
    if census:
        cur = None
        for rel, lineno, rule, what, snippet in all_hits:
            if rel != cur:
                print(f"\n── {rel}")
                cur = rel
            print(f"  {lineno:>5} [{rule}] {snippet}")
        print(f"\n총 {len(all_hits)}자리 · 파일 {len({h[0] for h in all_hits})}개")
        return 0
    if all_hits:
        print("[FAIL] 사설 값 판정 — 값의 동등·순서·포함은 common/value_semantics 한 벌로:")
        for rel, lineno, rule, what, snippet in all_hits[:60]:
            print(f"  {rel}:{lineno} [{rule}] {what}\n      {snippet}")
        if len(all_hits) > 60:
            print(f"  … 외 {len(all_hits) - 60}자리")
        print("\n고치는 법: common.value_semantics 로 위임하거나, 값 판정이 아니면"
              f"(프로토콜·확장자·op 어휘) 그 줄에 `# {ALLOW_COMMENT}: <사유>` 를 남기세요.")
        return 1
    print("✓ 사설 값 판정 없음 — 값의 뜻은 value_semantics 한 벌")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
