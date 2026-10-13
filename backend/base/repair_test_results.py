"""수리 검사의 실제 보고서. 셸 성공과 기능 검사 통과를 구분한다."""
import json
import re
import shlex
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


def invocation(command, workspace):
    """단일 pytest/Node/Go test를 계측한다. 복합 셸은 일반 관측으로 남긴다."""
    if "\n" in command:
        return None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return None
    cwd = Path(workspace).resolve()
    if len(tokens) > 3 and tokens[0] == "cd" and tokens[2] == "&&":
        cwd = (cwd / tokens[1]).resolve()
        tokens = tokens[3:]
    if not cwd.is_relative_to(Path(workspace).resolve()):
        raise ValueError("검사 cwd가 수리 사본 밖입니다")
    # Quoted regex alternatives belong to argv; an actual pipe must never hide
    # the test process's exit code behind tail/grep's exit code.
    if not tokens or any(re.fullmatch(r"[;&|<>()]+", t) or "`" in t or "$" in t for t in tokens):
        return None
    executable = Path(tokens[0]).name
    pytest = executable in {"pytest", "pytest3"} or (
        executable.startswith("python") and tokens[1:3] == ["-m", "pytest"])
    node = executable in {"node", "nodejs"} and "--test" in tokens
    go = executable in {"go", "go.exe"} and tokens[1:2] == ["test"]
    if not pytest and not node and not go:
        return None
    if go:
        if any(t.split("=", 1)[0] in {"-json", "-c", "-o", "-exec", "-args"} for t in tokens[2:]):
            raise ValueError("Go 검사는 호스트가 -json을 지정합니다. 보고서·컴파일 전용·실행 교체 옵션을 제거하세요")
        # A cached test is not a fresh observation of this repair candidate.
        tokens.insert(2, "-json")
        if not any(t == "-count" or t.startswith("-count=") for t in tokens):
            tokens.insert(3, "-count=1")
        return {"argv": tokens, "cwd": str(cwd), "kind": "go", "report": None}
    if any(t.startswith(("--junit", "--test-reporter", "--collect-only")) for t in tokens):
        raise ValueError("검사 보고서 옵션은 호스트가 지정합니다. 명령에서 보고서/수집 전용 옵션을 제거하세요")
    report = Path(workspace).resolve() / "data/spill/repair_checks" / (uuid.uuid4().hex + ".xml")
    if pytest:
        report.parent.mkdir(parents=True, exist_ok=True)
        tokens.append("--junitxml=" + str(report))
    else:
        tokens.insert(1, "--test-reporter=tap")
    return {"argv": tokens, "cwd": str(cwd), "kind": "pytest" if pytest else "node",
            "report": str(report) if pytest else None}


def summary(spec, output, exit_code):
    result = {"kind": spec["kind"], "tests": 0, "failures": 0, "skipped": 0,
              "passed": False, "cases": []}
    try:
        if spec["kind"] == "pytest":
            path = Path(spec["report"])
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 8_000_000:
                raise ValueError("검사 보고서가 없거나 유효하지 않습니다")
            raw = path.read_text()
            if "<!DOCTYPE" in raw or "<!ENTITY" in raw:
                raise ValueError("외부 엔티티를 포함한 검사 보고서")
            rows = list(ET.fromstring(raw).iter("testcase"))
            result.update(tests=len(rows),
                          failures=sum(r.find("failure") is not None or r.find("error") is not None for r in rows),
                          skipped=sum(r.find("skipped") is not None for r in rows),
                          cases=[r.get("classname", "") + "::" + r.get("name", "") for r in rows])
        elif spec["kind"] == "go":
            result.update(_go_summary(output))
        else:
            totals = {k: int(v) for k, v in re.findall(r"(?m)^# (tests|pass|fail|cancelled|skipped|todo) (\d+)\s*$", output)}
            if not {"tests", "pass", "fail", "cancelled", "skipped", "todo"} <= totals.keys():
                raise ValueError("Node 검사 집계가 없습니다")
            result.update(tests=totals["tests"], failures=totals["fail"] + totals["cancelled"],
                          skipped=totals["skipped"] + totals["todo"],
                          cases=re.findall(r"(?m)^# Subtest: (.+)$", output))
        result["passed"] = (exit_code == 0 and result["tests"] > 0
                            and result["failures"] == 0 and result["skipped"] == 0)
    except (OSError, ValueError, ET.ParseError) as exc:
        result["error"] = str(exc)
    return result


def _go_summary(output):
    """go test -json의 테스트·패키지 종료를 대조한다(0건·skip·절단은 통과 아님)."""
    packages, active, cases = {}, set(), []
    for line in output.splitlines():
        # stderr (e.g. go: downloading) is retained beside the JSON stdout.
        if not line.lstrip().startswith("{"):
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("Go 검사 사건이 객체가 아닙니다")
        package, test, action = event.get("Package"), event.get("Test"), event.get("Action")
        if not package:
            continue
        if not isinstance(package, str) or not isinstance(action, str) or (test is not None and not isinstance(test, str)):
            raise ValueError("Go 검사 사건 필드가 유효하지 않습니다")
        if test:
            if package not in packages or packages[package] is not None:
                raise ValueError("Go 검사가 실행 중인 패키지에 속하지 않습니다")
            key = (package, test)
            if action == "run":
                if key in active:
                    raise ValueError("Go 검사 시작이 중복됐습니다")
                active.add(key)
            elif action in {"pass", "fail", "skip"}:
                if key not in active:
                    raise ValueError("Go 검사 시작 사건이 없습니다")
                active.remove(key)
                cases.append((package, test, action))
        elif action == "start":
            if package in packages:
                raise ValueError("Go 패키지 시작이 중복됐습니다")
            packages[package] = None
        elif action in {"pass", "fail", "skip"}:
            if package not in packages or packages[package] is not None:
                raise ValueError("Go 패키지 시작·종료가 일치하지 않습니다")
            packages[package] = action
    if not packages or active or any(state is None for state in packages.values()):
        raise ValueError("Go 검사 보고서가 없거나 완료되지 않았습니다")
    if any(package not in packages for package, _, _ in cases):
        raise ValueError("Go 검사 패키지 종료가 없습니다")
    failed_packages = {package for package, _, state in cases if state == "fail"}
    return {"tests": len(cases),
            "failures": sum(state == "fail" for _, _, state in cases)
            + sum(state == "fail" and package not in failed_packages for package, state in packages.items()),
            "skipped": sum(state == "skip" for _, _, state in cases),
            "cases": [package + "::" + test for package, test, _ in cases],
            "packages": packages}
