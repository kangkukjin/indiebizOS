"""잠들기 도우미 — args(stdin JSON): {s: 초, i: 항목, fail_at: 항목(선택)} → INDIEBIZ_SCRIPT_RESULT 에 {i, slept}."""
import json, os, sys, time
args = json.load(sys.stdin) if not sys.stdin.isatty() else {}
s = float(args.get("s", 0.5)); i = args.get("i")
if args.get("fail_at") is not None and i == args.get("fail_at"):
    print(f"의도된 실패: 항목 {i}", file=sys.stderr); sys.exit(3)
time.sleep(s)
out = {"i": i, "slept": s}
p = os.environ.get("INDIEBIZ_SCRIPT_RESULT")
if p:
    tmp = p + ".tmp"; open(tmp, "w").write(json.dumps(out)); os.replace(tmp, p)
else:
    print(json.dumps(out))
