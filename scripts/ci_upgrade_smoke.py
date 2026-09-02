#!/usr/bin/env python3
"""ci_upgrade_smoke.py — 노후·개인화 설치본 위의 업그레이드 관문 (2026-09-02, ② B)

빈 설치본 부팅(ci_boot_smoke)의 다음 층. 릴리스 관문 5종 중 넷을 **실패하는 테스트**로 만든다:
  ② 노후·개인화 설치본이 업그레이드 뒤 부팅한다        (git 경로 + 설치본 동기화 경로 둘 다)
  ③ 사용자 소유물이 보존된다                            (파일 해시·패키지 활성상태·DB 행·설정)
  ④ 동기화가 도중에 죽으면 다음 기동이 원상복구한다      (저널 트랜잭션 — failAfterEntries 로 재현)
  ⑤ 은퇴 코어가 남지 않는다                             (git 경로=삭제, 설치본 경로=격리 이동)
  + 스키마 마이그레이션이 옛 DB 를 따라잡는다            (user_version, 옛 액션명 행)

두 경로:
  A. git pull 등가 — 옛 worktree 위에 지금 트리(추적+미추적·비무시 파일)를 덮고 사라진 추적 파일을
     지운다. 미커밋 변경도 그대로 실린다(로컬 증명에 필요). 부팅 = 그 트리의 backend.
  B. 설치본 동기화 — frontend/electron/userdata_sync.js 를 node 로 직접 불러 옛 userData 위에 돌린다.
     resources = 지금 트리(배포 필터 전 — 근사). 부팅 = 지금 트리의 backend + INDIEBIZ_BASE_PATH=userData.

사용: python3 scripts/ci_upgrade_smoke.py [--tag vX.Y.Z] [--keep] [--out DIR]
CI: .github/workflows/portability.yml upgrade-smoke 잡.
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_aged_install as fx   # noqa: E402
import update as up              # noqa: E402 — git 경로 업그레이드 레시피(배치 되돌림/재적용)

ROOT = fx.ROOT
SYNC_JS = ROOT / "frontend" / "electron" / "userdata_sync.js"
RETIRED_SCRIPT = "backend/migrate_storage_action.py"   # 2026-09-02 은퇴 — git 경로에서 사라져야 한다
NEW_MODULE = "backend/base/ai_candidates.py"            # 2026-09-02 신설 — 업그레이드로 도착해야 한다


class Fail(AssertionError):
    pass


def check(cond, msg):
    if not cond:
        raise Fail(msg)
    print(f"  ✓ {msg}", flush=True)


# ── 공통 단언 ──────────────────────────────────────────────────────────────

def assert_preserved(base: Path, expect: dict, label: str):
    print(f"[{label}] 보존 단언", flush=True)
    pk = base / "data" / "packages"
    disabled = expect["disabled_pkg"]
    check(not (pk / "installed" / "tools" / disabled).exists()
          and (pk / "not_installed" / "tools" / disabled).exists(),
          f"사용자가 끈 코어 패키지 {disabled} 가 not_installed 에 그대로")
    upk = pk / "not_installed" / "tools" / fx.USER_PKG
    check(upk.exists(), f"사용자 패키지 {fx.USER_PKG} 존재")
    check(fx.tree_hashes(upk) == expect["user_pkg_hashes"], "사용자 패키지 내용 불변(해시)")
    check(fx.sha(base / fx.USER_NOTE) == expect["user_note_sha"], "사용자 파일 불변")
    check(fx.sha(base / fx.USER_CONFIG) == expect["user_config_sha"], "사용자 설정 json 불변")
    con = sqlite3.connect(str(base / "data" / "business.db"))
    n = con.execute("SELECT count(*) FROM user_probe").fetchone()[0]; con.close()
    check(n == expect["business_user_rows"], f"business.db 사용자 표 행 {n}")
    if expect["have_world_pulse"]:
        con = sqlite3.connect(str(base / "data" / "world_pulse.db"))
        ver = con.execute("PRAGMA user_version").fetchone()[0]
        acts = [r[0] for r in con.execute("SELECT action FROM action_health")]
        con.close()
        check(ver >= 1, f"world_pulse user_version={ver} (스키마 마이그레이션 적용)")
        check("cctv_search" not in acts and "storage" in acts, "옛 액션명 행만 정리, 나머지 보존")
    if expect["have_usage"]:
        con = sqlite3.connect(str(base / "data" / "ibl_usage.db"))
        rows = [r[0] for r in con.execute("SELECT ibl_code FROM ibl_examples WHERE intent='픽스처 옛 이름'")]
        con.close()
        check(rows and all("storage_scan" not in c and '[self:storage]{op: "scan"' in c for c in rows),
              "ibl_usage 옛 액션명 행이 새 이름으로 치환")
    check(not (base / "data" / ".upgrade_pending").exists(), ".upgrade_pending 표식 없음")


# ── 경로 A: git pull 등가 ───────────────────────────────────────────────────

def current_tree_files() -> list:
    """지금 트리의 배포 집합 = 추적 + 미추적·비무시 파일 중 **작업 트리에 실존하는 것**.
    (작업 트리에서 지웠지만 아직 커밋 안 한 파일은 빠진다 — 다음 커밋이 지울 파일이므로.)"""
    out = fx.sh(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    return [f for f in out.split("\0") if f and (ROOT / f).is_file()]


def materialize_resources(out: Path) -> Path:
    """경로 B 의 resources — 설치본 번들의 근사: 지금 트리의 배포 집합만 임시 폴더에 옮긴다.
    ROOT 를 그대로 쓰면 개발 몸의 라이브 데이터(.db·개인 파일)가 '번들'로 실려 간다."""
    res = out / "resources"
    if res.exists():
        shutil.rmtree(res)
    n = 0
    for rel in current_tree_files():
        dst = res / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
        n += 1
    print(f"[B] resources 근사 번들: {n} 파일 → {res}", flush=True)
    return res


def apply_git_upgrade(aged: Path, tag: str) -> dict:
    """git pull 등가 — 상류(태그→지금 트리)가 **바꾼 파일만** 갱신·삭제한다. 사용자가 옮기거나
    지운 뒤 상류가 손대지 않은 파일은 그대로 둔다(pull 의 의미). 미커밋 변경도 실린다."""
    changed = [f for f in fx.sh(["git", "diff", "--name-only", "-z", tag]).split("\0") if f]
    untracked = [f for f in fx.sh(["git", "ls-files", "--others", "--exclude-standard", "-z"]).split("\0") if f]
    copied = removed = 0
    for rel in sorted(set(changed) | set(untracked)):
        src, dst = ROOT / rel, aged / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst); copied += 1
        elif dst.is_file():          # 상류에서 지워진(또는 작업 트리에서 지운) 추적 파일
            dst.unlink(); removed += 1
    return {"copied": copied, "removed": removed}


def _working_tree_clean() -> bool:
    return not fx.sh(["git", "status", "--porcelain"]).strip()


def run_path_a(fixture: dict) -> None:
    """git 경로. 지금 트리가 깨끗하면(CI) **진짜 레시피** `scripts/update.py --target HEAD` 를 옛 트리에서 돌리고,
    미커밋 변경이 있으면(로컬) update.py 의 배치 함수 사이에 "상류가 바꾼 파일만" 에뮬레이션을 끼운다."""
    aged, python, expect = fixture["tree"], fixture["python"], fixture["expect"]
    print(f"\n=== 경로 A (git): {fixture['tag']} → 지금 트리 ===", flush=True)
    devs, conflicts = up.placement_deviations(aged)
    check(not conflicts and any(d[0] == expect["disabled_pkg"] for d in devs),
          f"사용자 배치 감지: {expect['disabled_pkg']} (상류 변경 {'있음' if expect['disabled_pkg_upstream_changed'] else '없음'})")
    if _working_tree_clean():
        head = fx.sh(["git", "rev-parse", "HEAD"]).strip()
        r = subprocess.run([python, str(ROOT / "scripts" / "update.py"), "--root", str(aged), "--target", head, "--no-deps"],
                           capture_output=True, text=True)
        print(r.stdout.strip(), flush=True)
        check(r.returncode == 0, f"진짜 레시피 update.py --target {head[:8]} 성공" + ("" if r.returncode == 0 else f"\n{r.stderr[-600:]}"))
    else:
        moved = up.restore_git_placement(aged, devs)
        st = apply_git_upgrade(aged, fixture["tag"])
        re = up.reapply_placement(aged, devs)
        print(f"[A] (미커밋 변경 있음 → 에뮬레이션) 배치 되돌림 {len(moved)} · 덮어씀 {st['copied']} · 삭제 {st['removed']} · 재적용 {len(re['reapplied'])}", flush=True)
    check((aged / NEW_MODULE).exists(), f"신설 모듈 도착 {NEW_MODULE}")
    check(not (aged / RETIRED_SCRIPT).exists(), f"은퇴 스크립트 잔존 없음 {RETIRED_SCRIPT}")
    fx.boot(aged, aged, python, label="A-upgraded-boot")
    assert_preserved(aged, expect, "A")


# ── 경로 B: 설치본 동기화 ───────────────────────────────────────────────────

def _node_sync(user_data: Path, manifest: Path, resources: Path, fail_after: int = 0) -> dict:
    js = f"""
import('{SYNC_JS.as_posix()}').then(m => {{
  try {{
    const r = m.syncUserData({{ resourcesPath: {json.dumps(resources.as_posix())}, userDataPath: {json.dumps(user_data.as_posix())},
      version: 'upgrade-smoke', manifestPath: {json.dumps(manifest.as_posix())}, failAfterEntries: {fail_after},
      log: (s) => console.error(s) }});
    console.log(JSON.stringify({{ ok: true, changed: r.changed, rolledBack: r.rolledBack ? r.rolledBack.length : 0,
      retired: r.retired, backupDir: r.backupDir || null }}));
  }} catch (e) {{ console.log(JSON.stringify({{ ok: false, error: String(e) }})); }}
}});
"""
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise Fail(f"node 동기화 실행 실패: {r.stderr[-800:]}")
    out = json.loads(r.stdout.strip().splitlines()[-1])
    out["stderr"] = r.stderr
    return out


def run_path_b(fixture: dict, out: Path) -> None:
    print("\n=== 경로 B (설치본 동기화 userdata_sync.js) ===", flush=True)
    aged, python, expect = fixture["tree"], fixture["python"], fixture["expect"]
    user_data = out / "userdata_b"
    if user_data.exists():
        shutil.rmtree(user_data)
    user_data.mkdir(parents=True)
    for d in ("data", "projects", "templates", "tokens"):
        if (fixture["aged_snapshot"] / d).exists():
            shutil.copytree(fixture["aged_snapshot"] / d, user_data / d, ignore=shutil.ignore_patterns("__pycache__"))
    # 매니페스트: 지금 것 + 은퇴 어휘 조각 하나(격리 검증)
    manifest = json.loads((ROOT / "data" / "core_manifest.json").read_text(encoding="utf-8"))
    manifest.setdefault("retired", {}).setdefault("vocab_fragments", [])
    manifest["retired"]["vocab_fragments"] = sorted(set(manifest["retired"]["vocab_fragments"]) | {fx.RETIRED_FRAGMENT})
    mpath = out / "manifest_override.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    resources = materialize_resources(out)

    # ④ 도중 죽음 재현 → 표식이 남는다
    r1 = _node_sync(user_data, mpath, resources, fail_after=3)
    check(r1["ok"] is False and (user_data / "data" / ".upgrade_pending").exists(),
          "도중 죽은 동기화는 .upgrade_pending 표식을 남긴다")
    # 다음 기동 = 되감기 후 재동기화
    r2 = _node_sync(user_data, mpath, resources)
    check(r2["ok"] is True, f"재동기화 성공 (변경 {r2.get('changed')}건)")
    check(r2["rolledBack"] >= 1, f"지난 저널로 {r2['rolledBack']}건 원상복구 후 진행")
    check(not (user_data / "data" / ".upgrade_pending").exists(), "완료 뒤 표식 회수")
    check(not (user_data / "data" / "ibl_nodes_src" / fx.RETIRED_FRAGMENT).exists(), "은퇴 어휘 조각이 자리에서 사라짐")
    backups = list((user_data / "data" / "_backups").glob("*_upgrade"))
    check(backups and any((b / "retired" / "data" / "ibl_nodes_src" / fx.RETIRED_FRAGMENT).exists() for b in backups),
          "은퇴 조각은 삭제가 아니라 _backups/<날짜>_upgrade/retired 로 격리(사용자 판정)")
    check(any((b / "journal.jsonl").exists() for b in backups), "저널(journal.jsonl) 존재")
    # ② 부팅 + ③ 보존
    fx.boot(ROOT, user_data, python, label="B-upgraded-boot")
    assert_preserved(user_data, expect, "B")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag")
    ap.add_argument("--out")
    ap.add_argument("--keep", action="store_true", help="worktree·산출물을 남긴다(디버그)")
    a = ap.parse_args()
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="indiebiz_upgrade_smoke_"))
    fixture = None
    try:
        fixture = fx.build(out, a.tag)
        # 경로 B 는 A 가 트리를 바꾸기 전의 옛 상태가 필요하다 — 스냅샷
        snap = out / "aged_snapshot"
        for d in ("data", "projects", "templates", "tokens"):
            if (fixture["tree"] / d).exists():
                shutil.copytree(fixture["tree"] / d, snap / d, ignore=shutil.ignore_patterns("__pycache__"))
        fixture["aged_snapshot"] = snap
        run_path_b(fixture, out)
        run_path_a(fixture)
        print(f"\n[upgrade-smoke] OK — {fixture['tag']} → 지금 트리, 두 경로 모두 부팅·보존·롤백·은퇴 통과", flush=True)
        return 0
    except Fail as e:
        print(f"\n[upgrade-smoke] FAILED — {e}", flush=True)
        return 1
    except Exception as e:
        print(f"\n[upgrade-smoke] ERROR — {e}", flush=True)
        return 2
    finally:
        if fixture and not a.keep:
            fx.remove_worktree(fixture["tree"])
            shutil.rmtree(out, ignore_errors=True)
        elif fixture:
            print(f"[upgrade-smoke] 산출물 보존: {out}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
