"""수리 사본의 기준·검사·적용 바이트. 원장은 신뢰된 호스트만 쓴다."""
import base64
import hashlib
import json
import os
import stat
import subprocess
import shutil
from contextlib import contextmanager
from pathlib import Path

VERSION = 1
PRIVATE = (".git", ".worktrees", "data/system_ai_state", "data/restart_control",
           "data/_backups", "data/spill", "data/script_runs", "data/backend_keeper_off")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def environment(worktree):
    from python_environment_lock import fingerprint as python_fingerprint
    npm = Path(worktree) / "frontend/node_modules/.package-lock.json"
    return digest({"python": python_fingerprint(worktree, details=True)["environment"],
                   "npm": fingerprint(npm)})


def target(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or any(
            relative == p or relative.startswith(p + "/") for p in PRIVATE):
        raise ValueError("수리 경로가 보호 영역 또는 사본 밖입니다: " + relative)
    path = root / rel
    if not path.resolve().is_relative_to(root):
        raise ValueError("수리 경로의 심볼릭 링크가 사본 밖을 가리킵니다: " + relative)
    # 파일뿐 아니라 부모 링크도 거절한다. 적용 시 부모를 바꿔 다른 곳에 쓰지 않는다.
    if any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)):
        raise ValueError("수리 변경에 심볼릭 링크를 사용할 수 없습니다: " + relative)
    return path


def fingerprint(path):
    path = Path(path)
    if not path.exists():
        return None
    if path.is_symlink():
        return {"link": os.readlink(path)}
    if not path.is_file():
        raise ValueError("일반 파일이 아닌 수리 대상: " + str(path))
    return {"sha": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": stat.S_IMODE(path.stat().st_mode)}


def inventory(root):
    p = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                       cwd=root, capture_output=True, timeout=120)
    if p.returncode:
        raise ValueError("수리 사본의 파일 목록을 읽지 못했습니다")
    names = {os.fsdecode(x) for x in p.stdout.split(b"\0") if x}
    return {name: fingerprint(Path(root) / name) for name in sorted(names)
            if not any(name == p or name.startswith(p + "/") for p in PRIVATE)
            and not set(Path(name).parts) & {"__pycache__", ".pytest_cache", "node_modules", ".venv"}}


def initialize(repo, session):
    wt = Path(repo) / session["worktree"]
    session["baseline"] = inventory(wt)
    session["candidate_version"] = VERSION
    session["root_task_id"] = session.get("root_task_id") or session["key"]
    session["execution_checks"] = []


def collect(repo, session):
    """실제 사본 델타를 수집한다. 시작 시 가져온 타인의 미커밋 변경은 델타가 아니다."""
    baseline = session.get("baseline")
    if baseline is None:
        raise ValueError("기준 지문 없는 옛 수리 사본입니다. 새 기준으로 다시 준비해야 합니다")
    root = Path(repo).resolve()
    wt = root / session["worktree"]
    current = inventory(wt)
    files = {}
    for rel in sorted(set(baseline) | set(current)):
        before, after = baseline.get(rel), current.get(rel)
        if before == after:
            continue
        live, staged = target(root, rel), target(wt, rel)
        if (before or {}).get("link") or (after or {}).get("link"):
            raise ValueError("심볼릭 링크 변경은 지원하지 않습니다: " + rel)
        if staged.exists() and staged.stat().st_nlink != 1:
            raise ValueError("하드 링크 변경은 지원하지 않습니다: " + rel)
        files[str(live)] = {"rel": rel, "staged": str(staged),
                            "op": "write" if after else "delete", "existed": bool(before),
                            "base_sha": (before or {}).get("sha"), "base": before,
                            "candidate": after}
    session["files"] = files
    return current


def conflicts(repo, session, current=None):
    current = current if current is not None else inventory(Path(repo) / session["worktree"])
    live = inventory(repo)
    # 보수적 의존 범위: 사본의 전체 추적/비무시 입력. 예약 후 조용한 동기화는 없다.
    return [p for p in set(session["baseline"]) | set(live)
            if live.get(p) != session["baseline"].get(p)]


def invalidate(session):
    session.pop("readiness", None)
    session.pop("sealed", None)


def refresh(repo, session):
    """준비 이전에만 미수정 의존 파일을 동기화한다. 수리 델타와 충돌하면 보존한다."""
    current = collect(repo, session)
    live = inventory(repo)
    baseline = session["baseline"]
    changed = [p for p in set(live) | set(baseline) if live.get(p) != baseline.get(p)]
    collisions = [p for p in changed if current.get(p) not in (baseline.get(p), live.get(p))]
    if collisions:
        raise ValueError("정본과 사본 모두 수정한 파일의 충돌: " + ", ".join(sorted(collisions)))
    wt = Path(repo) / session["worktree"]
    for rel in changed:
        dst, src = target(wt, rel), target(repo, rel)
        if live.get(rel) is None:
            dst.unlink(missing_ok=True)
            baseline.pop(rel, None)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            baseline[rel] = live[rel]
    if changed:
        invalidate(session)
    return collect(repo, session)


def ignored_source_files(worktree):
    """검사에는 쓰였지만 Git 무시 규칙 때문에 적용 묶음에서 빠질 코드는 거절한다."""
    scopes = ["backend", "scripts", "frontend/src", "data/packages/installed/tools",
              "data/ibl_nodes_src", "data/scripts"]
    result = subprocess.run(["git", "ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", *scopes],
                            cwd=worktree, capture_output=True, check=True, timeout=60)
    caches = {"__pycache__", ".pytest_cache", ".hypothesis", "node_modules", ".venv"}
    return [os.fsdecode(name) for name in result.stdout.split(b"\0") if name
            and Path(os.fsdecode(name)).suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".yaml", ".yml"}
            and not set(Path(os.fsdecode(name)).parts) & caches]


def seal(repo, session, checks, decision, criteria):
    hidden = ignored_source_files(Path(repo) / session["worktree"])
    if hidden:
        raise ValueError("적용 묶음에서 누락된 무시 대상 소스: " + ", ".join(hidden[:12]))
    current = collect(repo, session)
    if conflicts(repo, session, current):
        raise ValueError("정본 기준이 변경됐습니다. 사본에 동기화하고 다시 검증하세요")
    if not session["files"]:
        raise ValueError("반영할 수리 델타가 없습니다")
    payload = {}
    for rec in session["files"].values():
        data = Path(rec["staged"]).read_bytes() if rec["op"] != "delete" else None
        if data is not None and hashlib.sha256(data).hexdigest() != rec["candidate"]["sha"]:
            raise ValueError("고정 중 사본이 변경됐습니다")
        payload[rec["rel"]] = {"before": rec["base"], "after": rec["candidate"],
                               "before_data": base64.b64encode(Path(repo, rec["rel"]).read_bytes()).decode()
                               if rec["base"] else None,
                               "data": base64.b64encode(data).decode() if data is not None else None}
    for rel, item in payload.items():
        if item["before_data"] is not None and hashlib.sha256(base64.b64decode(item["before_data"])).hexdigest() != item["before"]["sha"]:
            raise ValueError("고정 중 정본이 변경됐습니다: " + rel)
    session["sealed"] = payload
    session["readiness"] = {"version": 2 if session.get("repair_policy") == 2 else VERSION, "candidate_hash": digest(current),
                            "environment_hash": environment(Path(repo) / session["worktree"]),
                            "bundle_hash": digest(payload), "criteria": criteria,
                            "criteria_hash": digest(criteria), "checks": checks,
                            "decision": decision, "owner": session.get("owner"),
                            "root_task_id": session["root_task_id"],
                            "activation_commands": session.get("activation_commands", {})}


def validate(repo, session):
    ready, payload = session.get("readiness") or {}, session.get("sealed") or {}
    expected_version = 2 if session.get("repair_policy") == 2 else VERSION
    if (ready.get("version") != expected_version or not payload
            or ready.get("decision", {}).get("status") != "APPROVED"
            or ready.get("bundle_hash") != digest(payload)
            or ready.get("criteria_hash") != digest(ready.get("criteria"))
            or ready.get("owner") != session.get("owner")
            or ready.get("root_task_id") != session.get("root_task_id")):
        raise ValueError("유효한 사본 준비 판정이 없습니다")
    cancelled = Path(repo) / "data/system_ai_state/repair_continuations" / (session["root_task_id"] + ".cancel")
    if cancelled.exists():
        raise ValueError("취소된 수리입니다")
    if ignored_source_files(Path(repo) / session["worktree"]):
        raise ValueError("검증 이후 적용 묶음에 없는 소스가 생겼습니다")
    current = inventory(Path(repo) / session["worktree"])
    if digest(current) != ready["candidate_hash"]:
        raise ValueError("검증 이후 사본이 변경됐습니다. 준비 판정이 무효입니다")
    if environment(Path(repo) / session["worktree"]) != ready.get("environment_hash"):
        raise ValueError("검증 이후 실행 의존 환경이 변경됐습니다")
    drift = conflicts(repo, session, current)
    if drift:
        raise ValueError("정본 충돌: " + ", ".join(sorted(drift)[:12]))
    plan = []
    for rel, item in payload.items():
        path = target(repo, rel)
        data = base64.b64decode(item["data"], validate=True) if item["data"] is not None else None
        if data is not None and hashlib.sha256(data).hexdigest() != item["after"]["sha"]:
            raise ValueError("고정된 수리 바이트가 손상됐습니다")
        if fingerprint(path) != item["before"]:
            raise ValueError("적용 직전 정본 충돌: " + rel)
        plan.append((path, data, item))
    return plan


def commit(repo, session, body):
    """기존 각인 실행기에 수리 델타만 전달한다. 공유 인덱스/시작 미커밋 변경은 보존한다."""
    import tempfile
    if (session.get("commit") or {}).get("success"):
        return session["commit"]
    if session.get("status") != "applied" or not session.get("verified"):
        return {"success": False, "error": "적용 확인 전에는 커밋하지 않습니다"}
    payload = session.get("sealed") or {}
    if not payload or digest(payload) != (session.get("readiness") or {}).get("bundle_hash"):
        return {"success": False, "error": "커밋할 검증 묶음이 없습니다"}
    for rel, item in payload.items():
        if fingerprint(target(repo, rel)) != item["after"]:
            return {"success": False, "error": "적용 후 정본 변경: " + rel}
    marker = "Repair-Attempt: " + session["root_task_id"] + ":" + session["readiness"]["bundle_hash"]
    found = subprocess.run(["git", "log", "-1", "--format=%H", "--fixed-strings", "--grep=" + marker],
                           cwd=repo, capture_output=True, text=True, timeout=30)
    if found.returncode == 0 and found.stdout.strip():
        return {"success": True, "commit": found.stdout.strip(), "recovered": True}
    with tempfile.TemporaryDirectory(prefix="repair-commit-") as directory:
        root = Path(directory)
        (root / "old").mkdir()
        (root / "new").mkdir()
        for rel, item in payload.items():
            for side, field, state in (("old", "before_data", "before"), ("new", "data", "after")):
                if item[field] is not None:
                    data = base64.b64decode(item[field], validate=True)
                    p = root / side / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(data)
                    p.chmod(item[state]["mode"])
                    subprocess.run(["git", "hash-object", "-w", "--stdin"], input=data,
                                   cwd=repo, capture_output=True, check=True, timeout=30)
        diff = subprocess.run(["git", "diff", "--no-index", "--binary", "old", "new"],
                              cwd=root, capture_output=True, text=True, timeout=30)
        if diff.returncode not in (0, 1):
            return {"success": False, "error": diff.stderr}
        patch = "".join(line.replace("a/old/", "a/").replace("b/new/", "b/")
                        if line.startswith(("diff --git ", "--- ", "+++ ")) else line
                        for line in diff.stdout.splitlines(keepends=True))
        result = body.op_commit({"paths": list(payload), "message": "수리 사본 검증 후 반영\n\n" + marker},
                                index_patch=patch, trusted_root=str(repo))
        if result.get("success"):
            result["commit"] = result["items"][0]["커밋"]
        return result


@contextmanager
def locked(repo, key, *, nonblocking=False):
    """동시 적용/편집 진입을 직렬화한다. OS 미지원이면 쓰기 경로를 열지 않는다."""
    import fcntl
    path = Path(repo) / "data/system_ai_state/repair_sessions" / (key + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def activation(repo, session, field, command, save):
    """이미 실행한 활성 확인은 영수증으로 회수한다. 결과 불명 명령은 반복하지 않는다."""
    import uuid
    from red_apply import _run_post_verify
    from restart_protocol import read_json
    records = session.setdefault("activation_checks", {})
    record = records.get(field)
    expected = hashlib.sha256(command.encode()).hexdigest()
    if record is None:
        path = Path(repo) / "data/system_ai_state/repair_check_outputs" / (uuid.uuid4().hex + ".json")
        record = records[field] = {"state": "running", "command_sha256": expected, "output_path": str(path)}
        save(repo, session)
        receipt = _run_post_verify(repo, command, receipt_path=path)
        record.update(state="passed" if receipt.get("exit_code") == 0 else "failed", receipt=receipt)
        save(repo, session)
    elif record.get("state") == "running":
        path = Path(record.get("output_path", "")).resolve()
        home = Path(repo).resolve() / "data/system_ai_state/repair_check_outputs"
        receipt = read_json(path) if path.is_relative_to(home) else None
        if receipt and receipt.get("command_sha256") == record.get("command_sha256") == expected:
            record.update(state="passed" if receipt.get("exit_code") == 0 else "failed", receipt=receipt)
            save(repo, session)
    return record
