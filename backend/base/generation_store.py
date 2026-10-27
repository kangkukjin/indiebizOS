"""불변 실행 세대(generation) 저장소 — 정본 작업 트리의 스냅샷을 봉인해 그 사본에서 실행한다.

설계 정본: docs/SELF_REPAIR_SYSTEM_REDESIGN_2026_10_27.md §5 (G1·G2).

세대 = `data/restart_control/generations/<id>/` 한 폴더. 안에는
  - 실행 코드 사본: backend/·scripts/·mcp_server.py·requirements*·data/packages/installed/·
    data/ibl_nodes_src/·data/ibl_nodes.yaml (파일별 sha256 이 manifest 에 기록되고 읽기 전용으로 봉인)
  - 의존 환경: `.venv` 는 APFS 복제(clonefile, 쓰기 시 복사)로 바이트가 독립된 사본. 복제가
    불가능한 파일시스템이면 심볼릭 링크로 연결하고 manifest.environment.isolation 에 그 사실을 적는다.
  - 데이터 뷰: `data/` 아래 코드 쪽이 아닌 모든 항목과 저장소 최상위의 나머지 항목(frontend·docs·
    .env …)은 정본으로 가는 심볼릭 링크. `__file__` 기준으로 데이터를 찾는 코드가 정본 데이터를 본다.
    (.git·.worktrees 는 연결하지 않는다 — 세대는 git 저장소가 아니다.)
  - 패키지 안 `data/` 폴더와 git 이 무시하는 항목(DB·캐시·비밀)은 복사하지 않고 링크한다.

세대 ID = 파일 지문 + 의존 환경 신원 + 제어 프로토콜 판본의 sha256 앞 32자. HEAD 가 같아도 dirty 내용이
다르면 다른 세대다. 비밀(.env)·라이브 DB 는 사본에 복사하지 않는다(링크만).

동시 쓰기 계약: 원천을 복사 전·후 두 번 재고하고 사본도 다시 해시한다. 세 지문이 모두 같을 때만 봉인한다.
이것은 "이 파일 집합의 최종 내용이 복사 구간 동안 바뀌지 않았다" 를 증명하지, 임의 다중 파일 저장의
원자 스냅샷을 주장하지 않는다 — 편집기가 세 파일 중 하나만 저장한 순간의 재고도 일관된 한 세대다.
그 틈은 호출자의 정착 대기(quiet period)·사전검사·부팅 검증·복구가 받친다.
"""
import ctypes
import ctypes.util
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

PROTOCOL_VERSION = 2
MANIFEST = "manifest.json"
SEALED = "SEALED"

CODE_DIRS = ("backend", "scripts", "data/packages/installed", "data/ibl_nodes_src")
CODE_FILES = ("mcp_server.py", "requirements.txt", "requirements-core.txt", "data/ibl_nodes.yaml")
# 코드 쪽 경로를 뺀 나머지 data/ 항목과 최상위 항목은 정본 링크다.
CODE_TOP = {"backend", "scripts", "mcp_server.py", "requirements.txt", "requirements-core.txt", "data"}
NEVER_LINK_TOP = {".git", ".worktrees", "__pycache__", ".pytest_cache", ".hypothesis", ".DS_Store"}
DATA_CODE = {"packages", "ibl_nodes.yaml", "ibl_nodes_src"}
EXCLUDED_PARTS = {"__pycache__", ".hypothesis", ".pytest_cache", "node_modules", ".venv", ".render_workspaces",
                  ".tmp", ".git", ".DS_Store"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".db", ".db-shm", ".db-wal", ".db.bak", ".sqlite", ".sqlite3", ".log")
PACKAGE_STATE_DIRS = {"data"}       # 패키지 폴더 바로 아래 data/ = 패키지 상태(복사 않고 링크)


class CandidateChanged(RuntimeError):
    """복사 구간에 원천이 바뀌어 이 후보를 게시하지 않는다. 다음 변경을 다시 회수한다."""


class GenerationCorrupt(RuntimeError):
    """봉인된 세대의 바이트가 manifest 와 다르다."""


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _excluded(rel):
    parts = Path(rel).parts
    if set(parts) & EXCLUDED_PARTS:
        return True
    name = parts[-1]
    if name.startswith("_temp_") or name.endswith(EXCLUDED_SUFFIXES):
        return True
    if name.startswith("test_") and name.endswith(".py") or name == "conftest.py":
        return True
    # 패키지 폴더 바로 아래 data/ 는 상태다: data/packages/installed/<kind>/<pkg>/data/...
    if len(parts) > 5 and parts[:3] == ("data", "packages", "installed") and parts[5] in PACKAGE_STATE_DIRS:
        return True
    return False


def _git(root, *args):
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def code_files(source_root):
    """실행 입력 파일의 상대 경로 집합. git 이 있으면 추적+미추적(비무시) 파일, 없으면 규칙만."""
    root = Path(source_root)
    scopes = [s for s in (*CODE_DIRS, *CODE_FILES) if (root / s).exists()]
    if not scopes:
        return set()
    out = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *scopes)
    if out is not None:
        names = {os.fsdecode(x) for x in out.split(b"\0") if x}
        # 삭제됐지만 아직 인덱스에 남은 추적 파일은 실행 입력이 아니다.
        return {n for n in names if not _excluded(n) and (root / n).is_file()}
    names = set()
    for scope in scopes:
        path = root / scope
        if path.is_file():
            names.add(scope)
            continue
        for p in path.rglob("*"):
            if p.is_file() and not p.is_symlink():
                rel = p.relative_to(root).as_posix()
                if not _excluded(rel):
                    names.add(rel)
    return names


def execution_inventory(source_root):
    """실행 입력의 파일별 지문. 제어자의 변경 감시와 스냅샷이 같은 함수를 쓴다."""
    root = Path(source_root)
    files = {}
    for rel in sorted(code_files(root)):
        try:
            files[rel] = _sha(root / rel)
        except (FileNotFoundError, IsADirectoryError):
            continue  # 재고와 해시 사이에 사라진 파일 — 다음 재고가 다시 본다
    return {"files": files, "digest": digest(files)}


def environment_identity(source_root):
    """의존 환경 신원 — 설치된 배포판 메타데이터 지문(바이트 전수 아님)과 인터프리터."""
    root = Path(source_root)
    venv = root / ".venv"
    identity = {"python": sys.version.split()[0], "venv": str(venv) if venv.exists() else None}
    try:
        import importlib.metadata as metadata
        h = hashlib.sha256()
        for dist in sorted(metadata.distributions(), key=lambda d: d.metadata.get("Name", "")):
            h.update((dist.metadata.get("Name", "") + "=" + dist.version).encode())
            base = Path(getattr(dist, "_path", ""))
            for name in ("RECORD", "METADATA"):
                p = base / name
                if p.is_file():
                    st = p.stat()
                    h.update(f"{p.name}:{st.st_size}:{st.st_mtime_ns}".encode())
        identity["distributions"] = h.hexdigest()
    except Exception as exc:  # 메타데이터를 못 읽는 환경 — 신원 없음을 숨기지 않는다
        identity["distributions"] = None
        identity["error"] = f"{type(exc).__name__}: {exc}"
    return identity


def generation_id(inventory, environment, protocol_version=PROTOCOL_VERSION):
    return digest({"files": inventory["files"], "environment": environment.get("distributions"),
                   "python": environment.get("python"), "protocol": protocol_version})[:32]


def _clonefile(src, dst):
    """APFS 디렉터리 복제(쓰기 시 복사). 성공 True, 미지원/실패 False."""
    if sys.platform != "darwin":
        return False
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        libc.clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
        return libc.clonefile(os.fsencode(str(src)), os.fsencode(str(dst)), 0) == 0
    except (OSError, AttributeError):
        return False


def _link(target, link):
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(target), str(link), target_is_directory=target.is_dir())


def _ignored_entries(root, scope):
    """git 이 무시하는 항목(디렉터리는 하나로). 상태·캐시·비밀을 복사 대신 링크하기 위해."""
    out = _git(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory", "--", scope)
    if out is None:
        return []
    return [os.fsdecode(x).rstrip("/") for x in out.split(b"\0") if x]


def _populate(source_root, target, files):
    """코드 복사 + 상태·데이터 링크. 반환: 링크 목록(상대경로)."""
    root, links = Path(source_root), []
    for rel in files:
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst, follow_symlinks=True)
    # 패키지 상태(패키지 안 data/)·git 무시 항목은 정본으로 링크한다.
    for scope in CODE_DIRS:
        base = root / scope
        if not base.is_dir():
            continue
        for rel in _ignored_entries(root, scope):
            src, dst = root / rel, target / rel
            parts = Path(rel).parts
            if set(parts) & {"__pycache__", ".pytest_cache", ".hypothesis"} or dst.exists() or os.path.lexists(dst):
                continue
            if src.exists():
                _link(src, dst)
                links.append(rel)
    if (root / "data/packages/installed").is_dir():
        for kind in (root / "data/packages/installed").iterdir():
            if not kind.is_dir():
                continue
            for pkg in kind.iterdir():
                for state_dir in PACKAGE_STATE_DIRS:
                    src = pkg / state_dir
                    dst = target / src.relative_to(root)
                    if src.is_dir() and not os.path.lexists(dst):
                        _link(src, dst)
                        links.append(src.relative_to(root).as_posix())
    # data/ 뷰: 코드 쪽이 아닌 모든 항목은 정본 링크.
    data = root / "data"
    (target / "data").mkdir(exist_ok=True)
    if data.is_dir():
        for entry in data.iterdir():
            if entry.name in DATA_CODE or entry.name in NEVER_LINK_TOP:
                continue
            _link(entry, target / "data" / entry.name)
            links.append(("data/" + entry.name))
        packages = data / "packages"
        if packages.is_dir():
            (target / "data/packages").mkdir(exist_ok=True)
            for entry in packages.iterdir():
                if entry.name == "installed" or entry.name in NEVER_LINK_TOP:
                    continue
                _link(entry, target / "data/packages" / entry.name)
                links.append("data/packages/" + entry.name)
    for entry in root.iterdir():
        if entry.name in CODE_TOP or entry.name in NEVER_LINK_TOP or entry.name == ".venv":
            continue
        if not os.path.lexists(target / entry.name):
            _link(entry, target / entry.name)
            links.append(entry.name)
    return links


def _isolate_environment(source_root, target):
    venv = Path(source_root) / ".venv"
    if not venv.is_dir():
        return {"isolation": "none", "path": None}
    dst = target / ".venv"
    if _clonefile(venv, dst):
        return {"isolation": "clonefile", "path": str(dst)}
    _link(venv, dst)
    return {"isolation": "symlink", "path": str(dst),
            "note": "복제 불가 파일시스템 — 의존 환경 바이트는 정본과 공유된다. 환경 변경은 신원 드리프트로만 관측한다."}


def _seal_readonly(target, files):
    """봉인 = 파일 바이트를 읽기 전용으로. 디렉터리는 그대로 둔다(파이썬 캐시·잔류 회수·정리가 가능해야 한다).
    새 파일이 세대 안에 생기면 residue()/extra_code_files() 가 드러낸다 — 바이트 교체는 막고 관측은 남긴다."""
    for rel in files:
        p = target / rel
        mode = stat.S_IMODE(p.stat().st_mode)
        p.chmod(mode & ~0o222)


def _unseal(target):
    for dirpath, dirnames, filenames in os.walk(target):
        d = Path(dirpath)
        try:
            d.chmod(stat.S_IMODE(d.lstat().st_mode) | 0o700)
        except OSError:
            pass
        for name in filenames:
            p = d / name
            try:
                if not p.is_symlink():
                    p.chmod(stat.S_IMODE(p.lstat().st_mode) | 0o600)
            except OSError:
                pass


def read_manifest(generation_dir):
    path = Path(generation_dir) / MANIFEST
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sealed(generation_dir):
    g = Path(generation_dir)
    return g.is_dir() and (g / SEALED).exists() and read_manifest(g) is not None


def snapshot(source_root, store, *, environment=None, source_inventory=None, extra=None):
    """정본 작업 트리를 새 세대로 봉인한다. 같은 내용이면 기존 세대를 돌려준다(멱등)."""
    root, store = Path(source_root).resolve(), Path(store)
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    inventory = source_inventory or execution_inventory(root)
    environment = environment or environment_identity(root)
    gid = generation_id(inventory, environment)
    final = store / gid
    if sealed(final):
        return read_manifest(final)
    tmp = store / f".building-{gid}-{os.getpid()}"
    if tmp.exists():
        _unseal(tmp)
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(mode=0o700)
    started = time.time()
    try:
        files = sorted(inventory["files"])
        links = _populate(root, tmp, files)
        env = _isolate_environment(root, tmp)
        copied = {rel: _sha(tmp / rel) for rel in files}
        if copied != inventory["files"]:
            raise CandidateChanged("복사 중 원천 파일 내용이 바뀌었습니다")
        again = execution_inventory(root)
        if again["files"] != inventory["files"]:
            changed = sorted(p for p in set(again["files"]) | set(inventory["files"])
                             if again["files"].get(p) != inventory["files"].get(p))
            raise CandidateChanged("복사 구간에 원천이 바뀌었습니다: " + ", ".join(changed[:8]))
        head = _git(root, "rev-parse", "HEAD")
        dirty = _git(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", *CODE_DIRS, *CODE_FILES)
        manifest = {
            "generation": gid, "protocol": PROTOCOL_VERSION, "created_at": started,
            "source_root": str(root), "source_digest": inventory["digest"], "files": inventory["files"],
            "file_count": len(files), "links": links, "environment": {**environment, **env},
            "base_commit": head.decode().strip() if head else None,
            "dirty_inputs": sorted({os.fsdecode(e[3:]) for e in dirty.split(b"\0") if len(e) > 3}
                                   if dirty is not None else []),
            "python": sys.executable, "sealed_by": os.getpid(), "extra": extra or {},
        }
        (tmp / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
        (tmp / SEALED).write_text(str(time.time()))
        _seal_readonly(tmp, files)
        try:
            os.rename(tmp, final)
        except OSError:
            if sealed(final):   # 같은 세대를 다른 쪽이 먼저 봉인했다
                _unseal(tmp)
                shutil.rmtree(tmp, ignore_errors=True)
                return read_manifest(final)
            raise
        return manifest
    except BaseException:
        _unseal(tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def verify(generation_dir, *, files=None):
    """봉인된 사본의 바이트가 manifest 와 같은지 확인한다. 다르면 GenerationCorrupt."""
    g = Path(generation_dir)
    manifest = read_manifest(g)
    if not manifest or not (g / SEALED).exists():
        raise GenerationCorrupt("봉인되지 않은 세대: " + str(g))
    expected = manifest["files"] if files is None else {k: manifest["files"][k] for k in files if k in manifest["files"]}
    for rel, sha in expected.items():
        p = g / rel
        if not p.is_file() or _sha(p) != sha:
            raise GenerationCorrupt("세대 바이트 불일치: " + rel)
    return manifest


def python_executable(generation_dir):
    """세대의 인터프리터 — 복제된 .venv 가 있으면 그것(의존 바이트가 세대에 고정), 없으면 현재 것."""
    g = Path(generation_dir)
    for candidate in (g / ".venv/bin/python3", g / ".venv/Scripts/python.exe"):
        if candidate.exists() and not (g / ".venv").is_symlink():
            return str(candidate)
    return sys.executable


def syntax_check(generation_dir, manifest=None):
    """사본의 모든 .py 를 파싱한다(기존 preflight 의 구문 검사). 첫 오류를 예외로."""
    import ast
    g = Path(generation_dir)
    manifest = manifest or read_manifest(g) or {}
    for rel in sorted(manifest.get("files", {})):
        if rel.endswith(".py"):
            ast.parse((g / rel).read_bytes(), filename=rel)


def extra_code_files(generation_dir):
    """봉인 뒤 코드 디렉터리에 생긴 manifest 밖 파일 — 세대 안으로 새어 들어온 쓰기(캐시 제외)."""
    g = Path(generation_dir)
    manifest = read_manifest(g) or {}
    known = set(manifest.get("files", {}))
    links = set(manifest.get("links", []))
    out = []
    for scope in CODE_DIRS:
        base = g / scope
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.is_symlink():
                continue
            rel = p.relative_to(g).as_posix()
            if rel in known or any(rel == l or rel.startswith(l + "/") for l in links):
                continue
            if set(Path(rel).parts) & {"__pycache__", ".pytest_cache"}:
                continue
            out.append(rel)
    return sorted(out)


def residue(generation_dir):
    """세대 안에서 데이터처럼 새로 생긴 항목 — `__file__` 기준으로 쓴 코드가 남긴 것(정본 데이터가 아니다)."""
    g = Path(generation_dir)
    manifest = read_manifest(g) or {}
    known = set(manifest.get("files", [])) | set(manifest.get("links", []))
    out = []
    data = g / "data"
    if data.is_dir():
        for entry in data.iterdir():
            rel = "data/" + entry.name
            if rel not in known and entry.name not in DATA_CODE and not entry.is_symlink():
                out.append(rel)
        packages = data / "packages"
        if packages.is_dir():
            for entry in packages.iterdir():
                rel = "data/packages/" + entry.name
                if entry.name != "installed" and rel not in known and not entry.is_symlink():
                    out.append(rel)
    return sorted(out)


def salvage(generation_dir, source_root, log=lambda m: None):
    """은퇴 세대의 데이터 잔류를 정본으로 옮긴다. 정본에 같은 경로가 있으면 덮지 않고 남긴다."""
    g, root, moved, kept = Path(generation_dir), Path(source_root), [], []
    for rel in residue(g):
        src, dst = g / rel, root / rel
        if os.path.lexists(dst):
            kept.append(rel)
            continue
        try:
            _unseal(src) if src.is_dir() else None
            shutil.move(str(src), str(dst))
            moved.append(rel)
        except OSError as exc:
            kept.append(rel + f" ({exc})")
    if moved or kept:
        log(f"세대 {g.name} 데이터 잔류 — 정본으로 이동 {moved}, 보존 {kept}")
    return {"moved": moved, "kept": kept}


def remove(generation_dir):
    g = Path(generation_dir)
    if not g.exists():
        return
    _unseal(g)
    shutil.rmtree(g, ignore_errors=True)


def prune(store, keep, *, source_root=None, keep_latest=3, log=lambda m: None):
    """현역·직전·참조 중 세대와 최근 keep_latest 를 남기고 나머지를 지운다. 잔류는 먼저 회수한다."""
    store = Path(store)
    if not store.is_dir():
        return []
    keep = {Path(k).name for k in keep if k}
    rows = []
    for entry in store.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith(".building-"):
            try:
                if time.time() - entry.stat().st_mtime > 3600:
                    remove(entry)
            except OSError:
                pass
            continue
        manifest = read_manifest(entry) or {}
        rows.append((manifest.get("created_at", 0), entry))
    rows.sort(reverse=True)
    removed = []
    for index, (_, entry) in enumerate(rows):
        if entry.name in keep or index < keep_latest:
            continue
        if source_root:
            salvage(entry, source_root, log)
        remove(entry)
        removed.append(entry.name)
    return removed
