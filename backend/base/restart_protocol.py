"""재기동 요청/상태 파일 계약. 제어자만 상태를 쓰고 요청자는 inbox만 쓴다."""
import ast
import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

STATE_VERSION = 1
PHASES = {"ACTIVE", "CHECKING", "DRAINING", "STOPPING", "STARTING", "RECOVERING", "FAILED", "STOPPED"}


def control_dir(base):
    return Path(base) / "data" / "restart_control"


def atomic_json(path, value):
    """동일 디렉토리 rename + 파일/디렉토리 fsync. 비밀을 담는 파일은 0600."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


class OwnerLock:
    """커널 잠금. PID 파일 존재/숫자는 잠금을 대신하지 않는다."""
    def __init__(self, path):
        self.path, self.file = Path(path), None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            return False
        return True

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


def code_manifest(code_root):
    """가변 checkout의 검사 묶음. R2 불변 산출물/후보 준비는 하지 않는다.

    백엔드와 패키지 실행 소스·의존 선언을 hash한다. DB/비밀/사용자 산출물은 안 읽는다.
    """
    root = Path(code_root)
    paths = []
    for folder in (root / "backend", root / "data/packages/installed"):
        if folder.is_dir():
            paths.extend(p for p in folder.rglob("*") if p.is_file()
                         and (p.suffix == ".py" or p.name in {"ibl_actions.yaml", "tool.json", "package.json"})
                         and "__pycache__" not in p.parts
                         and not p.name.startswith("test_")
                         and (not p.name.startswith("_") or p.name == "__init__.py")
                         and p.name != "conftest.py"
                         and (folder.name != "backend" or p.suffix == ".py"))
    for name in ("mcp_server.py", "requirements.txt", "requirements-core.txt"):
        if (root / name).is_file():
            paths.append(root / name)
    manifest = {}
    for path in sorted(set(paths)):
        manifest[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return {"digest": digest, "files": manifest}


def preflight(code_root, manifest):
    root = Path(code_root)
    for rel, digest in manifest["files"].items():
        data = (root / rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("검사 중 코드가 바뀌었습니다")
        if rel.endswith(".py"):
            ast.parse(data, filename=rel)
    if code_manifest(root) != manifest:
        raise ValueError("검사 중 manifest가 바뀌었습니다")


def request(base, reason, *, request_id=None, expected_generation=None,
            artifact_digest=None, policy=None, operation="restart", payload=None):
    home = control_dir(base)
    state = read_json(home / "state.json", {})
    rid = request_id or secrets.token_hex(16)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", rid):
        raise ValueError("request_id 형식 오류")
    if operation not in {"restart", "shutdown", "red_apply", "red_verify", "cancel"}:
        raise ValueError("알 수 없는 제어 요청")
    req = {"version": STATE_VERSION, "request_id": rid, "reason": str(reason),
           "expected_generation": expected_generation or state.get("generation"),
           "artifact_digest": artifact_digest or state.get("code_digest"),
           "policy": policy or {"drain_timeout_s": 600, "force": False},
           "operation": operation, "payload": payload or {}, "created_at": time.time()}
    dest = home / "requests" / (rid + ".json")
    # 같은 ID의 payload가 바뀌면 거절한다. 재전달은 생성시각을 바꾸지 않는다.
    lock = OwnerLock(home / "inbox.lock")
    deadline = time.monotonic() + 10
    while not lock.acquire():
        if time.monotonic() > deadline:
            raise TimeoutError("요청 잠금 대기 초과")
        time.sleep(0.02)
    try:
        old = read_json(dest)
        if old:
            if expected_generation is not None and old.get("expected_generation") != expected_generation:
                raise ValueError("같은 request_id의 generation을 바꿀 수 없습니다")
            if artifact_digest is not None and old.get("artifact_digest") != artifact_digest:
                raise ValueError("같은 request_id의 artifact를 바꿀 수 없습니다")
            for field in ("reason", "operation", "payload", "policy"):
                if old.get(field) != req[field]:
                    raise ValueError("같은 request_id에 다른 요청을 보낼 수 없습니다")
            return old
        atomic_json(dest, req)
        return req
    finally:
        lock.close()


def wait_result(base, request_id, timeout=900):
    deadline = time.monotonic() + timeout
    path = control_dir(base) / "results" / (request_id + ".json")
    while time.monotonic() < deadline:
        result = read_json(path)
        if result is not None:
            return result
        time.sleep(0.2)
    return {"outcome": "pending", "request_id": request_id}
