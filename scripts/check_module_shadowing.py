#!/usr/bin/env python3
"""패키지 모듈명 그림자 검사 — 이름 충돌이 sys.modules 를 오염시키는 부류 차단.

배경(2026-08-05 감사에서 부류 확정): 도구 패키지 다수가 자기 폴더를
`sys.path.insert(0, ...)` 로 맨 앞에 넣는다. 그 폴더의 평평한 *.py 이름이
backend 최상위 모듈과 겹치면, 먼저 import 된 쪽이 `sys.modules` 를 차지해
프로세스 전체가 엉뚱한 모듈을 본다.

실제 사건: cctv 패키지의 옛 `common.py` 가 `sys.modules["common"]` 을 덮어
backend/common(공유 유틸)이 import 불가가 됐고, location-services 등이
공유 대신 로컬 복사(지오코더 3벌, curl_cffi 6벌…)를 만들며 우회했다.
급성 증상은 `cctv_common.py` 개명으로 치료됐지만(잔존 복붙은 별도 정리),
부류를 막는 가드가 없어 다음 패키지가 언제든 재발시킬 수 있었다 — 이 스크립트가 그 가드.

검사 대상: data/packages/installed/tools/*/ 의 최상위 *.py 스템과 최상위 디렉토리.
  (extensions/ 는 백엔드 코어 모듈의 사본이 설계상 동명이라 제외.)
충돌 기준:
  1) backend/*.py 스템 + backend 하위 패키지 이름(common, channels, drivers, providers)
  2) 파이썬 표준 라이브러리 이름(sys.stdlib_module_names) — json.py 하나가 전 프로세스를 죽인다
예외: handler / __init__ / tool_* (패키지 관습 이름, backend 와 안 겹침이 위에서 보장됨).

사용: python3 scripts/check_module_shadowing.py            # 저장소 검사
      python3 scripts/check_module_shadowing.py --self-test # 가드 자기 검증
의존성 0 (stdlib만). 실패 시 exit 1.
"""
import os
import sys
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BACKEND_SUBPACKAGES = {"common", "channels", "drivers", "providers"}


def backend_names(root: str) -> set:
    names = set(BACKEND_SUBPACKAGES)
    for f in glob.glob(os.path.join(root, "backend", "**", "*.py"), recursive=True):
        names.add(os.path.splitext(os.path.basename(f))[0])
    return names


def stdlib_names() -> set:
    # 3.10+ 전제 (이 저장소는 3.12+). 없으면 빈 집합으로 조용히 축소하지 말고 명시 실패.
    return set(sys.stdlib_module_names)


def scan(root: str) -> list:
    reserved_backend = backend_names(root)
    reserved_stdlib = stdlib_names()
    issues = []
    for pkgdir in sorted(glob.glob(os.path.join(root, "data/packages/installed/tools/*/"))):
        pkg = os.path.basename(os.path.dirname(pkgdir))
        for entry in sorted(os.listdir(pkgdir)):
            path = os.path.join(pkgdir, entry)
            if os.path.isfile(path) and entry.endswith(".py"):
                stem = entry[:-3]
            elif (os.path.isdir(path) and not entry.startswith((".", "__"))
                  and glob.glob(os.path.join(path, "*.py"))):
                # 디렉토리는 .py 를 품어야 그림자 위험(순수 자산 폴더는 제외 —
                # public-files/site 처럼 정적 파일만 담은 폴더가 오탐되지 않게).
                stem = entry
            else:
                continue
            if stem in ("handler", "__init__") or stem.startswith("tool_"):
                continue
            if stem in reserved_backend:
                issues.append(f"{pkg}/{entry}: backend 모듈 '{stem}' 을 그림자화 "
                              f"(sys.path 선순위에 따라 프로세스 전체 오염)")
            elif stem in reserved_stdlib:
                issues.append(f"{pkg}/{entry}: 표준 라이브러리 '{stem}' 을 그림자화")
    return issues


def self_test() -> bool:
    """가짜 패키지 트리로 검출/통과 양방향 확인."""
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        # 최소 backend
        os.makedirs(os.path.join(tmp, "backend"))
        open(os.path.join(tmp, "backend", "runtime_utils.py"), "w").close()
        base = os.path.join(tmp, "data/packages/installed/tools")
        # 위반 1: backend 스템 그림자
        os.makedirs(os.path.join(base, "bad1"))
        open(os.path.join(base, "bad1", "runtime_utils.py"), "w").close()
        # 위반 2: backend 하위 패키지 이름의 디렉토리(.py 보유)
        os.makedirs(os.path.join(base, "bad2", "common"))
        open(os.path.join(base, "bad2", "common", "x.py"), "w").close()
        # 위반 3: stdlib 그림자
        os.makedirs(os.path.join(base, "bad3"))
        open(os.path.join(base, "bad3", "json.py"), "w").close()
        # 정상: 접두 관습·비충돌 이름
        os.makedirs(os.path.join(base, "good"))
        for n in ("handler.py", "tool_watch.py", "cctv_common.py"):
            open(os.path.join(base, "good", n), "w").close()
        # 정상: 순수 자산 디렉토리(.py 없음)는 stdlib 동명이어도 통과
        os.makedirs(os.path.join(base, "good", "site"))
        open(os.path.join(base, "good", "site", "index.html"), "w").close()
        issues = scan(tmp)
        hits = {i.split(":")[0] for i in issues}
        expect = {"bad1/runtime_utils.py", "bad2/common", "bad3/json.py"}
        if hits != expect:
            print(f"✗ self-test: 기대 {expect} vs 실제 {hits}")
            ok = False
    print("✓ self-test 통과" if ok else "✗ self-test 실패")
    return ok


def main() -> int:
    if "--self-test" in sys.argv:
        return 0 if self_test() else 1
    issues = scan(ROOT)
    if issues:
        print(f"✗ 모듈 그림자 위반 {len(issues)}건:")
        for i in issues:
            print(f"  - {i}")
        print("\n수리: 패키지 모듈을 '<패키지>_<이름>.py' 식으로 개명 (예: common.py → cctv_common.py)")
        return 1
    print("✓ 모듈 그림자 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
