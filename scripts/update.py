#!/usr/bin/env python3
"""update.py — 정본 설치 경로(git clone)의 업그레이드 레시피 (bootstrap.py 의 짝, 2026-09-02)

헌법(canonical-install-path): 공식 설치 = git clone 한 소스 트리. 설치 레시피는 bootstrap.py 하나인데
**업그레이드 레시피는 없었다** — "git pull" 이 문서 어디에도 없었고, 사용자는 맨손으로 당겼다.
그 맨손 pull 이 깨지는 자리가 하나 있다(2026-09-02 upgrade-smoke 실측): 패키지 켜고/끄기는
`installed/ ↔ not_installed/` 폴더 이동인데 코어 패키지는 git 추적이라, 사용자가 옮겨 둔 패키지를
상류가 고치면 pull 이 거부되거나(로컬 변경) 옛 자리에 되살아난다.

이 스크립트는 그 이음매 하나를 맡는다 — 폴더 위치가 진실이라는 규칙은 그대로 두고(런타임 독자 20여 곳),
**당기는 동안만** 사용자 배치를 걷었다 다시 놓는다:

  1. 코어 패키지의 사용자 배치(= git 기본 위치와 다른 것)를 기록하고 git 자리로 되돌린다
  2. git pull --ff-only (또는 --target REF 로 ff 병합)
  3. 기록한 배치를 다시 놓는다 — 상류가 은퇴시킨 패키지는 놓을 것이 없으니 신고만
  4. requirements-*.txt 가 바뀌었으면 .venv 에 재설치
  (스키마 마이그레이션은 다음 부팅이 자동으로 — schema_migrations.py)

pull 이 실패하면(로컬 수정 충돌 등) 배치를 원래대로 돌려놓고 정직하게 멈춘다 — stash 마법 없음.
stdlib 만, 맥·윈도우·리눅스 공용, 멱등.

사용:
  python3 scripts/update.py                # 상류에서 당기기
  python3 scripts/update.py --dry-run      # 무엇을 옮기고 당길지만
  python3 scripts/update.py --target REF   # (시험용) 특정 커밋으로 ff 병합
  python3 scripts/update.py --no-deps      # 의존성 재설치 생략
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("tools", "extensions")
STATES = ("installed", "not_installed")


def git(root: Path, *args, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패({r.returncode}): {(r.stderr or r.stdout).strip()[:600]}")
    return r.stdout


def core_default_placement(root: Path) -> dict:
    """{pkg: (kind, state)} — git 이 추적하는 위치 = 배포 기본 배치."""
    out = {}
    for line in git(root, "ls-files", "-z", "data/packages").split("\0"):
        parts = line.split("/")
        if len(parts) >= 5 and parts[2] in STATES and parts[3] in KINDS:
            out.setdefault(parts[4], (parts[3], parts[2]))
    return out


def placement_deviations(root: Path) -> list:
    """사용자 배치가 git 기본과 다른 코어 패키지 목록: [(pkg, kind, default_state, actual_state)].
    양쪽에 다 있는 패키지(옛 맨손 pull 의 흔적)는 충돌로 따로 돌려준다."""
    devs, conflicts = [], []
    for pkg, (kind, default) in core_default_placement(root).items():
        other = "not_installed" if default == "installed" else "installed"
        at_default = (root / "data" / "packages" / default / kind / pkg).is_dir()
        at_other = (root / "data" / "packages" / other / kind / pkg).is_dir()
        if at_default and at_other:
            conflicts.append((pkg, kind))
        elif at_other and not at_default:
            devs.append((pkg, kind, default, other))
    return devs, conflicts


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def restore_git_placement(root: Path, devs: list) -> list:
    """사용자 배치 → git 기본 자리 (pull 전). 반환 = 옮긴 pkg 목록."""
    moved = []
    for pkg, kind, default, actual in devs:
        src = root / "data" / "packages" / actual / kind / pkg
        dst = root / "data" / "packages" / default / kind / pkg
        if src.is_dir() and not dst.exists():
            _move(src, dst); moved.append(pkg)
    return moved


def reapply_placement(root: Path, devs: list) -> dict:
    """git 기본 자리 → 사용자 배치 (pull 후). 상류가 은퇴시킨 패키지는 retired 로 신고."""
    reapplied, retired = [], []
    for pkg, kind, default, actual in devs:
        src = root / "data" / "packages" / default / kind / pkg
        dst = root / "data" / "packages" / actual / kind / pkg
        if src.is_dir():
            if not dst.exists():
                _move(src, dst); reapplied.append(pkg)
        else:
            retired.append(pkg)
    return {"reapplied": reapplied, "retired": retired}


def requirements_changed(root: Path, before: str, after: str) -> list:
    if before == after:
        return []
    out = git(root, "diff", "--name-only", before, after, "--", "backend/requirements-core.txt",
              "backend/requirements-tools.txt", "backend/requirements-ml.txt")
    return [l for l in out.splitlines() if l.strip()]


def venv_python(root: Path) -> str:
    cand = root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python3")
    return str(cand) if cand.exists() else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT), help="대상 소스 트리 (기본: 이 스크립트의 저장소)")
    ap.add_argument("--target", help="ff 병합할 커밋/브랜치 (기본: 상류 pull)")
    ap.add_argument("--no-deps", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if not (root / ".git").exists():
        print(f"✗ {root} 는 git 저장소가 아닙니다 — 설치본(.dmg/.exe)은 앱 재설치가 업그레이드입니다.")
        return 2

    devs, conflicts = placement_deviations(root)
    if conflicts:
        print("✗ 같은 코어 패키지가 installed/ 와 not_installed/ 양쪽에 있습니다(옛 pull 의 흔적) — 한쪽을 지운 뒤 다시:")
        for pkg, kind in conflicts:
            print(f"    data/packages/{{installed,not_installed}}/{kind}/{pkg}")
        return 1
    before = git(root, "rev-parse", "HEAD").strip()
    print(f"[update] {root}  HEAD={before[:8]}  사용자 배치 {len(devs)}건: "
          + (", ".join(f"{p}→{s}" for p, _, _, s in devs) or "없음"))
    if a.dry_run:
        print("[update] dry-run — 여기서 멈춤 (배치 되돌림 → " + ("ff 병합 " + a.target if a.target else "git pull --ff-only") + " → 배치 재적용)")
        return 0

    moved = restore_git_placement(root, devs)
    try:
        if a.target:
            git(root, "merge", "--ff-only", a.target)
        else:
            git(root, "pull", "--ff-only")
    except RuntimeError as e:
        reapply_placement(root, devs)
        print(f"✗ 당기기 실패 — 배치는 원래대로 돌려놓았습니다.\n  {e}\n"
              "  로컬 수정이 있으면 정비소(외부 하네스)에서 정리한 뒤 다시 실행하세요.")
        return 1
    after = git(root, "rev-parse", "HEAD").strip()
    re = reapply_placement(root, devs)
    print(f"[update] {before[:8]} → {after[:8]}  배치 되돌림 {len(moved)} · 재적용 {len(re['reapplied'])}"
          + (f" · 상류 은퇴로 놓을 것 없음: {', '.join(re['retired'])}" if re["retired"] else ""))

    changed = requirements_changed(root, before, after)
    if changed and not a.no_deps:
        py = venv_python(root)
        if not py:
            print(f"  ⚠ requirements 변경({', '.join(changed)}) — .venv 가 없어 재설치 생략. python3 scripts/bootstrap.py 를 실행하세요.")
        else:
            for req in changed:
                print(f"[update] 의존성 재설치 — {req}", flush=True)
                r = subprocess.run([py, "-m", "pip", "install", "--quiet", "-r", str(root / req)])
                if r.returncode != 0:
                    print(f"  ⚠ {req} 설치 실패 — 해당 기능이 돌 때 터집니다. 수동: {py} -m pip install -r {req}")
    elif changed:
        print(f"  (requirements 변경 {len(changed)}건 — --no-deps 라 생략)")
    print("[update] 완료 — 다음 부팅이 스키마 마이그레이션을 따라잡습니다(backend/datastore/schema_migrations.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
