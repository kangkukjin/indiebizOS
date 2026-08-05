#!/usr/bin/env python3
"""공용 렌더 코어 가드 — 앱 표면 렌더 로직이 다시 둘로 갈라지는 것을 막는다.

배경: 같은 15 프리미티브를 데스크탑(React/TSX)과 원격·폰(파이썬 문자열 속 JS)이 이중 구현하고
있었고, 마크업은 어쩔 수 없어도 *로직*은 글자 그대로 번역된 사본이었다. 그 로직을
backend/static/app_render_core.js 하나로 모은 뒤, 이 가드가 세 가지를 지킨다:

  1. 코어의 ESM export 블록이 **파일의 마지막 블록**이고 그 위엔 export 가 없다
     (원격은 고전 <script> 로 인라인하므로 export 가 남으면 런처 전체가 SyntaxError).
  2. 두 표면 어느 쪽도 코어 이름을 **재정의하지 않는다**(사본 복귀 차단).
  3. 두 표면 조립이 코어를 **실제로 싣는다**(원격/폰 어느 한쪽만 빠지는 사고 차단).

사용: python3 scripts/check_render_core.py [--self-test]
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "backend", "static", "app_render_core.js")
EXPORT_MARKER = "/* --- ESM export"

# 코어 이름을 재정의하면 안 되는 소비자들 (데스크탑 TSX / 원격·폰 JS-in-Python)
CONSUMERS = [
    "frontend/src/components/GenericInstrument.tsx",
    "frontend/src/components/generic/manifest.ts",
    "frontend/src/components/generic/prims-basic.tsx",
    "frontend/src/components/generic/prims-edit.tsx",
    "frontend/src/components/generic/prims-map-calendar.tsx",
    "backend/launcher_web_render.py",
    "backend/launcher_app_appmode.py",
    "backend/launcher_app_common.py",
]

# 코어를 실제로 싣는 표면 조립 파일 (원격런처 / 폰네이티브)
SURFACES = ["backend/launcher_web_app.py", "backend/launcher_surface_phone.py"]


def core_export_names(text: str) -> list:
    """코어 파일 맨 끝 export 블록에서 이름 목록을 뽑는다(가드가 코어를 따라가게)."""
    idx = text.rfind(EXPORT_MARKER)
    if idx < 0:
        return []
    block = text[idx:]
    m = re.search(r"export\s*\{([^}]*)\}", block, re.S)
    if not m:
        return []
    return [n.strip() for n in m.group(1).split(",") if n.strip()]


def check(root: str = ROOT) -> list:
    issues = []
    core_path = os.path.join(root, "backend", "static", "app_render_core.js")
    if not os.path.isfile(core_path):
        return ["공용 렌더 코어 없음: backend/static/app_render_core.js"]
    with open(core_path, encoding="utf-8") as f:
        text = f.read()

    # ① export 블록은 마지막 하나뿐이어야 한다
    names = core_export_names(text)
    if not names:
        issues.append(
            "app_render_core.js 의 맨 끝 ESM export 블록을 찾지 못했습니다 — "
            f"'{EXPORT_MARKER}' 마커 + `export {{ ... }}` 형태를 유지하세요."
        )
    else:
        head = text[: text.rfind(EXPORT_MARKER)]
        stray = re.findall(r"^\s*export\s", head, re.M)
        if stray:
            issues.append(
                f"app_render_core.js 에 맨 끝 블록 밖의 `export` 가 {len(stray)}개 — 원격 런처는 "
                "이 파일을 고전 <script> 로 인라인하므로 SyntaxError 가 됩니다."
            )

    # ② 소비자가 코어 이름을 재정의하지 않는다
    for rel in CONSUMERS:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            body = f.read()
        for n in names:
            pats = (
                r"\bfunction\s+%s\s*\(" % re.escape(n),
                r"\b(?:const|let|var)\s+%s\s*=" % re.escape(n),
                r"\bexport\s+(?:function|const)\s+%s\b" % re.escape(n),
            )
            if any(re.search(p, body) for p in pats):
                issues.append(
                    f"{rel}: 공용 렌더 코어의 `{n}` 을 다시 정의하고 있습니다 — 로직은 "
                    "backend/static/app_render_core.js 하나가 정본입니다(이중 구현 복귀)."
                )

    # ③ 두 표면 모두 코어를 싣는다
    for rel in SURFACES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            body = f.read()
        if "LAUNCHER_CORE_JS" not in body:
            issues.append(
                f"{rel}: 표면 조립에 LAUNCHER_CORE_JS 가 없습니다 — 그 표면의 앱 탭은 "
                "jget/tpl 부터 전부 undefined 로 죽습니다."
            )
    return issues


def _self_test() -> int:
    """가드가 실제로 잡는지 — 임시 트리에 위반을 심어 확인."""
    import shutil
    import tempfile

    ok = True

    def expect(name, cond):
        nonlocal ok
        print(("  ok   " if cond else "  FAIL ") + name)
        if not cond:
            ok = False

    with tempfile.TemporaryDirectory() as td:
        for rel in ["backend/static", "frontend/src/components/generic"]:
            os.makedirs(os.path.join(td, rel), exist_ok=True)
        shutil.copy(CORE, os.path.join(td, "backend", "static", "app_render_core.js"))
        for rel in SURFACES:
            with open(os.path.join(td, rel), "w", encoding="utf-8") as f:
                f.write("LAUNCHER_CORE_JS\n")
        expect("깨끗한 트리 = 위반 0", check(td) == [])

        # 재정의 심기
        cpath = os.path.join(td, "frontend/src/components/generic/manifest.ts")
        with open(cpath, "w", encoding="utf-8") as f:
            f.write("export function jget(o, p) { return o; }\n")
        expect("재정의 검출", any("`jget`" in i for i in check(td)))
        os.remove(cpath)

        # 표면 누락 심기
        with open(os.path.join(td, SURFACES[1]), "w", encoding="utf-8") as f:
            f.write("# 코어 안 실음\n")
        expect("표면 누락 검출", any("LAUNCHER_CORE_JS" in i for i in check(td)))
        with open(os.path.join(td, SURFACES[1]), "w", encoding="utf-8") as f:
            f.write("LAUNCHER_CORE_JS\n")

        # 떠도는 export 심기
        cj = os.path.join(td, "backend", "static", "app_render_core.js")
        with open(cj, encoding="utf-8") as f:
            body = f.read()
        with open(cj, "w", encoding="utf-8") as f:
            f.write("export function stray(){}\n" + body)
        expect("맨 끝 블록 밖 export 검출", any("밖의 `export`" in i for i in check(td)))

    print("자기검증 통과" if ok else "자기검증 실패")
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return _self_test()
    issues = check()
    for i in issues:
        print("  ✗ " + i)
    if issues:
        print(f"\n공용 렌더 코어 가드: 위반 {len(issues)}건")
        return 1
    print("공용 렌더 코어 가드: 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
