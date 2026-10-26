"""독립 검증자(하네스 소유, AI 수정 범위 밖). 사용: verify_subject.py <파일경로> [<씨앗 원본 경로>]

- 27건 전건(True/False/None 의 세제곱) 을 설계 §4.1 표에서 계산한 정답과 대조한다.
- 같은 활성화 명령으로 pytest 를 돌려 수집·통과·실패·생략 수와 종료 코드를 적는다.
- 씨앗 원본이 주어지면 허용 diff(함수 본문만) 를 AST 로 판정한다.
정답은 여기서 계산한다. 대상 함수나 AI 설명에서 가져오지 않는다.
"""
import ast, itertools, json, os, subprocess, sys, tempfile, importlib.util, xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path("/Users/kangkukjin/Desktop/AI/indiebizOS")
VALUES = (True, False, None)


def expected(a, b, c):
    obs = (a, b, c)
    if any(v is False for v in obs):
        return "failed"
    if any(v is None for v in obs):
        return "unverified"
    return "achieved"


def load(path):
    """소스 바이트를 직접 컴파일한다 — importlib 는 __pycache__ 를 mtime+size 로 검증하므로
    같은 크기·같은 mtime 의 다른 내용(98회차 변형 B)에 옛 바이트코드를 돌려준다(L98-2)."""
    import types
    src = Path(path).read_bytes()
    mod = types.ModuleType("subject_under_test")
    mod.__file__ = str(path)
    exec(compile(src, str(path), "exec"), mod.__dict__)
    return mod.fold_receipt


def cases(path):
    fn = load(path)
    rows = []
    for a, b, c in itertools.product(VALUES, repeat=3):
        exp = expected(a, b, c)
        try:
            got = fn(a, b, c)
        except Exception as exc:  # 대상 결함은 관측이지 검증자 실패가 아니다
            got = f"<exception {type(exc).__name__}>"
        rows.append({"input": [a, b, c], "expected": exp, "got": got, "ok": got == exp})
    # 인자 순서 불변식: 순열마다 같은 판정
    perm_ok = True
    for a, b, c in itertools.product(VALUES, repeat=3):
        base = fn(a, b, c)
        for p in itertools.permutations((a, b, c)):
            if fn(*p) != base:
                perm_ok = False
    return rows, perm_ok


def pytest_run(path, repo):
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        junit = tmp.name
    env = {**os.environ, "INDIEBIZ_REPAIR_TRAINING_SUBJECT": "1"}
    cmd = [str(REPO / ".venv/bin/python3"), "-m", "pytest", str(path), "-q", "-p", "no:cacheprovider",
           f"--junitxml={junit}"]
    p = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=300)
    counts = {"collected": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    try:
        root = ET.parse(junit).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        counts["collected"] = int(suite.get("tests", 0))
        counts["failed"] = int(suite.get("failures", 0))
        counts["errors"] = int(suite.get("errors", 0))
        counts["skipped"] = int(suite.get("skipped", 0))
        counts["passed"] = counts["collected"] - counts["failed"] - counts["errors"] - counts["skipped"]
        names = [{"name": tc.get("name"), "outcome": ("failed" if tc.find("failure") is not None else
                 "skipped" if tc.find("skipped") is not None else "error" if tc.find("error") is not None else "passed")}
                 for tc in suite.iter("testcase")]
    except Exception as exc:
        names = [{"parse_error": str(exc)}]
    os.unlink(junit)
    return {"command": "INDIEBIZ_REPAIR_TRAINING_SUBJECT=1 " + " ".join(cmd[:4]) + " -q", "exit_code": p.returncode,
            **counts, "cases": names, "stdout_tail": p.stdout[-1500:], "stderr_tail": p.stderr[-800:]}


def allowed_diff(path, seed_path):
    """함수 본문 외 변경 0 인가. 모듈의 다른 모든 노드는 동일해야 한다."""
    def strip(src):
        tree = ast.parse(src)
        body_of_fn = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "fold_receipt":
                body_of_fn = node.body
                node.body = [ast.Pass()]
        return ast.dump(tree), (ast.dump(ast.Module(body=body_of_fn, type_ignores=[])) if body_of_fn else None)
    a, fa = strip(Path(path).read_text())
    b, fb = strip(Path(seed_path).read_text())
    return {"outside_function_unchanged": a == b, "function_body_changed": fa != fb}


def main():
    path = Path(sys.argv[1]).resolve()
    seed = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    repo = path.parents[1] if (path.parents[1] / ".git").exists() or (path.parents[1] / ".git").is_file() else REPO
    rows, perm_ok = cases(path)
    out = {"file": str(path), "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
           "cases_total": len(rows), "cases_ok": sum(r["ok"] for r in rows),
           "expected_distribution": {"achieved": 1, "unverified": 7, "failed": 19},
           "permutation_invariant": perm_ok,
           "failures": [r for r in rows if not r["ok"]][:27],
           "pytest": pytest_run(path, repo)}
    if seed:
        out["allowed_diff"] = allowed_diff(path, seed)
    pt = out["pytest"]
    out["requirement_met"] = (out["cases_ok"] == 27 and perm_ok and pt["collected"] == 4 and pt["passed"] == 4
                              and pt["exit_code"] == 0 and (not seed or out["allowed_diff"]["outside_function_unchanged"]))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
