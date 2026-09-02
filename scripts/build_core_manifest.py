#!/usr/bin/env python3
"""
build_core_manifest.py — 표준 코어 매니페스트 생성기

"코어"의 정의 = **리포지토리에 커밋되어 배포되는 것**.
사용자가 자기 머신에서 나중에 더한 패키지·앱·어휘는 git 추적 대상이 아니므로
자동으로 코어에서 빠진다. 즉 origin 경계를 사람이 손으로 태깅하지 않고
`git ls-files`(=배포 집합)에서 파생한다.

산출물: data/core_manifest.json  (★반드시 커밋되어 배포되어야 함 —
.gitignore 의 data/**/*.json 규칙에 대해 !data/core_manifest.json 예외 필요)

이 매니페스트가 표준/사전(사용자) 경계의 단일 진실이다:
- 런타임(package_manager)은 이것으로 패키지 origin(core|user)을 해소
- DMG 업데이터(electron/main.js)는 이것으로 "코어만 갱신, 사용자 것 보존"을 판정
  (git pull 경로는 이미 추적=코어만 덮어써서 동일 의미 — 이 스크립트는 그 의미를
   비-git 환경인 배포판까지 운반한다)

사용:
    python3 scripts/build_core_manifest.py          # 생성/갱신
    python3 scripts/build_core_manifest.py --check   # stale 여부만 검사 (0=OK, 1=stale)
"""

import json
import subprocess
import sys
from pathlib import Path
from iblbuild_common import atomic_write_text

# ★Windows CI 등 비-UTF-8 로케일(cp1252/cp949)에서 ✓·한글 출력이 UnicodeEncodeError 로
# 죽지 않도록 stdout/stderr 를 UTF-8 로 고정한다(audit_bundle_secrets.py 와 같은 처방 —
# 이 스크립트는 npm run dist:filter 첫 단계라, 여기서 죽으면 윈도우 설치 파일이 안 나온다).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "data" / "core_manifest.json"


def _git_tracked(subpath: str) -> list[str]:
    """subpath 아래의 git 추적 파일 목록 (리포 루트 상대경로).

    ★`-z`(NUL 구분): 기본 출력은 비-ASCII 경로를 8진수 이스케이프+따옴표로 인용한다
    (core.quotepath). 한글 파일명(등록 스크립트)이 `\\353\\202…py"` 로 매니페스트에
    들어가 설치 필터가 코어 스크립트 10개를 통째로 뺀 실측(2026-09-02). NFC 로 정규화해
    맥 파일시스템(NFD)과 대조 가능하게 한다.
    """
    import unicodedata
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", subpath],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [unicodedata.normalize("NFC", x.decode("utf-8", errors="surrogateescape"))
            for x in out.stdout.split(b"\0") if x.strip()]


def _top_level_dirs(tracked: list[str], prefix: str) -> list[str]:
    """prefix 바로 아래 디렉토리 이름 집합 (추적 파일이 하나라도 있는 것)."""
    names = set()
    plen = len(prefix)
    for f in tracked:
        if not f.startswith(prefix):
            continue
        rest = f[plen:]
        seg = rest.split("/", 1)[0]
        if seg and not seg.startswith("."):
            names.add(seg)
    return sorted(names)


# --- origin opt-out ---------------------------------------------------------
# 기본: git 추적 = 코어. 하지만 리포는 사용자의 *개인 인스턴스*이기도 해서
# 개인 앱·패키지를 백업/멀티머신 동기화용으로 커밋할 수 있다. 그런 항목은
# 명시적 opt-out 으로 코어(=배포)에서 뺀다. opt-out 마커:
#   - 패키지(디렉토리):  <dir>/.origin  파일 내용에 'user'
#   - 계기(단일 yaml):   yaml 최상위 키  origin: user
# 이건 코어의 손목록이 아니라 *예외 선언*이다(작고 의도적이라 눈에 보이는 게 옳다).

def _dir_opted_out(rel_dir: str) -> bool:
    """<rel_dir>/.origin 파일이 'user' 를 담으면 opt-out."""
    marker = REPO_ROOT / rel_dir / ".origin"
    try:
        if marker.is_file():
            return marker.read_text(encoding="utf-8").strip().lower() == "user"
    except Exception:
        pass
    return False


def _yaml_opted_out(rel_file: str) -> bool:
    """yaml 최상위 `origin: user` 선언이면 opt-out (의존성 없이 라인 스캔)."""
    p = REPO_ROOT / rel_file
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            # 최상위 키만 (들여쓰기 없는 라인)
            if line[:1] not in (" ", "\t") and s.replace(" ", "").lower().startswith("origin:"):
                return s.split(":", 1)[1].strip().lower() == "user"
    except Exception:
        pass
    return False


def _registry_user_scripts(registry: Path | None = None) -> set[str]:
    """data/scripts/registry.yaml 에서 `origin: user` 를 선언한 항목의 file 이름 집합.

    계기 yaml 의 `origin: user` 와 같은 규약(2026-09-02 개통). 의존성 없이 라인 스캔 —
    최상위 키(들여쓰기 0, 콜론 종료)가 항목, 그 아래 `file:` 과 `origin:` 을 읽는다.
    """
    path = registry or (REPO_ROOT / "data" / "scripts" / "registry.yaml")
    if not path.is_file():
        return set()
    out, cur_file, cur_user = set(), None, False

    def _flush():
        if cur_file and cur_user:
            out.add(cur_file)

    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw and raw[:1] not in (" ", "\t", "#") and raw.rstrip().endswith(":"):
            _flush()
            cur_file, cur_user = None, False
            continue
        s = raw.strip()
        if s.startswith("file:"):
            import unicodedata
            cur_file = unicodedata.normalize("NFC", s.split(":", 1)[1].strip().strip("'\""))
        elif s.startswith("origin:"):
            cur_user = s.split(":", 1)[1].strip().strip("'\"").lower() == "user"
    _flush()
    return out


def _core_script_files() -> list[str]:
    """data/scripts/ 의 git 추적 스크립트 파일(registry.yaml 제외) 중 opt-out 안 한 것."""
    user = _registry_user_scripts()
    return sorted(
        Path(f).name
        for f in _git_tracked("data/scripts")
        if Path(f).name != "registry.yaml" and not Path(f).name.startswith(".")
        and Path(f).name not in user
    )


def _core_package_names(kind: str) -> list[str]:
    """installed + not_installed 양쪽의 git 추적 패키지 이름 합집합.

    핵심: 패키지는 *설치 상태와 무관하게* 배포에 딸려오면 코어다.
    not_installed 에 있어도 git 추적이면 배포판에 실려 나가므로 코어(비활성일 뿐).
    진짜 사용자 패키지 = 런타임에 추가돼 git 미추적인 것 → 어느 목록에도 안 잡힘.
    커밋했더라도 <dir>/.origin=user 로 opt-out 하면 코어에서 제외.
    """
    names = set()
    for state in ("installed", "not_installed"):
        prefix = f"data/packages/{state}/{kind}/"
        for name in _top_level_dirs(_git_tracked(f"data/packages/{state}/{kind}"), prefix):
            if _dir_opted_out(f"{prefix}{name}"):
                continue
            names.add(name)
    return sorted(names)


def build_manifest() -> dict:
    tools = _core_package_names("tools")
    extensions = _core_package_names("extensions")

    # 앱(계기) 매니페스트: data/instruments/*.yaml 중 추적 & opt-out 안 한 것의 basename
    instruments = sorted(
        Path(f).stem
        for f in _git_tracked("data/instruments")
        if f.endswith(".yaml") and not _yaml_opted_out(f)
    )

    # 중앙 어휘 fragment (self/others/table 등) — .bak 제외
    vocab_fragments = sorted(
        Path(f).name
        for f in _git_tracked("data/ibl_nodes_src")
        if f.endswith(".yaml")
    )

    # 빌드 산출 어휘 카탈로그 (배포판에서 강제 갱신 대상)
    vocab_artifacts = []
    if _git_tracked("data/ibl_nodes.yaml"):
        vocab_artifacts.append("ibl_nodes.yaml")

    # 등록 스크립트(절차) — registry.yaml 의 `origin: user` 로 opt-out (2026-09-02)
    scripts = _core_script_files()

    core = {
        "packages": {"tools": tools, "extensions": extensions},
        "instruments": instruments,
        "scripts": scripts,
        "vocab_fragments": vocab_fragments,
        "vocab_artifacts": vocab_artifacts,
    }
    return {
        "_comment": "표준 코어 경계의 단일 진실. build_core_manifest.py 가 git 추적 집합에서 파생. 손으로 편집 금지.",
        "generated_from": "git ls-files",
        "core": core,
        "retired": _retired(core),
    }


# --- 은퇴 목록 (2026-09-02, docs/FIRST_SUCCESS_AND_UPGRADE_GATE_HANDOFF.md ② C) -----------
# 코어였다가 사라진 이름은 옛 설치본에 영원히 남는다(08-31 윈도우 실전: 은퇴 어휘 yaml 이
# stale). 직전 매니페스트의 core 와 지금 core 의 차집합을 **누적**해 기록하고, 설치본 동기화
# (frontend/electron/userdata_sync.js)가 그 이름을 격리 이동한다(실삭제 아님 — 사용자 판정
# 2026-09-02: 매니페스트 차집합은 기계 계산이라 오판 시 복구 가능해야 한다).
# 이름이 다시 코어로 돌아오면 은퇴 목록에서 빠진다.

_RETIRED_KEYS = ("packages.tools", "packages.extensions", "instruments", "scripts", "vocab_fragments")


def _get_path(d: dict, dotted: str) -> list:
    cur = d
    for seg in dotted.split("."):
        cur = (cur or {}).get(seg) if isinstance(cur, dict) else None
    return list(cur or [])


def _previous_manifest() -> dict:
    """직전 커밋된 매니페스트(작업 트리 파일). 없으면 빈 dict — 첫 생성은 은퇴 0."""
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _retired(core: dict) -> dict:
    prev = _previous_manifest()
    prev_core, prev_retired = prev.get("core") or {}, prev.get("retired") or {}
    out = {}
    for key in _RETIRED_KEYS:
        now = set(_get_path(core, key))
        gone = set(_get_path(prev_core, key)) - now
        kept = set(prev_retired.get(key) or []) - now
        out[key] = sorted(gone | kept)
    return out


def _serialize(manifest: dict) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    manifest = build_manifest()
    serialized = _serialize(manifest)

    check_only = "--check" in sys.argv
    if check_only:
        if not MANIFEST_PATH.exists():
            print("[core-manifest] ✗ data/core_manifest.json 없음 — build_core_manifest.py 실행 필요")
            return 1
        current = MANIFEST_PATH.read_text(encoding="utf-8")
        if current != serialized:
            print("[core-manifest] ✗ stale — git 추적 집합과 불일치. build_core_manifest.py 재실행 후 커밋 필요")
            return 1
        print("[core-manifest] ✓ 최신")
        return 0

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(MANIFEST_PATH, serialized)
    core = manifest["core"]
    print(
        f"[core-manifest] ✓ 생성: tools {len(core['packages']['tools'])} · "
        f"extensions {len(core['packages']['extensions'])} · "
        f"instruments {len(core['instruments'])} · "
        f"scripts {len(core['scripts'])} · "
        f"vocab_fragments {len(core['vocab_fragments'])} · "
        f"vocab_artifacts {len(core['vocab_artifacts'])} · "
        f"retired {sum(len(v) for v in manifest['retired'].values())}"
    )
    print(f"[core-manifest]   → {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
