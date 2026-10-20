"""수리 뒤 같은 탐침 재실행: P8(화면 문맥 가드)·W1(목록 바이트)·P6(실패 코드)·Chrome 모양."""
import json, sqlite3, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_many import run
R = Path(__file__).resolve().parent; ROOT = R.parents[3]
ids = {"tv1": "guestpc-70e163471313", "mac26": "guestpc-9dc41d53987d", "s0": "guestpc-fc7b12fba936", "s1": "guestpc-4e51c614b25b", "yena": "guestpc-f0fa1e3465a0"}
def journal(resp):
    rid = resp.get("resume", {}).get("run_id"); p = list((ROOT / "data/ibl_runs").rglob(rid + ".sqlite"))
    db = sqlite3.connect(f"file:{p[0]}?mode=ro", uri=True); db.row_factory = sqlite3.Row
    n = collections.Counter(); b = collections.Counter()
    for r in db.execute("select request,receipt,call_info from calls"):
        a = (json.loads(r["call_info"]) or {}).get("action"); n[a] += 1; b[a] += len(r["receipt"] or "") + len(r["request"] or "")
    return {k: (n[k], b[k]) for k in n}
code = lambda name: (R / name).read_text(encoding="utf-8")
# P8 수리 뒤
_, p8 = run("post_p8_scheduler", code("probe_p8.ibl"), {"inputs": ids, "origin": "scheduler"})
v = p8["response"].get("value") or {}
print("P8 scheduler:", v.get("status"), json.dumps(v.get("failure"), ensure_ascii=False)[:260], "| journal", journal(p8["response"]))
_, p8u = run("post_p8_training", code("probe_p8.ibl"), {"inputs": ids, "origin": "training"})
v = p8u["response"].get("value") or {}
print("P8 training:", v.get("status"), json.dumps(v.get("failure"), ensure_ascii=False)[:200], "| journal", journal(p8u["response"]))
# W1 목록 바이트
_, p2 = run("post_p2_read", code("probe_p2_read.ibl"), {"inputs": {"tv1": ids["tv1"], "s0": ids["s0"]}})
print("W1 read program:", round(p2["seconds"], 1), "s | journal", journal(p2["response"]))
before = json.load(open(ROOT / "outputs/long_sentence_imagination/2026-10-20_87회차/runs/p2_read_first.json"))
print("   before:", round(before["seconds"], 1), "s | journal", journal(before["response"]))
# P6 실패 모양
_, p6 = run("post_probes_p1_p6", code("probes.ibl"), {"inputs": ids})
p = p6["response"]["value"]["p6"]
for k, vv in p.items():
    val = vv.get("value"); err = vv.get("error")
    print("P6", k, "value.failure=", json.dumps((val or {}).get("failure"), ensure_ascii=False)[:200] if val else None,
          "| error.details.failure=", json.dumps(((err or {}).get("details") or {}).get("failure"), ensure_ascii=False)[:160] if err else None)
m26 = [t for t in p6["response"]["value"]["p1"] if t["target"] == ids["mac26"]][0]
print("P1 mac26 first failure:", json.dumps(m26["items"][0].get("failure"), ensure_ascii=False)[:200])
# Chrome 모양
_, ch = run("post_chrome_status", '#!ibl edition=2\nreturn [self:script]{id:"Chrome제어",args:{op:"status"},timeout:60}', {})
cv = ch["response"]["value"]; print("Chrome status keys:", {k: cv.get(k) for k in ("status", "failure", "verified", "op")})
