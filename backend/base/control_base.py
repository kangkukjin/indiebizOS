"""제어 기반(제어자·helper·프로토콜)의 고정 판본 — 수리 기반 자체의 갱신에도 복구 경로를 남긴다(G6).

설계 정본: docs/SELF_REPAIR_SYSTEM_REDESIGN_2026_10_27.md §7.3.

제어자는 가변 checkout 이 아니라 `data/restart_control/control_base/<id>/` 의 봉인 사본에서 돈다.
`api.py start` 런처가 현재 승인된 기반을 고르고(검증 통과 → current, 아니면 previous), 그 기반의
restart_controller 를 exec 한다. 운영 중 정본의 제어 파일이 바뀌면 현역 제어자가 새 기반을 봉인·검증한
뒤 인계한다(restart_controller.handover). 인계 실패는 이전 기반이 계속 소유한다.

기반이 품는 것은 OS 프로세스·파일 교체·잠금·manifest 읽기에 필요한 최소 파일이다. 모델·IBL·가이드·
업무 패키지는 들어가지 않는다 — 그 나머지(restart_red 가 함수 안에서 부르는 red_apply 등)는
현역 세대(없으면 정본)에서 import 한다. 이 두 계층의 경로 배치는 install_support_path 가 맡는다.
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

CONTROL_FILES = (
    "backend/boot_paths.py",
    "backend/base/restart_protocol.py",
    "backend/base/restart_process.py",
    "backend/base/restart_child.py",
    "backend/base/generation_store.py",
    "backend/base/control_base.py",
    "backend/base/update_maintenance.py",
    ("backend/common/completion_contract.py", "backend/base/completion_contract.py"),
    "backend/services/restart_controller.py",
    "backend/services/restart_candidates.py",
    "backend/services/restart_helper.py",
    "backend/datastore/restart_red.py",
    "backend/datastore/repair_root.py",
)
# These modules run only in the controller/helper. Shared protocol, bootstrap and
# datastore modules still require a worker generation after control acceptance.
CONTROL_ONLY_FILES = frozenset({
    "backend/services/restart_controller.py",
    "backend/services/restart_candidates.py",
    "backend/services/restart_helper.py",
})
LAYER_DIRS = ["base", "datastore", "ibl", "cognition", "services", "surface"]
SELFTEST_TIMEOUT_S = 120


def store(base):
    return Path(base) / "data" / "restart_control" / "control_base"


def _entries():
    """(정본 상대경로, 기반 안 상대경로) — 패키지 안 파일은 평면 모듈로 옮겨 기반을 자족시킨다."""
    return [(e, e) if isinstance(e, str) else tuple(e) for e in CONTROL_FILES]


def inventory(source_root):
    root = Path(source_root)
    files = {}
    for src, _ in _entries():
        p = root / src
        if p.is_file():
            files[src] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"files": files, "digest": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:32]}


def read_current(base):
    try:
        return json.loads((store(base) / "current.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"current": None, "previous": None, "failed": {}}


def write_current(base, value):
    from restart_protocol import atomic_json
    atomic_json(store(base) / "current.json", value)


def base_dir(base, control_id):
    return store(base) / control_id


def manifest_of(path):
    try:
        return json.loads((Path(path) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def running_from(path=None):
    """이 모듈이 사는 기반의 id — 기반 사본에서 돌면 폴더 이름, 정본에서 돌면 None."""
    here = Path(path or __file__).resolve()
    for parent in here.parents:
        if (parent / "manifest.json").is_file() and parent.parent.name == "control_base":
            return parent.name
    return None


def _seal(path):
    for dirpath, _, filenames in os.walk(path):
        d = Path(dirpath)
        for name in filenames:
            p = d / name
            p.chmod(stat.S_IMODE(p.stat().st_mode) & ~0o222)
        d.chmod(stat.S_IMODE(d.stat().st_mode) & ~0o222)


def _unseal(path):
    for dirpath, _, filenames in os.walk(path):
        d = Path(dirpath)
        d.chmod(stat.S_IMODE(d.stat().st_mode) | 0o700)
        for name in filenames:
            p = d / name
            p.chmod(stat.S_IMODE(p.stat().st_mode) | 0o600)


def snapshot(source_root, base):
    """정본의 제어 파일을 새 기반으로 봉인한다(멱등). 검증은 verify 가 따로 한다."""
    root = Path(source_root)
    inv = inventory(root)
    final = base_dir(base, inv["digest"])
    if manifest_of(final):
        return manifest_of(final)
    tmp = store(base) / f".building-{inv['digest']}-{os.getpid()}"
    if tmp.exists():
        _unseal(tmp)
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, mode=0o700)
    try:
        placed = {src: dst for src, dst in _entries() if src in inv["files"]}
        for src, dst in placed.items():
            target = tmp / dst
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / src, target)
        copied = {src: hashlib.sha256((tmp / dst).read_bytes()).hexdigest() for src, dst in placed.items()}
        if copied != inv["files"] or inventory(root)["files"] != inv["files"]:
            raise RuntimeError("복사 중 제어 파일이 바뀌었습니다")
        manifest = {"id": inv["digest"], "files": inv["files"], "placed": placed, "created_at": time.time(),
                    "source_root": str(root), "python": sys.executable}
        (tmp / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1),
                                            encoding="utf-8")
        _seal(tmp)
        try:
            os.rename(tmp, final)
        except OSError:
            if manifest_of(final):
                _unseal(tmp)
                shutil.rmtree(tmp, ignore_errors=True)
                return manifest_of(final)
            raise
        return manifest
    except BaseException:
        _unseal(tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def verify(base, control_id, support_root, *, timeout=SELFTEST_TIMEOUT_S):
    """기반 사본의 자기검사 — 별도 프로세스에서 제어자·수행자·프로토콜을 import 하고 상태를 읽는다.

    통과하면 VERIFIED 표식을 남긴다. 실패 원인은 current.json 의 failed 에 기록되어 같은 id 를 다시
    검증하지 않는다(정본이 바뀌면 id 가 바뀐다)."""
    path = base_dir(base, control_id)
    marker = path / "VERIFIED"
    if marker.exists():
        return True, "verified"
    code = (
        "import sys, json\n"
        f"sys.argv = ['selftest']\n"
        f"from control_base import install_support_path\n"
        f"install_support_path({str(path)!r}, {str(support_root)!r})\n"
        "import boot_paths\n"
        "import restart_protocol, restart_process, restart_child, generation_store, control_base\n"
        "import restart_controller, restart_candidates, restart_red, repair_root\n"
        "assert restart_protocol.STATE_VERSION >= 1\n"
        "assert hasattr(restart_controller, 'Controller') and hasattr(restart_controller, 'main')\n"
        "print('selftest-ok')\n"
    )
    env = dict(os.environ, INDIEBIZ_BASE_PATH=str(base), PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=str(path / "backend/base"))
    try:
        p = subprocess.run([sys.executable, "-c", code], cwd=str(path / "backend"), env=env,
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"selftest 실행 실패: {exc}"
    if p.returncode != 0 or "selftest-ok" not in p.stdout:
        return False, (p.stdout + p.stderr).strip()[-1500:]
    path.chmod(stat.S_IMODE(path.stat().st_mode) | 0o700)
    marker.write_text(str(time.time()))
    path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)
    return True, "verified"


def install_support_path(control_root, support_root):
    """기반 사본의 층을 앞에, 현역 세대(없으면 정본)의 층을 뒤에 둔다. 기반이 먼저 이긴다."""
    control_root, support_root = Path(control_root), Path(support_root)
    for root in (support_root, control_root):
        backend = root / "backend"
        entries = [str(backend / d) for d in LAYER_DIRS if (backend / d).is_dir()] + [str(backend)]
        for entry in entries:
            if entry in sys.path:
                sys.path.remove(entry)
        # support 는 뒤에, control 은 앞에 — 두 번 돌면서 control 이 마지막에 앞으로 간다
        if root == support_root:
            sys.path.extend(entries)
        else:
            sys.path[0:0] = entries


def ensure(source_root, base, support_root=None):
    """정본의 제어 파일에 맞는 기반을 봉인·검증하고 current 로 올린다. 반환 (id|None, note)."""
    base = Path(base)
    current = read_current(base)
    inv = inventory(source_root)
    cid = inv["digest"]
    if current.get("current") == cid and manifest_of(base_dir(base, cid)):
        return cid, "current"
    if cid in (current.get("failed") or {}):
        return None, "failed:" + str(current["failed"][cid])[:200]
    try:
        snapshot(source_root, base)
    except Exception as exc:
        return None, f"snapshot:{exc}"
    ok, note = verify(base, cid, support_root or source_root)
    if not ok:
        current.setdefault("failed", {})[cid] = note
        write_current(base, current)
        return None, "verify:" + note
    previous = current.get("current")
    write_current(base, {"current": cid, "previous": previous if previous != cid else current.get("previous"),
                         "failed": current.get("failed") or {}, "updated_at": time.time()})
    return cid, "promoted"


def select(source_root, base, support_root=None):
    """런처가 exec 할 기반 폴더. 정본 제어 파일을 봉인·검증해 쓰되, 실패하면 이전 승인 기반으로."""
    cid, note = ensure(source_root, base, support_root)
    current = read_current(base)
    for candidate in (cid, current.get("current"), current.get("previous")):
        if candidate and manifest_of(base_dir(base, candidate)) and (base_dir(base, candidate) / "VERIFIED").exists():
            return base_dir(base, candidate), candidate, note
    return None, None, note


def mark_failed(base, control_id, note):
    current = read_current(base)
    current.setdefault("failed", {})[control_id] = note
    if current.get("current") == control_id:
        current["current"], current["previous"] = current.get("previous"), None
    write_current(base, current)


def prune(base, keep):
    root = store(base)
    if not root.is_dir():
        return
    for entry in root.iterdir():
        if entry.is_dir() and entry.name not in keep and not entry.name.startswith("."):
            manifest = manifest_of(entry)
            if manifest and time.time() - manifest.get("created_at", 0) > 7 * 86400:
                _unseal(entry)
                shutil.rmtree(entry, ignore_errors=True)
