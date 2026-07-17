#!/usr/bin/env python3
"""의식 출력 스키마 이름 드리프트 감사 — 생산자(프롬프트) ↔ 소비처(코드) 정합.

[[project_name_drift_audit]]의 4번째 층. IBL 액션명·tool명·함수명 감사가 *어휘*를
보듯, 이 감사는 **의식 에이전트 출력 dict의 키**를 본다. 무성음 누수(silent leak) 부류:
프롬프트가 `capability_focus`로 개명됐는데 융합 함수는 옛 `ibl_focus`를 읽어, highlight_actions·
hint가 사용자 명령 융합에서 조용히 사라진 2026-07-06 버그가 정확히 이 층에서 났다.

원리 (드리프트 = 생산≠소비):
  - 생산자 = consciousness_prompt.md 응답 형식 JSON 블록. **단일 진실 소스.**
  - 소비처 = consciousness_output(및 그 별칭 co / capability_focus 하위 dict)의 키 읽기.
  - 소비처가 읽는 키는 반드시 생산자가 내는 키(∪ 승인된 레거시 별칭)여야 한다.
    그렇지 않으면 그 읽기는 *항상 빈 값* → 조언이 조용히 버려진다.

정적 검사만 한다(백엔드 불필요). AST 1-hop: 함수 안에서
  cons = {consciousness_output 파라미터, `X = consciousness_output ...` 로 바인딩된 X}
  focus = {`Y = <cons>.get("capability_focus"|"ibl_focus") ...` 로 바인딩된 Y}
그 위의 .get("KEY") / ["KEY"] 문자열 키만 수집 → 프레즌스 dict(cap.get("micros") 등) 오탐 회피.

사용:  python3 scripts/consciousness_schema_check.py
종료코드 0=정합, 1=드리프트(소비처가 미선언 키를 읽음).
매뉴얼 §이름 드리프트 감사 카덴스에 합류(주 1회 / 의식 프롬프트 개명 직후).
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT = ROOT / "data" / "common_prompts" / "consciousness_prompt.md"

# 소비처로 스캔할 파일 — 의식 출력을 읽는 코드. 새 소비처 추가 시 여기에 등록.
CONSUMER_FILES = [
    ROOT / "backend" / "prompt_builder.py",
    ROOT / "backend" / "agent_cognitive.py",
    # 2026-07-17 모듈화: agent_cognitive 분할로 의식 출력 소비 코드가 이동한 파일들
    ROOT / "backend" / "cognitive_consciousness.py",
    ROOT / "backend" / "cognitive_eval.py",
]

# capability_focus 하위 dict를 바인딩하는 .get 키(별칭 포함). 새 별칭은 여기 추가.
FOCUS_GETTERS = {"capability_focus", "ibl_focus"}

# 승인된 레거시 별칭 → 정본. 폴백으로 관용하되 경고로 남겨 제거를 유도.
LEGACY_ALIASES = {"ibl_focus": "capability_focus"}


def load_producer_schema():
    """프롬프트 응답 형식 JSON 블록에서 최상위·focus 키 집합을 뽑는다."""
    text = PROMPT.read_text(encoding="utf-8")
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        print(f"[FAIL] 프롬프트 응답 형식 JSON 블록을 찾지 못함: {PROMPT}")
        sys.exit(2)
    schema = json.loads(m.group(1))
    top = set(schema.keys())
    focus = set()
    cap = schema.get("capability_focus")
    if isinstance(cap, dict):
        focus = set(cap.keys())
    return top, focus


def _str_key(node):
    """.get("K") 첫 인자 또는 ["K"] 아래첨자의 문자열 상수 키를 반환(아니면 None)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "get" and node.args:
        a = node.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return node.func.value, a.value  # (수신 노드, 키)
    if isinstance(node, ast.Subscript):
        s = node.slice
        if isinstance(s, ast.Constant) and isinstance(s.value, str):
            return node.value, s.value
    return None


def _name_of(node):
    return node.id if isinstance(node, ast.Name) else None


def scan_consumer(path):
    """(top_reads, focus_reads) — 각 [(key, lineno)]. cons/ focus 수신에 걸린 키만."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top_reads, focus_reads = [], []

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cons = {a.arg for a in fn.args.args if a.arg == "consciousness_output"}
        focus = set()
        # 1-hop 바인딩 수집 (정의 순서대로)
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = _name_of(node.targets[0])
                if not tgt:
                    continue
                val = node.value
                # X = consciousness_output ...  /  X = <cons> or {}
                names = [_name_of(n) for n in ast.walk(val) if isinstance(n, ast.Name)]
                if "consciousness_output" in names or (cons & set(names)):
                    # focus getter인지 먼저 본다
                    sk = _str_key(val if isinstance(val, (ast.Call, ast.Subscript))
                                  else getattr(val, "values", [None])[0] if isinstance(val, ast.BoolOp) else None)
                    bound_focus = False
                    if isinstance(val, ast.BoolOp):  # co.get("capability_focus") or co.get("ibl_focus") or {}
                        for v in val.values:
                            k = _str_key(v)
                            if k and k[1] in FOCUS_GETTERS:
                                bound_focus = True
                    else:
                        k = _str_key(val)
                        if k and k[1] in FOCUS_GETTERS:
                            bound_focus = True
                    if bound_focus:
                        focus.add(tgt)
                    else:
                        cons.add(tgt)

        # 키 읽기 수집
        for node in ast.walk(fn):
            k = _str_key(node)
            if not k:
                continue
            recv, key = k
            rname = _name_of(recv)
            if rname in cons and key not in FOCUS_GETTERS:
                top_reads.append((key, node.lineno))
            elif rname in focus:
                focus_reads.append((key, node.lineno))
    return top_reads, focus_reads


def main():
    top_schema, focus_schema = load_producer_schema()
    print(f"[생산자] {PROMPT.name} 최상위 키: {sorted(top_schema)}")
    print(f"[생산자] capability_focus 하위 키: {sorted(focus_schema)}")
    print()

    drift, legacy = [], []
    for path in CONSUMER_FILES:
        if not path.exists():
            print(f"[SKIP] 없음: {path}")
            continue
        top_reads, focus_reads = scan_consumer(path)
        for key, ln in top_reads:
            if key in LEGACY_ALIASES:
                legacy.append((path.name, ln, key, LEGACY_ALIASES[key]))
            elif key not in top_schema:
                drift.append((path.name, ln, "top", key))
        for key, ln in focus_reads:
            if key not in focus_schema:
                drift.append((path.name, ln, "focus", key))

    if legacy:
        print("── 레거시 별칭(관용, 제거 권고) ──")
        for f, ln, key, canon in legacy:
            print(f"  {f}:{ln}  '{key}' → 정본 '{canon}'")
        print()

    if drift:
        print("── 드리프트 (소비처가 미선언 키를 읽음 = 조언 무성음 누락) ──")
        for f, ln, layer, key in drift:
            print(f"  ✗ {f}:{ln}  [{layer}] '{key}' — 프롬프트가 내지 않는 키")
        print(f"\n[FAIL] 드리프트 {len(drift)}건. 소비처를 정본 키로 정렬하거나 프롬프트에 키를 선언하라.")
        return 1

    print("[OK] 의식 출력 스키마 정합 — 소비처가 읽는 키가 모두 생산자 선언에 속함.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
