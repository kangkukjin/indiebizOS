"""독립 검증기 — 실행자의 result.json 과 기기별 결과를 expected.json 으로 전건 대조 (수정 없음)."""
import json, sys, hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
exp = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
out = Path(sys.argv[1])
res = json.loads((out / "result.json").read_text(encoding="utf-8"))
report = {"out": str(out), "devices": len(res.get("devices", [])), "reachable": sum(1 for d in res["devices"] if d.get("reachable")), "jobs": []}
for j in res.get("jobs", []):
    r = j.get("result") or {}
    rows = r.get("rows") or []
    ok_rows = [(a.get("id"), a.get("result"), a.get("name")) for a in rows] == [(e["id"], e["result"], e["name"]) for e in exp["rows"]]
    ident = r.get("identity") or {}
    report["jobs"].append({"device_id": j.get("device_id"), "method": j.get("method"), "reused": j.get("reused"),
        "sum_ok": r.get("sum") == exp["sum"], "rows_exact": ok_rows, "count": len(rows),
        "identity_has_device": ident.get("device_id") == j.get("device_id"), "identity": ident,
        "status_keys": sorted((j.get("status") or {}).keys()) if isinstance(j.get("status"), dict) else j.get("status"), "skipped": j.get("skipped"), "failed": j.get("failed"), "reason": j.get("reason")})
pc = res.get("photo_chain") or {}
report["photo_chain"] = {k: pc.get(k) for k in ("executed","captured","phone_sha256","phone_size","blocked_at","blocked_reason","hub_sha256","pc_sha256","all_equal","reused","reason")}
report["blocked"] = res.get("blocked")
report["report_md_exists"] = (out / "report.md").exists()
report["result_sha256"] = hashlib.sha256((out / "result.json").read_bytes()).hexdigest()
print(json.dumps(report, ensure_ascii=False, indent=1))
