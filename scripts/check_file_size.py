#!/usr/bin/env python3
"""파일 크기 규칙(1500줄) 가드 — 게이트 없는 규칙은 선호일 뿐이라는 실증에서 신설.

배경(2026-08-05 감사): CLAUDE.md 의 1500줄 규칙은 2026-07 모듈화로 한 번 충족됐지만
줄 수를 세는 가드가 없어 3주 만에 재위반했다(api_portal.py 가 1903줄까지 자랐다 —
2026-08-05 감사 ⑨ 에서 5모듈로 분할하고 여기 BASELINE 에서 삭제해 재진입을 봉인). 17개 가드가
있는 저장소에서 이 규칙만 게이트가 없었다 — 이 스크립트가 그 게이트.

정책:
  - 신규 위반 차단: BASELINE 에 없는 파일이 1500줄을 넘으면 실패.
  - 래칫(악화 금지): BASELINE 파일이 기록된 줄 수를 넘어 자라면 실패.
    (분할해서 1500 이하로 내려가면 BASELINE 에서 그 줄을 지울 것 — 재진입 불가.)
  - BASELINE 은 부채 목록이지 면허가 아니다. 항목마다 분할 계획이 문서화된 곳을 적는다.

사용: python3 scripts/check_file_size.py
      python3 scripts/check_file_size.py --list   # 상위 20개 큰 파일 (계기판)
의존성 0. 실패 시 exit 1.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 1500

SCAN_PATTERNS = [
    "backend/**/*.py",
    "data/packages/installed/**/*.py",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.tsx",
    "frontend/electron/*.js",
    "scripts/*.py",
]
EXCLUDE_SUBSTR = ("node_modules", "__pycache__", "/pylibs/", "/build/", "/dist/",
                  "backend/static/")

# 기존 부채 동결(2026-08-05 실측). 값 = 그 시점 줄 수(래칫 상한).
# 분할 완료 시 항목 삭제. 새 항목 추가는 금지 — 추가하고 싶다는 충동이 곧 분할 신호.
BASELINE = {
    "backend/surface/api_nas.py": 1515,
    "data/packages/installed/tools/data-ops/handler.py": 1711,   # 통화 소비자 정본 — 최우선 분할 대상
    "data/packages/installed/tools/youtube/tool_youtube.py": 1570,
    "frontend/electron/main.js": 1990,
}


def count_lines(path: str) -> int:
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def scan(root: str):
    seen = set()
    for pat in SCAN_PATTERNS:
        for f in glob.glob(os.path.join(root, pat), recursive=True):
            rel = os.path.relpath(f, root)
            if any(e in ("/" + rel) or e in rel for e in EXCLUDE_SUBSTR):
                continue
            if rel in seen or not os.path.isfile(f):
                continue
            seen.add(rel)
            yield rel, count_lines(f)


def main() -> int:
    sizes = dict(scan(ROOT))
    if "--list" in sys.argv:
        for rel, n in sorted(sizes.items(), key=lambda x: -x[1])[:20]:
            mark = "★" if n > LIMIT else " "
            print(f"{mark} {n:5d}  {rel}")
        return 0

    issues = []
    for rel, n in sorted(sizes.items()):
        cap = BASELINE.get(rel)
        if cap is not None:
            if n > cap:
                issues.append(f"{rel}: {n}줄 — 래칫 상한 {cap} 초과(부채 파일은 더 자랄 수 없음. "
                              f"이번 변경분을 새 모듈로 분리할 것)")
        elif n > LIMIT:
            issues.append(f"{rel}: {n}줄 — 1500줄 규칙 위반(신규). 모듈로 분할할 것")
    # 부채 청산 감지: BASELINE 항목이 한계 아래로 내려갔으면 목록 정리를 안내(실패 아님)
    for rel, cap in BASELINE.items():
        n = sizes.get(rel)
        if n is not None and n <= LIMIT:
            print(f"ℹ {rel} 이 {n}줄로 내려옴 — BASELINE 에서 제거하세요(재진입 봉인)")

    if issues:
        print(f"✗ 파일 크기 위반 {len(issues)}건:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print(f"✓ 파일 크기 OK (한도 {LIMIT}줄, 부채 {len(BASELINE)}건 동결)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
