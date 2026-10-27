"""기존 수리 사본의 명령·검사 영수증. 적용과 일반 셸이 같은 기록을 쓴다."""
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from repair_test_results import invocation, summary


def execute(repo, session, candidate, command, controller=None, timeout=300):
    from repair_process import run
    wt = Path(repo) / session["worktree"]
    before = candidate.collect(repo, session)
    env = candidate.environment(wt)
    spec = invocation(command, wt)
    def cancelled():
        if controller and controller.cancelled():
            raise PermissionError("수리가 취소됐습니다")
    cancelled()
    try:
        # 앞머리 대입(VAR=값)은 판정기가 떼어 spec["env"] 에 담는다 — 자식 환경에 얹어야 시험 프로세스에 닿는다.
        child_env = {**os.environ, **spec["env"]} if spec and spec.get("env") else None
        shell = ([shutil.which("bash"), "-e", "-o", "pipefail", "-c", command]
                 if shutil.which("bash") else ["/bin/sh", "-e", "-c", command])
        result = run(spec["argv"] if spec else shell, wt,
                     cwd=spec["cwd"] if spec else str(wt), timeout=timeout, check=cancelled, env=child_env)
        output = result.stdout + result.stderr
        exit_code = result.returncode
    except (subprocess.TimeoutExpired, PermissionError) as exc:
        exit_code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 130
        output = "\n".join(x.decode("utf-8", "replace") if isinstance(x, bytes) else x
                           for x in (getattr(exc, "stdout", None), getattr(exc, "stderr", None), str(exc)) if x)
    after = candidate.collect(repo, session)
    after_env = candidate.environment(wt)
    report = summary(spec, output, exit_code) if spec else None
    unchanged = before == after and env == after_env
    status = ("passed" if report and report["passed"] and unchanged else
              "failed" if exit_code or report and report["failures"] else "unverified")
    record = {"id": uuid.uuid4().hex, "command": command, "exit_code": exit_code, "status": status,
              "candidate_hash": candidate.digest(after), "before_hash": candidate.digest(before),
              "environment_hash": after_env, "output": output, "test_report": report,
              "changed_files": sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))}
    if controller:
        record["evidence_ref"] = controller.store.evidence(record)
    session.setdefault("execution_checks", []).append(record)
    candidate.invalidate(session)
    return record


def check(repo, session, candidate, command, controller):
    wt = Path(repo) / session["worktree"]
    if not isinstance(command, str) or len(command) > 4000 or invocation(command, wt) is None:
        return {"status": "unverified", "error": "기능 검사는 단일 pytest, node --test 또는 go test 명령으로 지정하세요. "
                "파이프·복합 셸·빌드는 검사 영수증이 아닙니다. 빌드 뒤 검사를 별도 실행하세요. "
                "앞머리 환경변수 대입(VAR=값 명령)은 허용되며 시험 프로세스의 환경으로 전달됩니다."}
    current = candidate.digest(candidate.collect(repo, session))
    env = candidate.environment(wt)
    prior = next((r for r in reversed(session.get("execution_checks", []))
                  if r.get("command") == command and r.get("candidate_hash") == current
                  and r.get("before_hash") == current and r.get("environment_hash") == env
                  and r.get("test_report") and r.get("status") == "passed"), None)
    if prior:
        return prior
    return execute(repo, session, candidate, command, controller)
