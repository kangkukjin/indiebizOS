"""Sequential probe runner: P1/P6 → P2 (first + reuse) → P3 (lost receipts) → P8 (scheduler origin) → Chrome variant B."""
import json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_many import run, OUT
R = Path(__file__).resolve().parent
ids = {"tv1": "guestpc-70e163471313", "mac26": "guestpc-9dc41d53987d", "s0": "guestpc-fc7b12fba936", "s1": "guestpc-4e51c614b25b", "yena": "guestpc-f0fa1e3465a0"}
def code(name): return (R / name).read_text(encoding="utf-8")
def brief(label, rec):
    r = rec["response"]; v = r.get("value")
    print(f"== {label} {rec['seconds']:.1f}s success={r.get('success')} run={r.get('resume',{}).get('run_id','')[:8]} err={str(r.get('error') or '')[:200]}")
    print(json.dumps(v, ensure_ascii=False, default=str)[:1200]); sys.stdout.flush()
t0 = time.time(); print(time.strftime("%H:%M:%S"))
# P1 + P6
_, rec = run("probes_p1_p6", code("probes.ibl"), {"inputs": ids}); brief("probes_p1_p6", rec)
# P2 first then reuse
_, first = run("p2_read_first", code("probe_p2_read.ibl"), {"inputs": {"tv1": ids["tv1"], "s0": ids["s0"]}}); brief("p2_read_first", first)
rid = first["response"].get("resume", {}).get("run_id")
_, again = run("p2_read_reuse", code("probe_p2_read.ibl"), {"inputs": {"tv1": ids["tv1"], "s0": ids["s0"]}, "reuse": {"run_id": rid}}); brief("p2_read_reuse", again)
# P3 lost receipts: step1 pending with 대기:0, tamper task ids, step2 확인
_, s1 = run("p3_step1", code("probe_p3_step1.ibl"), {"inputs": ids}); brief("p3_step1", s1)
v = s1["response"].get("value") or {}
def tamper(rec):
    rec = json.loads(json.dumps(rec)); tr = rec.get("task_ref") or {}
    tr["task_id"] = "l87lost" + "0" * 25; rec["task_ref"] = tr; return rec
if v.get("android") and v.get("pc"):
    _, s2 = run("p3_step2_tampered", code("probe_p3_step2.ibl"), {"inputs": {"작업a": tamper(v["android"]), "작업p": tamper(v["pc"])}}); brief("p3_step2_tampered", s2)
# P8 origin scheduler
_, p8 = run("p8_scheduler", code("probe_p8.ibl"), {"inputs": ids, "origin": "scheduler"}); brief("p8_scheduler", p8)
# Chrome variant B
print("== chrome_b"); sys.stdout.flush()
print(subprocess.run([sys.executable, str(R / "chrome_b.py")], capture_output=True, text=True, timeout=600).stdout[-3000:])
print(time.strftime("%H:%M:%S"), f"total {time.time()-t0:.0f}s")
