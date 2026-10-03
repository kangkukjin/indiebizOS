"""기존 수리 사본의 명령·검사 영수증. 적용과 일반 셸이 같은 기록을 쓴다."""
import subprocess
import uuid
from pathlib import Path

from repair_test_results import invocation, summary


def execute(repo, session, candidate, command, controller=None, timeout=300):
    from repair_process import run
    wt = Path(repo) / session["worktree"]
    before = candidate.inventory(wt)
    env = candidate.environment(wt)
    spec = invocation(command, wt)
    def cancelled():
        if controller and controller.cancelled():
            raise PermissionError("수리가 취소됐습니다")
    cancelled()
    try:
        result = run(spec["argv"] if spec else ["/bin/sh", "-c", command], wt,
                     cwd=spec["cwd"] if spec else str(wt), timeout=timeout, check=cancelled)
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
        return {"status": "unverified", "error": "기능 검사는 단일 pytest 또는 node --test 명령으로 지정하세요. 일반 명령은 의미 검토 자료입니다."}
    current = candidate.digest(candidate.inventory(wt))
    env = candidate.environment(wt)
    prior = next((r for r in reversed(session.get("execution_checks", []))
                  if r.get("command") == command and r.get("candidate_hash") == current
                  and r.get("before_hash") == current and r.get("environment_hash") == env
                  and r.get("test_report") and r.get("status") == "passed"), None)
    if prior:
        return prior
    return execute(repo, session, candidate, command, controller)
