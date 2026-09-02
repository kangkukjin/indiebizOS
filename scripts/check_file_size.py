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

# 기존 부채 동결. 값 = 그 시점 줄 수(래칫 상한).
# 분할 완료 시 항목 삭제. 새 항목 추가는 금지 — 추가하고 싶다는 충동이 곧 분할 신호.
# **2026-08-06 전액 상환**: 마지막 4건(api_nas·data-ops·tool_youtube·main.js)까지 분할해
# 부채 0. 이제 이 가드는 예외 없는 한도다 — 1500줄을 넘기려면 먼저 쪼개야 한다.
BASELINE = {}

# ── 두 번째 규칙 집합: 가이드 바이트 예산 (2026-09-02, 사용자 승인) ─────────────────────
# 가이드는 절차 기억이라 자라기만 했다(79KB 까지) — 1500줄 규칙과 같은 논리로 관문이 집행한다.
# 예산 값은 data/lifecycle_policy.yaml(guide_budget_bytes) 이 정본이고 여기는 읽기만 한다.
# 초과분은 삭제가 아니라 압축·분할로 맞춘다(야간 guide_downscale 이 예산 초과분부터 압축).
GUIDE_PATTERNS = ["data/guides/*.md"]
GUIDE_BUDGET_DEFAULT = 36000
GUIDE_BASELINE = {}   # 부채 래칫(악화 금지). 예산 안으로 내려오면 항목 삭제 — 재진입 봉인.


def guide_budget() -> int:
    try:
        import yaml
        d = yaml.safe_load(open(os.path.join(ROOT, "data", "lifecycle_policy.yaml"), encoding="utf-8")) or {}
        return int(d.get("guide_budget_bytes") or GUIDE_BUDGET_DEFAULT)
    except Exception:
        # yaml 없이도 관문은 선다 — 한 줄 파싱 폴백
        try:
            for ln in open(os.path.join(ROOT, "data", "lifecycle_policy.yaml"), encoding="utf-8"):
                if ln.strip().startswith("guide_budget_bytes"):
                    return int(ln.split(":", 1)[1].split("#")[0].strip())
        except Exception:
            pass
        return GUIDE_BUDGET_DEFAULT


def scan_guides(root: str):
    for pat in GUIDE_PATTERNS:
        for f in sorted(glob.glob(os.path.join(root, pat))):
            rel = os.path.relpath(f, root)
            if os.path.isfile(f):
                yield rel, os.path.getsize(f)


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
        print("— 가이드(바이트) —")

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

    # 가이드 예산 — 두 번째 규칙 집합(파일별 전개 X: 규칙 하나·glob 하나)
    budget = guide_budget()
    gsizes = dict(scan_guides(ROOT))
    if "--list" in sys.argv:
        for rel, n in sorted(gsizes.items(), key=lambda x: -x[1])[:10]:
            mark = "★" if n > budget else " "
            print(f"{mark} {n:6d}B {rel}")
        return 0
    for rel, n in sorted(gsizes.items()):
        cap = GUIDE_BASELINE.get(rel)
        if cap is not None:
            if n > cap:
                issues.append(f"{rel}: {n}B — 가이드 래칫 상한 {cap}B 초과(부채 가이드는 더 자랄 수 없음. 압축·분할할 것)")
        elif n > budget:
            issues.append(f"{rel}: {n}B — 가이드 예산 {budget}B 초과(신규). 압축(자리표 골격·실측 기록 이관)"
                          f" 또는 분할할 것 — 삭제로 맞추지 말 것")
    for rel, cap in GUIDE_BASELINE.items():
        n = gsizes.get(rel)
        if n is not None and n <= budget:
            print(f"ℹ {rel} 이 {n}B 로 내려옴 — GUIDE_BASELINE 에서 제거하세요(재진입 봉인)")

    if issues:
        print(f"✗ 파일 크기 위반 {len(issues)}건:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print(f"✓ 파일 크기 OK (한도 {LIMIT}줄, 부채 {len(BASELINE)}건 동결 · 가이드 예산 {budget}B, "
          f"{len(gsizes)}개 안)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
