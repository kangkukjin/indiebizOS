#!/usr/bin/env python3
"""추적 중인데 .gitignore 가 무시하라는 파일이 있으면 실패시킨다 (2026-08-24 신설).

배경: `.gitignore` 는 **이미 추적 중인 파일을 되돌리지 못한다.** 그래서 규칙을 나중에
세운 부류(런타임 캐시·일회성 백업·모델 카드·굴러다니는 스크린샷)는 규칙이 생긴 뒤에도
계속 커밋되며, diff 가 타임스탬프 한 줄뿐인 소음 커밋으로 남는다. 실측(2026-08-24):
investment 종목/기업 코드 캐시가 22·17회 커밋되어 히스토리에 6.7MB, `data/_backups/`
40파일(규약이 "절대 커밋 금지"라 못박은 폴더)이 추적 중이었다.

가드의 오라클 = git 자신. `git ls-files -i -c --exclude-standard` 는 "추적 중 ∧ 무시
대상" 교집합을 기계가 계산해준다. **동결 목록이 없다** — 예외를 두고 싶으면 코드가
아니라 `.gitignore` 에 `!` 부정 규칙으로 선언하라(그래야 `git add -A` 도 같은 판정을
쓴다). 그 결과 이 저장소에서 "무엇이 저장소에 속하는가"의 단일 진실은 `.gitignore`
하나가 된다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


# 저장소 루트에 굴러다니는 SQLite 파일(추적 여부 무관). 2026-09-02 실측: 이름 없는 메모리 호출이
# 루트에 memory_None.db 를 만들었다 — 무시 규칙은 커밋만 막고 존재 자체는 못 본다.
_ROOT_LITTER_GLOBS = ("*.db", "*.db-wal", "*.db-shm", "*.db-journal", "*.sqlite", "*.sqlite3")


def root_litter() -> list[str]:
    return sorted(p.name for g in _ROOT_LITTER_GLOBS for p in _ROOT.glob(g) if p.is_file())


def tracked_but_ignored() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-i", "-c", "--exclude-standard", "-z"],
        cwd=_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def main() -> int:
    litter = root_litter()
    if litter:
        print(f"❌ 저장소 루트에 DB 파일 {len(litter)}개 — 이름 없는 호출의 부산물이다(memory_None.db 부류):\n")
        for p in litter:
            print(f"  - {p}")
        print("\n내용을 확인해 정본 DB(data/ 또는 projects/<id>/)로 옮긴 뒤 지워라. 루트는 DB 자리가 아니다.")
        return 1

    leaks = tracked_but_ignored()
    if not leaks:
        print("✅ 추적 ∩ 무시 = 0 — 저장소에 생산물·런타임 부산물이 없다.")
        return 0

    print(f"❌ 추적 중인데 .gitignore 가 무시하라는 파일 {len(leaks)}개:\n")
    for p in leaks[:40]:
        print(f"  - {p}")
    if len(leaks) > 40:
        print(f"  … 외 {len(leaks) - 40}개")
    print(
        "\n둘 중 하나로 닫아라:\n"
        "  ① 생산물·부산물이 맞다  → git rm --cached <경로>   (워킹트리는 남는다)\n"
        "  ② 저장소에 속하는 소스다 → .gitignore 에 `!` 부정 규칙 추가\n"
        "     (코드에 예외 목록을 만들지 말 것 — git add -A 가 그 목록을 읽지 않는다)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
