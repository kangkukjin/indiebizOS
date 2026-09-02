#!/usr/bin/env python3
"""검수↔실행 정합 관문 — dry-run(`/ibl/validate`)의 **거짓 빨강** 탄생 차단.

왜: 검수기가 파서의 개정을 모르면 실행되는 문장에 `valid:false` 가 난다. 조종실은
번역→**검수**→실행이라 거짓 빨강은 곧 멀쩡한 문장의 차단이고, 상상훈련의 계측기이기도
하다. 같은 속이 두 회차에서 났다(가이드 §4-3 밭 이관 규약 — 두 번째 발견은 census 로):

  · B49-1 (49회차) `do` 컨테이너 재파싱이 바깥 `$변수` 자리표를 몰라 죽었다
  · B53-1 (53회차) `$변수[.경로] >>` 파이프 머리(08-27)·`$변수 & $변수` 병렬 분기(09-01)를
    검수기가 빈 액션으로 읽어 "노드가 지정되지 않았습니다" — 실행은 정상

부류의 정의(기계로 셀 수 있다): **파싱되고, 등장하는 액션이 전부 사전에 실존하는데,
검수가 valid:false 를 내는 문장.** 사전에 없는 액션(은퇴 어휘·다른 몸)의 빨강은 참이라
관문 밖이다 — 그래서 손으로 고른 오류 문구 목록이 필요 없다.

무엇을 넣나:
  [A] 카탈로그 fixture 전수 (`data/ibl_nodes.yaml` 의 action.fixture · ops.fixture)
  [B] 교재 코드 블록 (`data/common_prompts/fragments/12_ibl_only.md`, WRONG 예시 블록 제외)
  [C] `--corpus` : 해마 코퍼스 `ibl_examples` 전수 (기본은 보고만, `--strict` 면 차단)

사용: python3 scripts/check_validate_parity.py [--corpus] [--strict] [--verbose]
      (시스템 python 이면 .venv 로 스스로 재실행한다 — 검수기는 백엔드 모듈이라.)
실패 시 exit 1.
"""
import os
import sys
import re
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")


def _reexec_in_venv() -> None:
    if os.environ.get("_CVP_REEXEC"):
        return
    if os.path.exists(VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(VENV_PY):
        os.environ["_CVP_REEXEC"] = "1"
        os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])


_reexec_in_venv()
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))
import boot_paths  # noqa: E402,F401

try:
    from api_ibl import validate_code          # noqa: E402
    from ibl_parser import parse, IBLSyntaxError  # noqa: E402
    from ibl_engine import get_node_actions    # noqa: E402
except Exception as e:  # 관문 고장 = 무검사가 아니라 실패 (fail-closed)
    print(f"[validate-parity] ✗ 검수기 로드 실패 — 관문을 돌릴 수 없습니다: {e}")
    sys.exit(1)

TEXTBOOK = os.path.join(ROOT, "data", "common_prompts", "fragments", "12_ibl_only.md")
NODES = os.path.join(ROOT, "data", "ibl_nodes.yaml")
CORPUS = os.path.join(ROOT, "data", "ibl_usage.db")


def fixtures():
    import yaml
    with open(NODES, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    out = []
    for node, nd in (d.get("nodes") or {}).items():
        for act, ad in (nd.get("actions") or {}).items():
            if not isinstance(ad, dict):
                continue
            fx = ad.get("fixture")
            if isinstance(fx, str) and fx.strip():
                out.append((f"fixture {node}:{act}", fx.strip()))
            for op, ofx in ((ad.get("ops") or {}).get("fixture") or {}).items():
                if isinstance(ofx, str) and ofx.strip():
                    out.append((f"fixture {node}:{act}.{op}", ofx.strip()))
    return out


_SKIP_LINE = ("execute_ibl(", "run_command(", "…", "...", "read_guide(")


def textbook_blocks():
    if not os.path.exists(TEXTBOOK):
        return []
    text = open(TEXTBOOK, encoding="utf-8").read()
    out = []
    for i, m in enumerate(re.finditer(r"```[^\n]*\n(.*?)```", text, re.S)):
        body = m.group(1)
        if "WRONG" in body:
            continue
        lines = []
        for ln in body.splitlines():
            s = ln.rstrip()
            if not s.strip():
                continue
            if any(t in s for t in _SKIP_LINE):
                continue
            lines.append(s)
        code = "\n".join(lines).strip()
        if code:
            out.append((f"textbook block#{i + 1}", code))
    return out


def corpus():
    import sqlite3
    if not os.path.exists(CORPUS):
        return []
    conn = sqlite3.connect(CORPUS)
    try:
        rows = conn.execute("SELECT id, ibl_code FROM ibl_examples").fetchall()
    finally:
        conn.close()
    return [(f"corpus#{r[0]}", r[1]) for r in rows if isinstance(r[1], str) and r[1].strip()]


def _all_actions_known(steps) -> bool:
    """검수 steps 에 등장한 (node, action) 이 전부 사전에 있는가 — 없으면 그 빨강은 참."""
    for st in steps or []:
        node, act = st.get("node") or "", st.get("action") or ""
        if st.get("kind") in ("assign", "var", "block") or node in ("assign", "var"):
            continue
        if not node:
            continue                      # 이름 없는 step = 검수기가 구조를 못 읽은 것 → 거짓 빨강 후보
        acts = get_node_actions(node)
        if not acts or act not in acts:
            return False
    return True


def check(items, strict: bool, verbose: bool):
    bad = []
    seen = 0
    for label, code in items:
        try:
            parse(code)
        except IBLSyntaxError:
            continue                      # 문법 오류는 검수의 몫이 아니다(파서가 이미 정직 거절)
        except Exception:
            continue
        seen += 1
        try:
            v = validate_code(code)
        except Exception as e:
            bad.append((label, code, f"검수기 예외: {e}"))
            continue
        if v.get("valid"):
            continue
        if v.get("syntax_error"):
            continue
        if not _all_actions_known(v.get("steps")):
            continue                      # 사전에 없는 액션 — 참인 빨강
        errs = [f"[{s.get('node')}:{s.get('action')}] {s.get('error')}"
                for s in (v.get("steps") or []) if s.get("valid") is False]
        bad.append((label, code, " / ".join(errs) or "(오류문 없음)"))
    return seen, bad


def main() -> int:
    args = set(sys.argv[1:])
    strict = "--strict" in args
    verbose = "--verbose" in args
    if "--self-test" in args:
        s, b = check([("self", "$q = [self:time]\n$q >> [table:take]{n: 1}"),
                      ("self2", "$a = [self:time]\n$b = [self:time]\n$a & $b >> [table:union]")],
                     True, True)
        print(f"[validate-parity] self-test: {s} checked, {len(b)} false-red")
        return 1 if b else 0
    total_bad = []
    for name, items, blocking in (("fixture", fixtures(), True),
                                  ("textbook", textbook_blocks(), True),
                                  ("corpus", corpus() if "--corpus" in args else [], strict)):
        if not items:
            continue
        seen, bad = check(items, strict, verbose)
        print(f"[validate-parity] {name}: {seen} checked, {len(bad)} false-red"
              + ("" if blocking else " (보고만)"))
        for label, code, why in bad:
            if blocking or verbose:
                print(f"  ✗ {label}: {why}")
                if verbose:
                    print("     " + code.replace("\n", "\n     ")[:400])
        if blocking:
            total_bad.extend(bad)
    if total_bad:
        print(f"[validate-parity] ✗ 거짓 빨강 {len(total_bad)}건 — 검수기가 파서 개정을 모릅니다"
              " (backend/surface/api_ibl.py validate_code 의 _walk 에 그 모양을 가르치세요).")
        return 1
    print("[validate-parity] OK ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
