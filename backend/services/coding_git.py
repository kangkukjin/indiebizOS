"""Git 시작 트리·현재 트리·고정 검토 묶음. 공유 인덱스를 snapshot에 쓰지 않는다."""
import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from coding_store import fingerprint


class CodingConflict(ValueError):
    pass


def git(root, *args, env=None, data=None, check=True):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    clean.update({"GIT_TERMINAL_PROMPT": "0", "GIT_LITERAL_PATHSPECS": "1"})
    clean.update(env or {})
    result = subprocess.run(["git", "-C", str(root), *args], input=data,
                            capture_output=True, env=clean, timeout=120)
    if check and result.returncode:
        raise CodingConflict(result.stderr.decode(errors="replace") or "Git 명령 실패")
    return result.stdout


def text_git(root, *args, **kwargs):
    return git(root, *args, **kwargs).decode().strip()


def safe_path(root, relative, *, allow_link=False):
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise ValueError("작업 공간 밖 또는 Git 메타데이터 경로")
    root = Path(root).resolve()
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError("심볼릭 링크가 작업 공간 밖을 가리킵니다")
    if not allow_link and any(p.is_symlink() for p in [target, *target.parents] if p != root):
        raise ValueError("심볼릭 링크는 직접 편집할 수 없습니다")
    return target


def identity(path):
    root = Path(path).expanduser().resolve(strict=True)
    top = Path(text_git(root, "rev-parse", "--show-toplevel")).resolve()
    if root != top:
        raise ValueError("Git 저장소의 최상위 경로를 선택하세요")
    common = text_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return root, str(Path(common).resolve())


def status(root):
    return git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").decode(errors="replace")


def untracked(root):
    return [p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0") if p]


def current_tree(root, selected=None):
    """HEAD는 중간 커밋을 포함한다. 최종 diff의 기준은 과제의 불변 start다."""
    with tempfile.TemporaryDirectory(prefix="coding-index-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git(root, "read-tree", "HEAD", env=env)
        git(root, "add", "-u", "--", ".", env=env)
        for path in untracked(root) if selected is None else selected:
            safe_path(root, path)
            if Path(path).name == ".env" or Path(path).name.startswith(".env."):
                raise ValueError("환경·자격 파일은 검토 묶음에 넣지 않습니다: " + path)
            git(root, "add", "--", path, env=env)
        return text_git(root, "write-tree", env=env)


def tree_entries(root, tree):
    entries = {}
    for item in git(root, "ls-tree", "-r", "-z", tree).split(b"\0"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        entries[path.decode()] = {"mode": mode, "kind": kind, "oid": oid}
    return entries


def delta(root, start, current):
    before, after = tree_entries(root, start), tree_entries(root, current)
    paths = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    for path in paths:
        safe_path(root, path, allow_link=True)
        if any(entry and entry["mode"] in {"120000", "160000"}
               for entry in (before.get(path), after.get(path))):
            raise ValueError("첫 버전은 링크·서브모듈 변경 반영을 지원하지 않습니다: " + path)
    patch = git(root, "diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", start, current)
    return paths, patch


def target_state(root, paths):
    head = text_git(root, "rev-parse", "HEAD")
    index = git(root, "ls-files", "--stage", "-z")
    files = {}
    for relative in paths:
        path = safe_path(root, relative)
        files[relative] = ({"sha": fingerprint(path.read_bytes()), "mode": path.stat().st_mode & 0o777}
                           if path.is_file() else None)
    return {"head": head, "index": fingerprint(index), "files": files}


def require_clean_targets(root, start, paths):
    entries = tree_entries(root, start)
    for relative in paths:
        path = safe_path(root, relative)
        expected = entries.get(relative)
        if expected is None:
            if path.exists():
                raise CodingConflict("정본의 기존 파일과 겹칩니다: " + relative)
        else:
            if not path.is_file() or text_git(root, "hash-object", "--", relative) != expected["oid"]:
                raise CodingConflict("정본의 기존 변경과 겹칩니다: " + relative)
            if bool(path.stat().st_mode & 0o111) != (expected["mode"] == "100755"):
                raise CodingConflict("정본 파일 모드가 바뀌었습니다: " + relative)
        if git(root, "diff", "--cached", "--name-only", "--", relative):
            raise CodingConflict("정본에 staged 변경이 있습니다: " + relative)


def commit_paths(root, paths, message, expected_head):
    if text_git(root, "rev-parse", "HEAD") != expected_head:
        raise CodingConflict("커밋 전 정본 HEAD가 바뀌었습니다")
    with tempfile.TemporaryDirectory(prefix="coding-commit-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git(root, "read-tree", expected_head, env=env)
        git(root, "add", "-A", "--", *paths, env=env)
        git(root, "commit", "-m", message, env=env)
    commit = text_git(root, "rev-parse", "HEAD")
    git(root, "reset", "-q", commit, "--", *paths)
    return commit
