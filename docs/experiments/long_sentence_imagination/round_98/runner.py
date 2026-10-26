"""P1 보조 실행부(98회차). IBL inputs Text 로 공급돼 ~turn 에 self:write 된다.
좁은 시험 도우미만 맡는다: pytest 실행·구조화 출력, 함수 소스·해시, 독립 검증자 호출, 소유 fixture 쓰기, 사본 변경 파일 목록.
값 전달·분기·판정·보고 조합은 IBL 에 남긴다.
args(stdin JSON): {op:"pytest"|"source"|"verify"|"write"|"changed"|"sha", ...} → INDIEBIZ_SCRIPT_RESULT 에 JSON 하나."""
import hashlib, json, os, subprocess, sys, tempfile, xml.etree.ElementTree as ET
from pathlib import Path

args = json.load(sys.stdin)
repo = Path(args.get("repo") or "/Users/kangkukjin/Desktop/AI/indiebizOS")
raw = args.get("path")
path = Path(raw) if raw else None
if path is not None and not path.is_absolute():
    path = repo / path
op = args.get("op", "pytest")
out = {"op": op, "path": str(path) if path else None, "observed": False}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
try:
    if op == "pytest":
        junit = tempfile.NamedTemporaryFile(suffix=".xml", delete=False).name
        env = {**os.environ}
        enabled = args.get("enabled", True)
        if enabled:
            env["INDIEBIZ_REPAIR_TRAINING_SUBJECT"] = "1"
        else:
            env.pop("INDIEBIZ_REPAIR_TRAINING_SUBJECT", None)
        cmd = [str(repo / ".venv/bin/python3"), "-m", "pytest", str(path), "-q", "-p", "no:cacheprovider", "--junitxml=" + junit]
        out["command"] = ("INDIEBIZ_REPAIR_TRAINING_SUBJECT=1 " if enabled else "") + " ".join(cmd[:5])
        out["candidate_sha256"] = sha(path)
        p = subprocess.run(cmd, cwd=path.parents[1], env=env, capture_output=True, text=True, timeout=float(args.get("timeout", 240)))
        root = ET.parse(junit).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        cases = []
        for tc in suite.iter("testcase"):
            for oc in ("failure", "skipped", "error"):
                node = tc.find(oc)
                if node is not None:
                    cases.append({"name": tc.get("name"), "outcome": "failed" if oc == "failure" else oc, "message": (node.get("message") or "")[:300]}); break
            else:
                cases.append({"name": tc.get("name"), "outcome": "passed", "message": ""})
        os.unlink(junit)
        collected = int(suite.get("tests", 0)); failed = int(suite.get("failures", 0))
        errors = int(suite.get("errors", 0)); skipped = int(suite.get("skipped", 0))
        out.update(observed=True, exit_code=p.returncode, collected=collected, failed=failed, skipped=skipped, errors=errors,
                   passed=collected - failed - errors - skipped, cases=cases, output_ref=p.stdout[-800:])
    elif op == "source":
        import ast
        src = path.read_text(encoding="utf-8"); tree = ast.parse(src); lines = src.splitlines(); rows = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == args.get("function", "fold_receipt"):
                rows = [{"lineno": ln, "text": lines[ln - 1]} for ln in range(node.lineno, node.end_lineno + 1)]
        out.update(observed=True, function=args.get("function", "fold_receipt"), lines=rows, sha256=sha(path), size=path.stat().st_size)
    elif op == "verify":
        cmd = [str(repo / ".venv/bin/python3"), args["verifier"], str(path)] + ([args["seed"]] if args.get("seed") else [])
        p = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=300)
        try:
            v = json.loads(p.stdout)
        except Exception:
            v = {"parse_error": p.stdout[-500:] + p.stderr[-500:]}
        out.update(observed=p.returncode == 0 and "cases_ok" in v, verifier_exit=p.returncode,
                   cases_ok=v.get("cases_ok"), cases_total=v.get("cases_total"), requirement_met=v.get("requirement_met"),
                   permutation_invariant=v.get("permutation_invariant"), allowed_diff=v.get("allowed_diff"),
                   counterexamples=(v.get("failures") or [])[:5],
                   pytest=({k: v["pytest"].get(k) for k in ("exit_code", "collected", "passed", "failed", "skipped")} if v.get("pytest") else None),
                   sha256=v.get("sha256"))
    elif op == "write":
        before = sha(path) if path.exists() else None
        st = path.stat() if path.exists() else None
        if args.get("append"):
            data = path.read_text(encoding="utf-8") + args["content"]
        elif args.get("old") is not None:
            cur = path.read_text(encoding="utf-8")
            if cur.count(args["old"]) != 1:
                raise ValueError("old 가 정확히 한 번 나오지 않음: %d" % cur.count(args["old"]))
            data = cur.replace(args["old"], args["new"], 1)
        else:
            data = args["content"]
        path.write_text(data, encoding="utf-8")
        if args.get("keep_mtime") and st is not None:
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
        # mtime_ns 는 JSON 도구 경계의 정수 범위를 넘는다(98회차 실행 수정 1주기) — 문자열로 넘긴다.
        out.update(observed=True, sha_before=before, sha_after=sha(path), size_before=(st.st_size if st else None),
                   size_after=path.stat().st_size, mtime_before=(str(st.st_mtime_ns) if st else None), mtime_after=str(path.stat().st_mtime_ns))
    elif op == "changed":
        wt = Path(args["worktree"]); wt = wt if wt.is_absolute() else repo / wt
        p = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "-z"], cwd=wt, capture_output=True, timeout=60)
        rows = [e[3:] for e in p.stdout.decode().split("\0") if len(e) > 3]
        base = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "-z"], cwd=repo, capture_output=True, timeout=60)
        live_dirty = [e[3:] for e in base.stdout.decode().split("\0") if len(e) > 3]
        # 사본 worktree 는 체크아웃 드리프트(L97-5: csv·.venv)를 보이므로 라이브 비교는 범위 판정에 쓸 수 없다(98회차 실행 수정 2주기).
        # exclude(제안 직후 기준선) 를 주면 그 뒤 생긴 변경만 남기되 allowed(허용 파일)는 항상 포함한다.
        exclude = {e.get("rel") if isinstance(e, dict) else e for e in (args.get("exclude") or [])}
        allowed = args.get("allowed")
        delta = sorted((set(rows) - exclude) | ({allowed} & set(rows))) if "exclude" in args else sorted(set(rows) - set(live_dirty))
        out.update(observed=p.returncode == 0, files=[{"rel": r} for r in sorted(rows)], delta=[{"rel": r} for r in delta],
                   delta_vs_live=[{"rel": r} for r in sorted(set(rows) - set(live_dirty))])
    elif op == "sha":
        out.update(observed=path.exists(), sha256=(sha(path) if path.exists() else None), size=(path.stat().st_size if path.exists() else None))
except subprocess.TimeoutExpired as exc:
    out.update(observed=False, error="TimeoutExpired", timeout=True, partial_output=(exc.stdout or b"")[-400:].decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else str(exc.stdout)[-400:])
except Exception as exc:
    out.update(observed=False, error=f"{type(exc).__name__}: {exc}")
result = Path(os.environ["INDIEBIZ_SCRIPT_RESULT"]); tmp = result.with_suffix(".tmp")
tmp.write_text(json.dumps(out, ensure_ascii=False, allow_nan=False), encoding="utf-8"); tmp.replace(result)
