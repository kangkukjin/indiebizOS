"""Independent, read-only comparison of the saved report and execution journals (round 87)."""
import json, sqlite3, hashlib, sys
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-20_87회차"

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def journal(run_id):
    paths = list((ROOT / "data/ibl_runs").rglob(run_id + ".sqlite"))
    if len(paths) != 1: return {"found": len(paths)}
    with sqlite3.connect(f"file:{paths[0]}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        life = dict(db.execute("select * from lifecycle").fetchone())
        rows = list(db.execute("select receipt,call_info,state_change from calls"))
    kinds = Counter()
    for r in rows:
        ci = json.loads(r["call_info"]) if r["call_info"] else {}
        kinds[str(ci.get("action") or ci.get("op") or ci.get("kind") or "?")] += 1
    return {"lifecycle_status": life.get("status"), "calls": len(rows), "by_action": dict(kinds)}

def summarize(label):
    rec = read(OUT / "runs" / f"{label}.json"); resp = rec["response"]
    out = {"label": label, "seconds": round(rec["seconds"], 1), "success": resp.get("success"), "run_status": resp.get("run_status"),
           "error": (resp.get("error") or "")[:300]}
    if resp.get("resume"): out["journal"] = journal(resp["resume"]["run_id"])
    v = resp.get("value")
    if isinstance(v, dict) and v.get("saved"):
        rep = read(v["saved"]); out["report_sha"] = sha(v["saved"])
        rows_all = []
        for b in rep["branches"]:
            rows = b["rows"]; rows_all += [(b["surface"], b["target"], r) for r in rows]
            out.setdefault("branches", []).append({"surface": b["surface"], "target": b["target"][-12:], "mode": b["mode"], "count": b["count"],
                "verified": b["verified_count"], "restore": b["restore"], "error": (json.dumps(b["error"], ensure_ascii=False)[:160] if b["error"] else None),
                "actions": [(r["action"], r["status"], r["verified"], r.get("failure_stage") or r.get("failure_code")) for r in rows]})
        # P4 false-success shapes
        p4 = []
        for s, t, r in rows_all:
            raw = r.get("raw") or {}
            res = raw.get("result") if isinstance(raw, dict) else None
            if r["verified"] and isinstance(res, dict):
                if r["action"] == "apps":
                    apps = res.get("apps") or []
                    nulls = [a for a in apps if not a.get("name")]
                    if nulls: p4.append((t[-8:], "apps rows with null name", len(nulls)))
                if res == {}: p4.append((t[-8:], r["action"], "empty result"))
        out["P4_false_success_shapes"] = p4
        # P5 null+basis
        p5 = {}
        for s, t, r in rows_all:
            raw = r.get("raw") or {}; res = raw.get("result") if isinstance(raw, dict) else None
            if s == "pc" and isinstance(res, dict) and r["action"] in ("power", "display", "presence") and "windows" == res.get("platform"):
                for k in ("flags", "sleep_holders", "display_asleep", "lid_closed", "requests_basis", "asleep"):
                    if k in res: p5[f"{r['action']}.{k}"] = res[k]
        out["P5_windows_nulls"] = p5
    return out

if __name__ == "__main__":
    for label in sys.argv[1:]:
        print(json.dumps(summarize(label), ensure_ascii=False, indent=1, default=str)[:6000])
