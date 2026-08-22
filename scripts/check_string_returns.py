#!/usr/bin/env python3
"""맨 문자열 반환 가드 — 도구 결과 경로에서 문자열 리터럴 return 재발 차단.

배경(2026-08-05 감사 ②): 에러·상태를 맨 한국어 문자열로 반환하는 경로가 전 패키지에
흩어져 있었다("검색어를 입력해주세요." 등 72곳 실측). returns:items 액션이 맨 문자열을
반환하면 파이프(_parse_prev)가 통화를 못 살린다 — 통화 계약의 조용한 위반. 소탕(0dd1050,
2차 완결) 후 이 가드가 재발을 봉쇄한다.

검사 범위(정밀 — 오탐 없는 집합만):
  각 패키지 handler.py 의 `execute` + `_OP_DISPATCHERS` 값으로 참조된 op 함수의
  **직접 return** (중첩 def/lambda 내부 제외 — 내부 헬퍼의 문자열 반환은 정상).
  거기서 문자열 리터럴/f-string 을 반환하면 위반. json.dumps(...)·변수·헬퍼 호출은 통과.

관례(수렴 완료 2026-08-05): 에러 = {"success": False, "error": msg} /
  효과·빈 결과 = {"success": True, "message": msg[, "items": []]} — json.dumps 로 반환.

정책:
  - 신규 위반 차단: BASELINE 에 없는 패키지에서 1건이라도 나오면 실패.
  - 래칫(악화 금지): BASELINE 패키지가 기록 건수를 넘으면 실패.
    (줄여서 0 이 되면 BASELINE 에서 항목 삭제 — 재진입 불가.)

사용: python3 scripts/check_string_returns.py
      python3 scripts/check_string_returns.py --self-test
의존성 0. 실패 시 exit 1.
"""
import ast
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(ROOT, "data", "packages", "installed", "tools")

# 기존 부채 동결(2026-08-05 실측). 값 = 그 시점 건수(래칫 상한).
# system_essentials 는 텍스트 계약 도구(파일 편집·run_command·계획모드 프로토콜 마커
# [[QUESTION_PENDING]]/__REQUIRES_APPROVAL__ 등)라 문자열이 정당 — 단 더 늘리지는 말 것.
BASELINE = {
    "system_essentials": 29,  # 2026-08-22 래칫 조임 (실측 29건, 재진입 불가)
    # 30→29: 앞선 수리들이 이 부채를 한 자리 줄여 놓았는데 BASELINE 이 안 따라와,
    # 가드가 매 커밋 "29건 < BASELINE 30 — 숫자를 내리세요" 를 스스로 신고하고 있었다.
    # 래칫은 내려간 만큼 즉시 조여야 그 자리가 다시 채워지는 걸 막는다(재진입 불가가 요점).
}


def _dispatcher_func_names(tree: ast.Module) -> set:
    """모듈의 _OP_DISPATCHERS 할당에서 값으로 참조된 함수 이름(Name) 집합."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_OP_DISPATCHERS" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for inner in node.value.values:
            if isinstance(inner, ast.Dict):  # {tool: {op: fn}}
                names.update(v.id for v in inner.values if isinstance(v, ast.Name))
            elif isinstance(inner, ast.Name):  # 평면형 {op: fn}
                names.add(inner.id)
    return names


def _direct_string_returns(fn: ast.AST) -> list:
    """함수 자신의 return 중 문자열 리터럴/f-string 인 것의 줄 번호 목록.

    중첩 def/lambda 내부는 제외 — 내부 헬퍼("N분 전" 포맷터 등)의 문자열 반환은 정상."""
    hits = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Return) and child.value is not None:
                v = child.value
                if isinstance(v, ast.JoinedStr) or (
                    isinstance(v, ast.Constant) and isinstance(v.value, str)
                ):
                    hits.append(child.lineno)
            walk(child)

    walk(fn)
    return hits


def scan_handler(path: str) -> list:
    """handler.py 하나의 위반 목록 [(func, lineno), ...]."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, OSError):
        return []  # 문법 오류는 다른 가드(py_compile/CI) 소관
    targets = _dispatcher_func_names(tree) | {"execute"}
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in targets:
            out.extend((node.name, ln) for ln in _direct_string_returns(node))
    return out


def main() -> int:
    failures = []
    for handler in sorted(glob.glob(os.path.join(TOOLS_DIR, "*", "handler.py"))):
        pkg = os.path.basename(os.path.dirname(handler))
        hits = scan_handler(handler)
        limit = BASELINE.get(pkg, 0)
        if len(hits) > limit:
            detail = ", ".join(f"{fn}:{ln}" for fn, ln in hits[:10])
            failures.append(
                f"  {pkg}/handler.py: 맨 문자열 return {len(hits)}건 (허용 {limit}) — {detail}"
            )
        elif limit and len(hits) < limit:
            print(f"[check_string_returns] {pkg}: {len(hits)}건 < BASELINE {limit} — "
                  f"BASELINE 숫자를 내리세요 (래칫 조이기)")
    if failures:
        print("맨 문자열 반환 위반 — 도구 결과는 json.dumps 된 dict 여야 합니다:", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        print('  에러 = {"success": False, "error": msg} / '
              '효과·빈 결과 = {"success": True, "message": msg[, "items": []]}', file=sys.stderr)
        return 1
    print("[check_string_returns] OK — 도구 결과 경로 맨 문자열 반환 없음")
    return 0


def self_test() -> int:
    """합성 소스로 탐지·제외 규칙 검증."""
    src_bad = '''
_OP_DISPATCHERS = {"t": {"a": do_a}}
def do_a(x):
    return f"에러: {x}"
def execute(tool_input, context):
    return "알 수 없는 도구"
'''
    src_good = '''
import json
_OP_DISPATCHERS = {"t": {"a": do_a}}
def do_a(x):
    def ago(m):
        return f"{m}분 전"  # 중첩 헬퍼 — 제외돼야 함
    return json.dumps({"success": True, "message": ago(3)}, ensure_ascii=False)
def execute(tool_input, context):
    return do_a(tool_input)
def helper():
    return "디스패처 밖 함수 — 검사 대상 아님"
'''
    def hits_of(src):
        tree = ast.parse(src)
        targets = _dispatcher_func_names(tree) | {"execute"}
        out = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in targets:
                out.extend(_direct_string_returns(node))
        return out

    bad = hits_of(src_bad)
    good = hits_of(src_good)
    assert len(bad) == 2, f"bad 소스에서 2건 탐지돼야 함 (실제 {len(bad)})"
    assert len(good) == 0, f"good 소스에서 0건이어야 함 (실제 {len(good)}) — 중첩 def/비대상 함수 제외 실패"
    # 래칫: BASELINE 초과만 실패
    assert BASELINE.get("system_essentials", 0) >= 1
    print("[check_string_returns] self-test OK (탐지 2 / 제외 0 / 래칫 상수 존재)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
