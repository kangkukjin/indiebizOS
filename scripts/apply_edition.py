#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/apply_edition.py — 설치 에디션 + 로케일에 맞춰 도구 패키지를
installed ↔ not_installed 로 분할한다 (능력 자기완결화 계획 Phase 5).

능력 자기완결화(Phase 0~4)로 각 패키지가 "코드 + 어휘"를 원자적으로 담은 능력이
됐으므로, 이제 "무엇을 기본 설치할지"를 결정적 필터 하나로 고를 수 있다. 이 스크립트가
그 필터를 적용한다 — 새 매니페스트를 만들지 않고 data/package_meta.json 세 축을 그대로 쓴다.

에디션(능력 폭):
  standard = 외부 키 불요(needs_key 비어있음) ∧ 가벼움(weight=light)  — "그냥 켜진다"
  full     = 전부(키 요구·무거운 팩 포함)

로케일(지역 관련성):
  universal = universal 로케일 팩만
  kr        = universal + kr 팩
  all       = 로케일 무시(전부)

설치 집합 = in_edition(edition) ∧ in_locale(locale).
탈락한 도구 패키지는 not_installed/tools 로 이동한다 — 지우는 게 아니라 "available"로
남겨 카탈로그가 on-demand 재설치를 제안할 수 있게 한다(3-상태의 available 상태).
그 아래 두 상태는 이미 구현돼 있다: installed-dormant(키 대기, ibl_access 의 dormant 속성),
live(키까지 있음).

절대 건드리지 않는 것:
  - extensions/(백엔드 코어 모듈: ai-agent, gmail, scheduler …) — 몸의 일부.
  - _PROTECTED 도구(ibl-core, system_essentials) — 표준 필터를 통과하지만 방어적으로 고정.
  - 중앙 backend-native 어휘(ibl_nodes_src).

이동 후 build_ibl_nodes.py 를 재실행해 ibl_nodes.yaml / phone_manifest.json /
package_meta.json 을 동기화한다(부재-패키지 관용 덕에 --check 는 계속 초록).

사용:
  python3 scripts/apply_edition.py --list                         # 각 에디션 멤버십만 출력
  python3 scripts/apply_edition.py --dry-run --edition standard --locale universal
  python3 scripts/apply_edition.py --edition full --locale kr

무인 설치(installer): 인자 대신 환경변수 INDIEBIZ_EDITION / INDIEBIZ_LOCALE 사용 가능.
재실행 가능 — 에디션을 바꿔 다시 돌리면 팩이 양방향으로 이동한다.
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
_PROTECTED = {"ibl-core", "system_essentials"}

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
    if (ROOT / INSTALLED_TOOLS / pkg).is_dir():
        return "installed"
    if (ROOT / NOT_INSTALLED_TOOLS / pkg).is_dir():
        return "not_installed"
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
        if desired and loc == "not_installed" and parked_by_us:
            # 우리가 내보낸 팩만 되돌린다(출하 not_installed 큐레이션은 보존).
            to_install.append(pkg)
        elif not desired and loc == "installed":
            to_remove.append(pkg)
        else:
            keep.append(pkg)
    return to_remove, to_install, keep


def _move(pkg: str, src_root: str, dst_root: str, park: bool):
    src = ROOT / src_root / pkg
    dst = ROOT / dst_root / pkg
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    marker = dst / _PARK_MARKER
    if park:
        marker.write_text("moved to not_installed by apply_edition\n", encoding="utf-8")
    elif marker.exists():
        marker.unlink()  # 되돌릴 때 마커 제거


def rebuild():
    """build_ibl_nodes.py 재실행 — 생성물 동기화. 실패 시 예외."""
    proc = subprocess.run(
        [sys.executable, "scripts/build_ibl_nodes.py"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit("build_ibl_nodes.py 재빌드 실패 (exit=%d)" % proc.returncode)


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
