"""수리 검사의 실제 보고서. 셸 성공과 기능 검사 통과를 구분한다."""
import re
import shlex
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


def invocation(command, workspace):
    """단일 pytest/Node test 명령만 계측한다. 복합 셸은 일반 관측으로 남긴다."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    cwd = Path(workspace).resolve()
    if len(tokens) > 3 and tokens[0] == "cd" and tokens[2] == "&&":
        cwd = (cwd / tokens[1]).resolve()
        tokens = tokens[3:]
    if not cwd.is_relative_to(Path(workspace).resolve()):
        raise ValueError("검사 cwd가 수리 사본 밖입니다")
    if not tokens or any(re.search(r"[;&|<>`\n]", t) or "$" in t for t in tokens):
        return None
    executable = Path(tokens[0]).name
    pytest = executable in {"pytest", "pytest3"} or (
        executable.startswith("python") and tokens[1:3] == ["-m", "pytest"])
    node = executable in {"node", "nodejs"} and "--test" in tokens
    if not pytest and not node:
        return None
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
