"""P1 보조 실행부(IBL inputs Text 로 공급, ~turn 에 self:write). pytest 실행·구조화 출력·독립 검증자 호출만 맡는다.
args: {op:"pytest"|"verify"|"source"|"commit", path, repo, verifier?, seed?, commit?} → 결과 파일 JSON 하나."""
import json, os, subprocess, sys, tempfile, xml.etree.ElementTree as ET
from pathlib import Path

args = json.load(sys.stdin)
repo = Path(args.get("repo") or "/Users/kangkukjin/Desktop/AI/indiebizOS")
path = Path(args["path"])
if not path.is_absolute():
    path = repo / path
out = {"op": args.get("op", "pytest"), "path": str(path), "observed": False}
try:
    if out["op"] == "pytest":
        junit = tempfile.NamedTemporaryFile(suffix=".xml", delete=False).name
        env = {**os.environ, "INDIEBIZ_REPAIR_TRAINING_SUBJECT": "1"}
        cmd = [str(repo / ".venv/bin/python3"), "-m", "pytest", str(path), "-q", "-p", "no:cacheprovider",
               "--junitxml=" + junit]
        p = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=240)
        root = ET.parse(junit).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        cases = []
        for tc in suite.iter("testcase"):
            if tc.find("failure") is not None:
                oc, msg = "failed", (tc.find("failure").get("message") or "")[:300]
            elif tc.find("skipped") is not None:
                oc, msg = "skipped", (tc.find("skipped").get("message") or "")[:300]
            elif tc.find("error") is not None:
                oc, msg = "error", (tc.find("error").get("message") or "")[:300]
            else:
                oc, msg = "passed", ""
            cases.append({"name": tc.get("name"), "outcome": oc, "message": msg})
        os.unlink(junit)
        collected = int(suite.get("tests", 0)); failed = int(suite.get("failures", 0))
        errors = int(suite.get("errors", 0)); skipped = int(suite.get("skipped", 0))
        out.update(observed=True, command="INDIEBIZ_REPAIR_TRAINING_SUBJECT=1 " + " ".join(cmd[:5]),
                   exit_code=p.returncode, collected=collected, failed=failed, skipped=skipped, errors=errors,
                   passed=collected - failed - errors - skipped, cases=cases, output_ref=p.stdout[-1200:])
    elif out["op"] == "commit":
        import re
        commit = args.get("commit")
        if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{7,40}", commit):
            out.update(error="커밋 식별자 미관측")
        else:
            resolved = subprocess.run(["git", "rev-parse", "--verify", commit + "^{commit}"],
                                      cwd=repo, capture_output=True, text=True, timeout=30)
            rel = path.resolve().relative_to(repo.resolve()).as_posix()
            full = resolved.stdout.strip()
            if resolved.returncode:
                out.update(observed=True, matches=False, error="커밋이 존재하지 않음")
            else:
                blob = subprocess.run(["git", "show", full + ":" + rel], cwd=repo,
                                      capture_output=True, timeout=30)
                out.update(observed=True, commit=full, matches=blob.returncode == 0 and blob.stdout == path.read_bytes())
    elif out["op"] == "source":
        import ast
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        lines = src.splitlines()
        rows = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == args.get("function", "fold_receipt"):
                for ln in range(node.lineno, node.end_lineno + 1):
                    rows.append({"lineno": ln, "text": lines[ln - 1]})
        out.update(observed=True, function=args.get("function", "fold_receipt"), lines=rows,
                   sha256=__import__("hashlib").sha256(path.read_bytes()).hexdigest())
    elif out["op"] == "verify":
        cmd = [str(repo / ".venv/bin/python3"), args["verifier"], str(path)] + ([args["seed"]] if args.get("seed") else [])
        p = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=300)
        try:
            v = json.loads(p.stdout)
        except Exception:
            v = {"parse_error": p.stdout[-500:] + p.stderr[-500:]}
        out.update(observed=p.returncode == 0 and "cases_ok" in v, verifier_exit=p.returncode,
                   cases_ok=v.get("cases_ok"), cases_total=v.get("cases_total"), requirement_met=v.get("requirement_met"),
                   permutation_invariant=v.get("permutation_invariant"), allowed_diff=v.get("allowed_diff"),
                   pytest=({k: v["pytest"].get(k) for k in ("exit_code", "collected", "passed", "failed", "skipped")} if v.get("pytest") else None),
                   sha256=v.get("sha256"))
except Exception as exc:
    out.update(observed=False, error=f"{type(exc).__name__}: {exc}")
result = Path(os.environ["INDIEBIZ_SCRIPT_RESULT"])
tmp = result.with_suffix(".tmp")
tmp.write_text(json.dumps(out, ensure_ascii=False, allow_nan=False), encoding="utf-8")
tmp.replace(result)
