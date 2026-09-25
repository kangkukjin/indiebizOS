"""Five-run median: identical pure plans, baseline vs repaired Runtime."""
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_v2_compile import compile_program  # noqa: E402
from ibl_v2_runtime import Runtime  # noqa: E402

source = subprocess.check_output(
    ["git", "show", "34304426:backend/ibl/ibl_v2_runtime.py"], cwd=ROOT, text=True)
baseline = types.ModuleType("round57_baseline")
sys.modules[baseline.__name__] = baseline
exec(compile(source, "baseline_runtime.py", "exec"), baseline.__dict__)
scenarios = {
    "repeat1000": "$sum=0\n[repeat:1000]{$sum=$sum+$i}\nreturn $sum",
    "each1000": "[table:each]{items:$xs}{return $it*2}",
}
summary = {}
for name, code in scenarios.items():
    inputs = {"xs": list(range(1000))} if name.startswith("each") else {}
    plan = compile_program(code, inputs=inputs)
    entry = {}
    for label, runtime in [("before", baseline.Runtime), ("after", Runtime)]:
        times = []
        for _ in range(5):
            start = time.perf_counter()
            result = runtime(plan, inputs).run()
            times.append((time.perf_counter() - start) * 1000)
        assert result["success"], result
        entry[label] = {
            "median_ms": round(statistics.median(times), 2),
            "events": len(result["evidence"]),
            "edges": sum(len(e["parents"]) for e in result["evidence"]),
            "value": result["value"] if name.startswith("repeat") else [result["value"][0], result["value"][-1]],
        }
    summary[name] = entry
print(json.dumps(summary, ensure_ascii=False, indent=2))
