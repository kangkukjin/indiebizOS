#!/usr/bin/env python3
"""
build_dist_stage.py — 설치 파일에 담을 `data/` 를 **git 추적 집합**으로 스테이징한다.

문제(2026-09-06 실측): frontend/package.json 의 extraResources `data` 는 개발 몸의 `../data` 를
통째로 담고 손목록으로 빼는 denylist 였다. 173개 최상위 항목 중 git 추적은 28개 — 나머지
(백업 8.9G·쇼케이스 5.1G·음악·해마 원장·기억 트리·로그)가 그대로 실려 로컬 빌드가 18GB 가
됐고 DMG 는 복사 중 죽었다. 손으로 고른 제외 목록은 반드시 샌다(관문을 먼저 써라).

해결: 경계를 하나로 — 배포에 딸려오는 것 = git 이 추적하는 것(core_manifest 와 같은 정의,
CI 의 fresh clone 빌드와 같은 결과). 이 스크립트가 `git ls-files data` 를
`frontend/.dist_stage/data/` 에 하드링크(실패 시 복사)로 펼치고, package.json 의 data 항목은
`from: ".dist_stage/data"` 를 본다. 기존 필터(secret·크러프트 제외)는 그 위에 그대로 걸린다.
미추적 코어 자산(임베딩 모델 data/models)은 애초에 미번들·첫 실행 다운로드(hippocampus_provision)라
빠지는 게 맞다 — 프로덕션 번들의 resources/data/models 는 비어 있어야 한다(ibl_usage_db 주석).

사용:
    python3 scripts/build_dist_stage.py           # 스테이지 재생성 (빌드 프리스텝, npm run dist:stage)
    python3 scripts/build_dist_stage.py --check   # package.json 이 스테이지를 보는지 + gitignore (0=OK)
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
STAGE_ROOT = REPO_ROOT / "frontend" / ".dist_stage"
STAGE_DATA = STAGE_ROOT / "data"
PKG_JSON = REPO_ROOT / "frontend" / "package.json"
EXPECTED_FROM = ".dist_stage/data"


def tracked_data_files() -> list[str]:
    """git 인덱스 기준 data/ 아래 추적 파일(NFC 경로, data/ 기준 상대)."""
    out = subprocess.run(["git", "ls-files", "-z", "data"], cwd=REPO_ROOT,
                         capture_output=True, check=True).stdout
    rels = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "surrogateescape")
        rels.append(rel[len("data/"):])
    return rels


def build_stage() -> int:
    if STAGE_ROOT.exists():
        shutil.rmtree(STAGE_ROOT)
    STAGE_DATA.mkdir(parents=True)
    linked = copied = missing = 0
    total_bytes = 0
    for rel in tracked_data_files():
        src = DATA_DIR / rel
        dst = STAGE_DATA / rel
        if not src.is_file():
            missing += 1  # 인덱스엔 있는데 작업 트리엔 없음(로컬 이동·삭제) — 정직하게 셈만 한다
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)
            linked += 1
        except OSError:
            shutil.copy2(src, dst)
            copied += 1
        total_bytes += src.stat().st_size
    print(f"[dist-stage] {STAGE_DATA.relative_to(REPO_ROOT)}: 추적 파일 {linked + copied}개 "
          f"(하드링크 {linked} · 복사 {copied} · 작업트리 부재 {missing}) · {total_bytes / 1e6:.1f}MB")
    if missing:
        print(f"[dist-stage] ⚠ 인덱스에만 있는 파일 {missing}개는 담지 않았다 — 로컬에서 옮기거나 지운 것(커밋 전이면 배치를 확인)")
    return 0


def check() -> int:
    cfg = json.loads(PKG_JSON.read_text(encoding="utf-8"))
    froms = [e.get("from") for e in cfg.get("build", {}).get("extraResources", []) if e.get("to") == "data"]
    ok = True
    if froms != [EXPECTED_FROM]:
        print(f"[dist-stage] ✗ package.json data 항목 from={froms} — {EXPECTED_FROM!r} 이어야 한다(손목록 denylist 로 되돌리지 말 것)")
        ok = False
    gi = (REPO_ROOT / "frontend" / ".gitignore").read_text(encoding="utf-8").splitlines()
    if ".dist_stage" not in [l.strip() for l in gi]:
        print("[dist-stage] ✗ frontend/.gitignore 에 .dist_stage 가 없다")
        ok = False
    if ok:
        print("[dist-stage] ✓ package.json 이 git 추적 스테이지를 본다")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else build_stage())
