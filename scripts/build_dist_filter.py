#!/usr/bin/env python3
"""
build_dist_filter.py — 설치 파일(installer)을 코어 기준으로 만들기 위한
electron-builder 파일 필터의 *매니페스트 주도* 생성기.

문제: frontend/package.json 의 extraResources `data` 필터는 "전부 담고(**/*)
개인 파일을 이름으로 하나씩 빼는" ~60줄 손수 관리 제외 목록이다. 리포가 사용자의
개인 인스턴스이기도 해서, 커밋한 개인 앱·패키지와 온갖 런타임 크러프트
(.fuse_hidden*, 개인 .md/.html, *.bak …)가 필터를 새어 다른 사용자에게 배포된다.

해결: 경계를 core_manifest.json 하나로 몰기. 이 스크립트는 package.json 의 data
필터에서 두 sentinel(`!__GEN_START__` … `!__GEN_END__`) 사이 구간을 재생성한다:
  - 매니페스트에 없는 on-disk 패키지 → 제외 (installed·not_installed 양쪽, opt-out 포함)
  - 매니페스트에 없는 계기(instruments/*.yaml) → 제외
  - 개인 크러프트 패턴 → 제외
기존 secret/런타임 제외(그 hard-won 손목록)는 **건드리지 않는다** — 순수 추가라
어떤 코어 파일도 떨어뜨리지 않는다(비-코어만 뺌). 크러프트도 안전한 패턴만.

★주의(미완): 코어 *런타임 자산* 중 git 미추적인 것(임베딩 모델 data/models/,
해마 코퍼스 data/training/, 일부 빌드 산출물)은 순수 git-포함으로는 빠진다.
현재는 기존 필터가 이들을 (제외 목록에 없어서) 담고 있으므로 이 스크립트도 건드리지
않는다. 완전한 '스테이징 트리 포함' 전환은 실빌드 검증 + 코어-자산 allowlist 확정
후속 작업. (docs/CORE_USER_INSTALL_SEAM 참조)

사용:
    python3 scripts/build_dist_filter.py           # 필터 재생성
    python3 scripts/build_dist_filter.py --check    # stale 검사 (0=OK, 1=stale)
"""

import json
import sys
from pathlib import Path

# ★Windows CI 등 비-UTF-8 로케일(cp1252/cp949)에서 ✓·한글 출력이 UnicodeEncodeError 로
# 죽지 않도록 stdout/stderr 를 UTF-8 로 고정한다(audit_bundle_secrets.py 와 같은 처방).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_JSON = REPO_ROOT / "frontend" / "package.json"
MANIFEST_PATH = REPO_ROOT / "data" / "core_manifest.json"

GEN_START = "!__GEN_START__"
GEN_END = "!__GEN_END__"

# 개인·런타임 크러프트 — 확장자/이름 패턴이 명백히 코어가 아닌 것만(안전).
# (개인 .md/.html/.png 은 data/ 최상위에만 두는 관습 — 코어 문서는 guides/·system_docs/
#  하위라 `*.ext` 최상위 매칭이 안 건드림.)
CRUFT_PATTERNS = [
    "!**/.fuse_hidden*",      # NAS 마운트 잔재
    "!**/.DS_Store",
    "!**/*.bak",
    "!**/*.bak.*",
    "!**/*.bak_*",
    "!**/*.backup*",
    "!**/*.bak-*",
    "!*.md",                   # data/ 최상위 개인 메모(cheongju_restaurants.md 등)
    "!*.html",                 # data/ 최상위 개인 산출(regime_change_analysis.html 등)
    "!*.png",                  # data/ 최상위 테스트/개인 이미지(gomoku_board.png 등)
    "!*.sql",
    "!*.jsonl",
]


# 몸 전속 신원·상태·개인 콘텐츠 — 새 몸이 물려받으면 안 되는 것들.
#
# ★배경(2026-07-21): 윈도우 PC 가 맥의 원격 런처 주소를 그대로 보여준 사고를 쫓다가,
#   data 필터가 "이름으로 하나씩 빼는 denylist" 라서 *신원 파일 전체*가 빠져 있는 걸 발견.
#   지금 배포본은 CI(fresh checkout)에서 빌드돼 무사하지만, 개발 맥에서 로컬 빌드하면
#   showcase_state.json(창고 주소)·portal_state.json(회원 비번 해시·발급 키)·dms.db·
#   Gmail OAuth 토큰이 설치 파일에 그대로 실린다.
#
# 두 부류를 함께 막는다:
#   (a) 신원·상태 — 물려받으면 새 몸이 남의 주소·남의 회원 명부를 갖게 된다.
#   (b) 개인 콘텐츠·자격증명 — 애초에 남에게 가면 안 되는 것.
# 전부 각 모듈이 없으면 기본값으로 새로 만드는 파일이라, 빼도 새 설치가 깨지지 않는다.
PERSONAL_STATE_PATTERNS = [
    # (a) 이 몸의 공개 신원 — 주소는 몸마다 달라야 한다
    "!showcase_state.json",
    "!public_face.json",
    "!warehouse.json",
    "!warehouse_feed.db",
    "!warehouse_guestbook.json",
    "!warehouse_likes.json",
    "!device_registry.json",
    # (b) 개인 명부·대화·기억
    "!portal_state.json",          # 포털 회원 명부(비밀번호 해시·발급한 개인 링크 키)
    "!dms.db",                     # Nostr DM 캐시
    "!conversation.db",            # (복수형 conversations.db 는 위 손목록에 이미 있음)
    "!forage_*.db",                # 포식 기억 — 개인 디스크 지도
    "!hidden_dm_peers.json",
    "!auto_response_state.json",
    "!bulletin/**",                # 자유게시판 글·사진
    "!family_news/**",             # 가족신문 사진·방명록·업로드
    # (c) 자격증명 — ★`!tokens/**` 는 data/ 최상위만 매칭해서 패키지 안 토큰이 새어나갔다
    "!**/tokens/**",               # packages/installed/extensions/gmail/tokens/*.json 등
    "!packages/installed/extensions/gmail/config.yaml",
    "!*.log",                      # cloudflared.log 등 — 호스트명·경로가 찍힌다
]


def _load_manifest_core() -> dict:
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    core = m.get("core", {})
    pkgs = core.get("packages", {})
    return {
        "tools": set(pkgs.get("tools", [])),
        "extensions": set(pkgs.get("extensions", [])),
        "instruments": set(core.get("instruments", [])),
    }


def _noncore_package_excludes(core: dict) -> list[str]:
    """on-disk 패키지 중 매니페스트에 없는 것 → 제외 글롭 (배포 from=../data 기준 상대)."""
    out = []
    for state in ("installed", "not_installed"):
        for kind in ("tools", "extensions"):
            d = REPO_ROOT / "data" / "packages" / state / kind
            if not d.is_dir():
                continue
            for child in sorted(d.iterdir()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                if child.name not in core[kind]:
                    out.append(f"!packages/{state}/{kind}/{child.name}/**")
    return out


def _noncore_instrument_excludes(core: dict) -> list[str]:
    out = []
    d = REPO_ROOT / "data" / "instruments"
    if d.is_dir():
        for f in sorted(d.glob("*.yaml")):
            if f.stem not in core["instruments"]:
                out.append(f"!instruments/{f.name}")
    return out


def _generated_block() -> list[str]:
    core = _load_manifest_core()
    block = [GEN_START]
    block += CRUFT_PATTERNS
    block += PERSONAL_STATE_PATTERNS
    block += _noncore_package_excludes(core)
    block += _noncore_instrument_excludes(core)
    block.append(GEN_END)
    return block


def _data_entry(build_cfg: dict) -> dict:
    for e in build_cfg.get("extraResources", []):
        if isinstance(e, dict) and e.get("to") == "data":
            return e
    raise RuntimeError("extraResources 에서 to=data 항목을 못 찾음")


def _with_generated_filter(existing: list[str], block: list[str]) -> list[str]:
    """기존 필터에서 이전 GEN 구간을 떼고 새 block 을 뒤에 붙인다(나머지 보존)."""
    kept, skipping = [], False
    for item in existing:
        if item == GEN_START:
            skipping = True
            continue
        if item == GEN_END:
            skipping = False
            continue
        if not skipping:
            kept.append(item)
    return kept + block


def main() -> int:
    check_only = "--check" in sys.argv
    pkg = json.loads(PKG_JSON.read_text(encoding="utf-8"))
    entry = _data_entry(pkg.get("build", {}))
    current = list(entry.get("filter", []))
    desired = _with_generated_filter(current, _generated_block())

    if check_only:
        if current != desired:
            print("[dist-filter] ✗ stale — package.json data 필터가 매니페스트와 불일치. "
                  "`python3 scripts/build_dist_filter.py` 재실행 필요", file=sys.stderr)
            return 1
        print("[dist-filter] ✓ 최신")
        return 0

    if current == desired:
        print("[dist-filter] 변경 없음 (이미 최신)")
        return 0

    entry["filter"] = desired
    PKG_JSON.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gen = _generated_block()
    n_pkg = sum(1 for x in gen if x.startswith("!packages/"))
    n_inst = sum(1 for x in gen if x.startswith("!instruments/"))
    print(f"[dist-filter] ✓ 재생성: 크러프트 {len(CRUFT_PATTERNS)} · "
          f"몸 전속 신원·개인 {len(PERSONAL_STATE_PATTERNS)} · "
          f"비-코어 패키지 제외 {n_pkg} · 비-코어 계기 제외 {n_inst}")
    print(f"[dist-filter]   → {PKG_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
