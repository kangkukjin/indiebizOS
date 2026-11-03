"""기존 수리 사본의 명령·검사 영수증. 적용과 일반 셸이 같은 기록을 쓴다."""
import os
import shutil
import shlex
import subprocess
import uuid
from pathlib import Path

from repair_test_results import invocation, selected_invocation, summary


def execute(repo, session, candidate, command, controller=None, timeout=300):
    from repair_process import run
    wt = Path(repo) / session["worktree"]
    before = candidate.collect(repo, session)
    env = candidate.execution_environment(wt, session)
    spec = invocation(command, wt)
    def cancelled():
        if controller and controller.cancelled():
            raise PermissionError("수리가 취소됐습니다")
    cancelled()
    failure_kind = None
    selection = {"command": command, "instrumented": bool(spec)}
    try:
        expression = selected_invocation(command, wt)
        if expression:
            picked = run(expression["selector"], wt, readonly=True, timeout=timeout, check=cancelled)
            selected = shlex.split(picked.stdout) if picked.returncode == 0 else []
            selection.update(selector=expression["selector"], selected=selected,
                             selector_output=picked.stdout, selector_diagnostic=picked.stderr)
            if not selected or any(p.startswith("-") or not (wt / p.split("::")[0]).resolve().is_relative_to(wt.resolve())
                                   for p in selected):
                raise OSError("시험 선택 실패: " + picked.stdout + picked.stderr)
            spec = invocation(shlex.join([*expression["prefix"], *selected, *expression["suffix"]]), wt)
            if spec is None:
                raise OSError("선택된 검사는 단일 pytest 명령이어야 합니다")
            selection["instrumented"] = True
        # 앞머리 대입(VAR=값)은 판정기가 떼어 spec["env"] 에 담는다 — 자식 환경에 얹어야 시험 프로세스에 닿는다.
        child_env = {**os.environ, **spec["env"], **spec.get("observer_env", {})} if spec else None
        shell = ([shutil.which("bash"), "-e", "-o", "pipefail", "-c", command]
                 if shutil.which("bash") else ["/bin/sh", "-e", "-c", command])
        result = run(spec["argv"] if spec else shell, wt,
                     cwd=spec["cwd"] if spec else str(wt), timeout=timeout, check=cancelled, env=child_env)
        output = result.stdout + result.stderr
        exit_code = result.returncode
    except (subprocess.TimeoutExpired, OSError) as exc:
        failure_kind = ("timeout" if isinstance(exc, subprocess.TimeoutExpired) else
                        "cancelled" if controller and controller.cancelled() else "environment")
        exit_code = 124 if failure_kind == "timeout" else 130 if failure_kind == "cancelled" else 126
        output = "\n".join(x.decode("utf-8", "replace") if isinstance(x, bytes) else x
                           for x in (getattr(exc, "stdout", None), getattr(exc, "stderr", None), str(exc)) if x)
    after = candidate.collect(repo, session)
    after_env = candidate.execution_environment(wt, session)
    report = summary(spec, output, exit_code) if spec else None
    unchanged = before == after and env == after_env
    status = ("passed" if report and report["passed"] and unchanged else
              "failed" if exit_code or report and report["failures"] else "unverified")
    if not unchanged:
        failure_kind = "candidate_changed"
    elif not failure_kind and exit_code:
        from repair_live_probe import failure_kind as classify
        failure_kind = classify(output, exit_code)
        if failure_kind == "check" and report and report.get("error"):
            failure_kind = "execution_incomplete"
    record = {"id": uuid.uuid4().hex, "command": command, "exit_code": exit_code, "status": status,
              "candidate_hash": candidate.digest(after), "before_hash": candidate.digest(before),
              "environment_hash": after_env, "output": output, "test_report": report,
              "failure_kind": failure_kind, "selection": selection,
              "changed_files": sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))}
    if controller:
        record["evidence_ref"] = controller.store.evidence(record)
    session.setdefault("execution_checks", []).append(record)
    from execution_situation import emit
    subject = {'kind': 'code_candidate', 'workspace': str(wt.resolve()), 'session': session.get('id')}
    emit(subject, 'version', {}, source='repair_check',
         subject_revision=record['candidate_hash'])
    emit(subject, 'validation:tests', {'status': status, 'exit_code': exit_code,
                                     'test_report': report}, source='repair_check',
         source_ref=record.get('evidence_ref') or {'check_id': record['id']},
         subject_revision=record['before_hash'],
         relation=[{'subject': subject, 'revision': record['before_hash']}])
    candidate.invalidate(session)
    return record


def check(repo, session, candidate, command, controller):
    wt = Path(repo) / session["worktree"]
    if not isinstance(command, str) or len(command) > 4000 or (invocation(command, wt) is None and selected_invocation(command, wt) is None):
        return {"status": "unverified", "error": "기능 검사는 단일 pytest, node --test 또는 go test 명령으로 지정하세요. "
                "파이프·복합 셸·빌드는 검사 영수증이 아닙니다. 빌드 뒤 검사를 별도 실행하세요. "
                "앞머리 환경변수 대입(VAR=값 명령)은 허용되며 시험 프로세스의 환경으로 전달됩니다."}
    current = candidate.digest(candidate.collect(repo, session))
    env = candidate.execution_environment(wt, session)
    prior = next((r for r in reversed(session.get("execution_checks", []))
                  if r.get("command") == command and r.get("candidate_hash") == current
                  and r.get("before_hash") == current and r.get("environment_hash") == env
                  and r.get("test_report") and r.get("status") == "passed"), None)
    if prior:
        return prior
    return execute(repo, session, candidate, command, controller)
