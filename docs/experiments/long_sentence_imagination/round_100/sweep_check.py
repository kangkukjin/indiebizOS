"""100회차 P0 — 보존 프로그램 검사 회귀 스윕. round_84..99 의 모든 .ibl 을 입력 없이 check:true 로 보내고
UNBOUND(입력 부재) 를 뺀 진단 코드를 모은다. 실행 0. 결과 JSON 한 장."""
import json, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]; EXP = ROOT / "docs/experiments/long_sentence_imagination"
OUT = Path(sys.argv[1]); lo, hi = int(sys.argv[2]), int(sys.argv[3])
def check(code):
    body = {"code": code, "edition": 2, "check": True, "origin": "training", "project_id": "study", "inputs": {}}
    req = urllib.request.Request("http://127.0.0.1:8765/ibl/execute", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return json.load(r)
    except urllib.error.HTTPError as e: return {"http_error": e.code, "body": e.read().decode()[:300]}
    except Exception as e: return {"transport_error": str(e)[:200]}
rows = []
for n in range(lo, hi + 1):
    d = EXP / f"round_{n}"
    if not d.is_dir(): continue
    for f in sorted(d.glob("*.ibl")):
        code = f.read_text(encoding="utf-8"); t = time.time(); res = check(code); sec = round(time.time() - t, 2)
        issues = res.get("issues") or []
        codes = {}
        for i in issues:
            c = i.get("code") or "?"; codes.setdefault(c, []).append((i.get("message") or "")[:140])
        non_unbound = {c: v for c, v in codes.items() if c != "UNBOUND"}
        rows.append({"round": n, "file": f.name, "chars": len(code), "edition_line": code.splitlines()[0][:40] if code else "", "seconds": sec,
                     "ok": res.get("ok"), "http_error": res.get("http_error"), "transport_error": res.get("transport_error"),
                     "issue_count": len(issues), "unbound": len(codes.get("UNBOUND", [])), "other_codes": {c: len(v) for c, v in non_unbound.items()},
                     "other_samples": {c: v[:3] for c, v in non_unbound.items()}, "error": (json.dumps(res.get("error"), ensure_ascii=False)[:200] if res.get("error") else None)})
        print(f"round_{n}/{f.name}: ok={res.get('ok')} issues={len(issues)} unbound={rows[-1]['unbound']} other={rows[-1]['other_codes']} {sec}s", flush=True)
summary = {"files": len(rows), "ok_true": sum(1 for r in rows if r["ok"] is True), "only_unbound": sum(1 for r in rows if r["issue_count"] and not r["other_codes"]),
           "with_other": sum(1 for r in rows if r["other_codes"]), "http_or_transport_errors": sum(1 for r in rows if r["http_error"] or r["transport_error"]),
           "other_code_totals": {}}
for r in rows:
    for c, k in r["other_codes"].items(): summary["other_code_totals"][c] = summary["other_code_totals"].get(c, 0) + k
OUT.write_text(json.dumps({"summary": summary, "rows": rows, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=1))
print(json.dumps(summary, ensure_ascii=False))
