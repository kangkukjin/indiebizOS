#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""에디션/로케일에 맞춰 이 몸의 활성 원장을 공통 생명주기 함수로 갱신한다.

보유 파일과 사전집은 유지한다. 필수 묶음은 vocabulary_policy.yaml로 보호한다.
--list 또는 --dry-run은 변경 없이 선택 결과만 출력한다.
사용: python3 scripts/apply_edition.py --edition standard --locale universal
"""

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLED_TOOLS = "data/packages/installed/tools"
NOT_INSTALLED_TOOLS = "data/packages/not_installed/tools"

# apply_edition 이 not_installed 로 내보낸 팩에만 남기는 마커. 재실행으로 더 넓은
# 에디션을 고르면 "우리가 내보낸" 팩만 되돌린다 — 출하 시 이미 not_installed 였던
# 큐레이션(house-designer, publishing 등)은 마커가 없어 부활하지 않는다.
_PARK_MARKER = ".edition_parked"

# 표준 필터를 통과하더라도 절대 not_installed 로 내보내지 않는 코어 도구.
# (현재는 둘 다 keyless∧light 라 표준에 포함되지만, 더 마른 에디션이 생겨도 안전하게.)
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from vocabulary_policy import required_packages  # noqa: E402

_PROTECTED = required_packages(ROOT)

EDITIONS = ("standard", "full")


def _load_build_module():
    """build_ibl_nodes.py 를 모듈로 로드(derive_package_meta 재사용 — 단일 진실 소스)."""
    path = ROOT / "scripts" / "build_ibl_nodes.py"
    spec = importlib.util.spec_from_file_location("build_ibl_nodes", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def derive_tool_meta():
    """installed/tools + not_installed/tools 전체의 needs_key/weight/locale 도출.

    build 의 derive_package_meta 를 재사용하되 스캔 범위만 두 tools 디렉토리로 좁힌다
    (extensions 는 제외 → 이동 후보에서 원천 배제)."""
    build = _load_build_module()
    meta = build.derive_package_meta(
        ROOT, package_dirs=[INSTALLED_TOOLS, NOT_INSTALLED_TOOLS]
    )
    return meta["packages"]


def in_edition(m: dict, edition: str) -> bool:
    if edition == "full":
        return True
    # standard: 외부 키 불요 ∧ 가벼움
    return not m.get("needs_key") and m.get("weight") == "light"


def in_locale(m: dict, locale: str) -> bool:
    if locale in (None, "all"):
        return True
    if m.get("locale") == "universal":
        return True
    return m.get("locale") == locale


def _tool_location(pkg: str):
    """pkg 가 현재 installed / not_installed / 없음 중 어디인지."""
    from vocabulary_state import inventory, is_active
    if pkg in inventory(ROOT)["packages"]:
        return "installed" if is_active(pkg, ROOT) else "not_installed"
    return None


def plan_moves(meta: dict, edition: str, locale: str):
    """반환: (to_remove, to_install, keep) — 각 pkg 이름 리스트."""
    to_remove, to_install, keep = [], [], []
    for pkg in sorted(meta):
        loc = _tool_location(pkg)
        if loc is None:
            continue  # extensions 등 — 이동 대상 아님
        desired = in_edition(meta[pkg], edition) and in_locale(meta[pkg], locale)
        if pkg in _PROTECTED:
            desired = True  # 코어 도구는 항상 설치 유지
        parked_by_us = (ROOT / NOT_INSTALLED_TOOLS / pkg / _PARK_MARKER).exists()
        if desired and loc == "not_installed":
            # 우리가 내보낸 팩만 되돌린다(출하 not_installed 큐레이션은 보존).
            to_install.append(pkg)
        elif not desired and loc == "installed":
            to_remove.append(pkg)
        else:
            keep.append(pkg)
    return to_remove, to_install, keep


def _move(pkg: str, src_root: str, dst_root: str, park: bool):
    """호환 진입점: 폴더를 옮기지 않고 공통 생명주기로 선택을 바꾼다."""
    from boot_common import wire_local_subsystems
    from vocabulary_lifecycle import set_package_active, HUMAN_AUTHORITY
    wire_local_subsystems()
    result = set_package_active(pkg, not park, authority=HUMAN_AUTHORITY)
    if not result.get("success"):
        raise RuntimeError(result.get("message", "어휘 선택 변경 실패"))


def rebuild():
    """스위치는 빌드하지 않는다. 공통 생명주기가 캐시까지 갱신했다."""
    return None


def cmd_list(meta: dict):
    print("에디션별 도구 멤버십 (로케일=all 기준, 실제 설치는 로케일로 추가 필터):\n")
    for pkg in sorted(meta):
        if _tool_location(pkg) is None:
            continue
        m = meta[pkg]
        editions = [e for e in EDITIONS if in_edition(m, e)]
        prot = " [core]" if pkg in _PROTECTED else ""
        key = ("key:" + ",".join(m["needs_key"])) if m.get("needs_key") else "keyless"
        print("  %-22s %-16s %-8s %-10s → %s%s" % (
            pkg, "|".join(editions), m.get("weight", "?"),
            m.get("locale", "?"), key, prot))
    std = sorted(p for p in meta if _tool_location(p) and in_edition(meta[p], "standard"))
    print("\n표준 에디션(keyless ∧ light) 도구 %d개:" % len(std))
    print("  " + ", ".join(std))


def main():
    ap = argparse.ArgumentParser(description="설치 에디션/로케일 적용")
    ap.add_argument("--edition", choices=EDITIONS,
                    default=os.environ.get("INDIEBIZ_EDITION"))
    ap.add_argument("--locale",
                    default=os.environ.get("INDIEBIZ_LOCALE"))
    ap.add_argument("--dry-run", action="store_true", help="이동 계획만 출력")
    ap.add_argument("--list", action="store_true", help="에디션 멤버십만 출력하고 종료")
    args = ap.parse_args()

    meta = derive_tool_meta()

    if args.list:
        cmd_list(meta)
        return 0

    edition = args.edition or "standard"
    locale = args.locale or "universal"
    if edition not in EDITIONS:
        print("알 수 없는 에디션: %r (standard|full)" % edition, file=sys.stderr)
        return 2

    to_remove, to_install, keep = plan_moves(meta, edition, locale)

    print("에디션=%s  로케일=%s" % (edition, locale))
    print("  유지(설치 상태): %d개" % len(keep))
    print("  → not_installed 로 이동(available): %d개%s" % (
        len(to_remove), ("  " + ", ".join(to_remove)) if to_remove else ""))
    print("  → installed 로 이동(추가 설치): %d개%s" % (
        len(to_install), ("  " + ", ".join(to_install)) if to_install else ""))

    if args.dry_run:
        print("\n(dry-run — 이동/재빌드 안 함)")
        return 0

    if not to_remove and not to_install:
        print("\n변경 없음 — 이미 원하는 상태.")
        return 0

    for pkg in to_remove:
        _move(pkg, INSTALLED_TOOLS, NOT_INSTALLED_TOOLS, park=True)
    for pkg in to_install:
        _move(pkg, NOT_INSTALLED_TOOLS, INSTALLED_TOOLS, park=False)

    print("\n어휘 재빌드 중 …")
    rebuild()
    print("완료. 카탈로그가 이제 이 에디션을 반영합니다 "
          "(백엔드가 떠 있으면 POST /packages/reload 또는 재시작으로 런타임 반영).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
