#!/usr/bin/env python3
"""items 주입 게이트 관문 — `items:` 파라미터를 **손으로 읽는** 자리 탄생 차단.

왜: `items: "$변수"` 는 치환이 통화를 JSON 문자열·통화 봉투·columns/rows 봉투 어느 모양으로도
넣을 수 있다. 그 되읽기의 정본은 `backend/common/currency.py` 의 `coerce_items_payload`
(→ `derive_items`) 한 벌인데, 소비자마다 자기 눈으로 읽어 같은 문장이 소비자에 따라
되고 안 됐다 — 같은 속의 결함이 세 번 났다(가이드 §4-3 밭 이관 규약):

  · B19-2 (19회차) reduce·brief 가 JSON 문자열을 못 읽었다(take 는 통과)
  · B51-1 (51회차) brief 가 변환자 결과 변수(columns/rows)를 못 읽었다 — 게이트 위임으로 수리
  · B53-2 (53회차) 고전 변환자(take/select/filter)가 columns/rows 를 못 읽고 "받은 봉투의 키:
    ['items']" 자기모순 거절 — 같은 자리를 손으로 다시 읽고 있었다

무엇을 잡나 (AST, 의존성 0):
  입력 dict(tool_input/params/input_data/inp/args …)에서 `"items"` 를 읽는 함수는
  같은 함수 안에서(또는 그 모듈에 들여온 별칭으로) `coerce_items_payload` 를 **불러야** 한다.
  안 부르면 그 자리는 자기 눈으로 읽는 것이다 — 위반.
  정당한 예외는 그 줄에 `# items-ok: <사유>` 를 단다(사유 없는 면제는 거부).

사용: python3 scripts/check_items_injection.py [--self-test]
실패 시 exit 1.
"""
import ast
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = sorted(
    glob.glob(os.path.join(ROOT, "data", "packages", "installed", "tools", "*", "*.py"))
    + glob.glob(os.path.join(ROOT, "backend", "ibl", "*.py"))
)
INPUT_NAMES = {"tool_input", "params", "input_data", "inp", "tool_args", "kwargs"}   # API JSON 을 담는 data·req 는 입력 dict 가 아니다(오탐)
GATE = "coerce_items_payload"


def _gate_aliases(tree: ast.AST):
    names = {GATE}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("currency"):
            for a in n.names:
                if a.name == GATE:
                    names.add(a.asname or a.name)
    return names


def _reads_items(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
        base = node.func.value
        if isinstance(base, ast.Name) and base.id in INPUT_NAMES and node.args:
            a0 = node.args[0]
            return isinstance(a0, ast.Constant) and a0.value == "items"
    if isinstance(node, ast.Subscript):
        base = node.value
        if isinstance(base, ast.Name) and base.id in INPUT_NAMES:
            sl = node.slice
            return isinstance(sl, ast.Constant) and sl.value == "items"
    return False


def _calls_gate(fn: ast.AST, aliases) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in aliases:
                return True
            if isinstance(f, ast.Attribute) and f.attr == GATE:
                return True
    return False


def scan_file(path: str):
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [(path, e.lineno or 0, "<syntax>", f"파싱 실패: {e}")]
    lines = src.splitlines()
    aliases = _gate_aliases(tree)
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        reads = [n for n in ast.walk(fn) if _reads_items(n)]
        if not reads:
            continue
        # 함수 안 지역 import 별칭도 인정
        local = set(aliases) | _gate_aliases(fn)
        if _calls_gate(fn, local):
            continue
        for n in reads:
            ln = getattr(n, "lineno", fn.lineno)
            text = lines[ln - 1] if 0 < ln <= len(lines) else ""
            if "items-ok:" in text and text.split("items-ok:", 1)[1].strip():
                continue
            out.append((path, ln, fn.name, "items 를 자기 눈으로 읽음 — coerce_items_payload 미경유"))
    return out


def main() -> int:
    if "--self-test" in sys.argv:
        import tempfile
        bad = "def f(tool_input):\n    x = tool_input.get('items')\n    return x\n"
        good = ("from common.currency import coerce_items_payload as _c\n"
                "def f(tool_input):\n    return _c(tool_input.get('items'))\n")
        ok_ = "def f(tool_input):\n    x = tool_input.get('items')  # items-ok: 시험\n    return x\n"
        with tempfile.TemporaryDirectory() as d:
            for name, s, expect in (("bad.py", bad, 1), ("good.py", good, 0), ("ok.py", ok_, 0)):
                p = os.path.join(d, name)
                open(p, "w").write(s)
                got = len(scan_file(p))
                if got != expect:
                    print(f"[items-injection] self-test FAIL {name}: {got} != {expect}")
                    return 1
        print("[items-injection] self-test OK")
        return 0
    viol = []
    for p in FILES:
        if p.endswith(os.path.join("backend", "common", "currency.py")):
            continue
        viol.extend(scan_file(p))
    if viol:
        print(f"[items-injection] ✗ {len(viol)}건 — items 파라미터를 손으로 읽는 자리:")
        for path, ln, fn, why in viol:
            print(f"  {os.path.relpath(path, ROOT)}:{ln} {fn}() — {why}")
        print("  → common.currency.coerce_items_payload 로 되읽거나, 정당하면 `# items-ok: <사유>`.")
        return 1
    print(f"[items-injection] OK ✓ ({len(FILES)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
