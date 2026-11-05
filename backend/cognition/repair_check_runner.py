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
    try:
        spec = invocation(command, wt)
    except ValueError:
        spec = None  # 계측하지 못하는 합법적인 명령도 그대로 실행하고 출력을 전달한다.
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
    report = summary(spec, output, exit_code) if spec else None
    status = "failed" if exit_code else "passed" if report and report["passed"] else "unverified"
    if not failure_kind and exit_code:
        from repair_live_probe import failure_kind as classify
        failure_kind = classify(output, exit_code)
    record = {"id": uuid.uuid4().hex, "command": command, "exit_code": exit_code, "status": status,
              "output": output, "test_report": report, "failure_kind": failure_kind,
              "selection": selection, "workspace": str(wt.resolve())}
    if controller:
        record["evidence_ref"] = controller.store.evidence(record)
    session.setdefault("execution_checks", []).append(record)
    # 관측은 명령의 결과다. 셸 조회마다 사본 전체와 설치 환경을 승인/무효화하지 않는다.
    return record


def check(repo, session, candidate, command, controller):
    """명시적 실행은 항상 새 관측을 만든다. 과거 성공/실패 캐시가 대신하지 않는다."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("실행할 command 문자열이 필요합니다")
    return execute(repo, session, candidate, command, controller)
