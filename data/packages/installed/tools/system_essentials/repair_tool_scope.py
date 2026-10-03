"""승인된 자기수리 도구의 공통 경로와 실행 증거. 일반 작업에는 적용하지 않는다."""
import json
import os
import re
import uuid
from pathlib import Path

FILE_TOOLS = {"read_op", "read_file", "write_file", "edit_file", "list_directory", "make_directory",
        "delete_path", "move_path", "copy_path", "run_command", "patch_op", "grep_files", "glob_files"}
PATHS = {"path", "root_path", "file_path", "target", "dir_path", "src", "source", "dest", "destination", "args_file"}


def prepare(self_module, name, payload, project):
    if name == "body_op" and payload.get("op") == "commit":
        raise PermissionError("수리 델타의 각인은 self:patch apply 이후 적용 서비스가 수행합니다")
    if name not in FILE_TOOLS and name != "script_op":
        return dict(payload), project
    st, repo, key = self_module._staging_mod(), str(self_module._REPO_ROOT), self_module._staging_key()
    from repair_context import activation_only
    if activation_only():
        if name not in {"read_file", "read_op", "list_directory", "patch_op"} or (
                name == "patch_op" and payload.get("op") not in {"status", "apply"}):
            raise PermissionError("적용 이후에는 활성 확인만 합니다. 추가 결함은 같은 root의 복구 단계에서 수리하세요")
        return dict(payload), repo
    if name == "patch_op":
        return dict(payload), repo
    sess = st.ensure_session(repo, key)
    if not sess:
        raise PermissionError("수리 사본을 확보하지 못했습니다. 정본은 변경하지 않습니다")
    from repair_continuation import cancelled
    if cancelled({"root_task_id": sess.get("root_task_id", key)}, repo):
        raise PermissionError("취소된 수리입니다")
    wt, root = (Path(repo) / sess["worktree"]).resolve(), Path(repo).resolve()
    result = dict(payload)
    if name in {"glob_files", "grep_files"}:
        # 메타 색인은 정본을 가리키므로 사본의 실제 파일만 탐색한다.
        pattern = payload.get("pattern" if name == "glob_files" else "file_pattern") or ""
        if os.path.isabs(pattern) or ".." in Path(pattern).parts:
            raise ValueError("수리 검색 패턴은 사본의 검색 루트 안에서만 사용합니다")
        if not result.get("path") and not result.get("root_path"):
            result["path"] = "."
    if name == "patch_op":
        return result, str(root)  # 적용자는 정본을 소유. 일반 파일 도구와 구별한다.
    from runtime_utils import expand_body_path
    for field in PATHS & result.keys():
        if not isinstance(result[field], str):
            raise ValueError("수리 파일 경로는 문자열이어야 합니다")
        path = Path(expand_body_path(result[field]))
        if path.is_absolute():
            if path.is_relative_to(wt):
                rel = path.relative_to(wt).as_posix()
            elif path.is_relative_to(root):
                rel = path.relative_to(root).as_posix()
            else:
                raise PermissionError("수리 파일 도구는 같은 사본만 읽고 씁니다. 외부 의존성은 격리 셸로 읽으세요")
        else:
            rel = path.as_posix()
        from script_workspace import current_scope, workspace, prepare_path
        candidate = (wt / rel).resolve()
        if current_scope() and candidate.is_relative_to(workspace().resolve()):
            prepare_path(candidate)
            result[field] = str(candidate)
        else:
            result[field] = str(st._candidate.target(wt, rel))
    return result, str(wt)


def run_shell(handler, command, timeout):
    from repair_process import run
    from supervision_bus import current
    st, repo, key = handler._staging_mod(), str(handler._REPO_ROOT), handler._staging_key()
    sess = st.ensure_session(repo, key)
    if not sess:
        raise PermissionError("수리 사본이 없습니다")
    candidate = st._candidate
    wt = Path(repo) / sess["worktree"]
    if sess.get("repair_policy") == 2:
        from repair_check_runner import execute
        # Preparation occurs before the command; apply itself never syncs or builds.
        candidate.refresh(repo, sess)
        record = execute(repo, sess, candidate, command, current(), timeout)
        st._save_session(repo, sess)
        return {"success": record["exit_code"] == 0, "exit_code": record["exit_code"],
                "output": record["output"],
                "verification": {k: v for k, v in record.items() if k != "output"}, "worktree": str(wt)}
    before = candidate.digest(candidate.inventory(wt))
    before_env = candidate.environment(wt)
    controller = current()
    def check():
        if controller and controller.cancelled():
            raise PermissionError("수리가 취소됐습니다")
    import subprocess
    try:
        result = run(["/bin/sh", "-c", command], wt, timeout=timeout, check=check)
        output = result.stdout + result.stderr
    except (subprocess.TimeoutExpired, PermissionError) as exc:
        result = subprocess.CompletedProcess(command, 124 if isinstance(exc, subprocess.TimeoutExpired) else 130, "", "")
        chunks = [getattr(exc, "stdout", None), getattr(exc, "stderr", None), str(exc)]
        output = "\n".join(c.decode("utf-8", "replace") if isinstance(c, bytes) else c
                           for c in chunks if c)
    after = candidate.digest(candidate.collect(repo, sess))
    after_env = candidate.environment(wt)
    # 종료 코드와 내부 검사 결과는 별개다. skip·0건·실패를 초록으로 승격하지 않는다.
    passed = result.returncode == 0 and bool(output.strip()) and before == after and before_env == after_env
    if re.search(r"(?:no tests ran|collected 0 items|\b[1-9]\d* (?:failed|errors?|skipped)\b)", output):
        passed = False
    try:
        internal = json.loads(output)
        if isinstance(internal, dict) and (internal.get("ok") is False or internal.get("success") is False):
            passed = False
    except ValueError:
        pass
    record = {"id": uuid.uuid4().hex, "command": command, "exit_code": result.returncode,
              "status": "passed" if passed else "unverified" if result.returncode == 0 else "failed",
              "candidate_hash": after, "output": output, "before_hash": before,
              "environment_hash": after_env}
    if controller:
        record["evidence_ref"] = controller.store.evidence(record)
    sess.setdefault("execution_checks", []).append(record)
    candidate.invalidate(sess)
    st._save_session(repo, sess)
    return {"success": result.returncode == 0, "exit_code": result.returncode,
            "output": output, "verification": {k: v for k, v in record.items() if k != "output"},
            "worktree": str(wt)}


def record_write(st, repo, key, result):
    session = st.load_session(repo, key)
    st._candidate.collect(repo, session)
    st._candidate.invalidate(session)
    st._save_session(repo, session)
    try:
        parsed = json.loads(result)
    except (ValueError, TypeError):
        parsed = {"success": not str(result).startswith("Error:"), "message": str(result)}
    if isinstance(parsed, dict) and parsed.get("success", True) and not parsed.get("error"):
        parsed.update(staged=True, worktree=session["worktree"],
                      message="격리 사본에 변경을 보존했습니다. 정본 무변경. 요청 전체를 검증한 뒤 apply 하세요")
        return json.dumps(parsed, ensure_ascii=False)
    return result
