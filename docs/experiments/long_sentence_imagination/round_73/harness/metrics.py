"""읽기 전용 회계 — 73회차 이후 에피소드(id>4787)의 도구 호출·역할별 토큰·압축 횟수, 훈련자 run 요약."""
import collections, json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-15_73회차"
SINCE = int(sys.argv[1]) if len(sys.argv) > 1 else 4787
db = sqlite3.connect(f"file:{ROOT}/data/world_pulse.db?mode=ro", uri=True); db.row_factory = sqlite3.Row
report = {"token_note": "input 은 공급자 보고값. cache_read/create 는 별도 표시, input 에 더하지 않음. 훈련자(작성자) 토큰 미측정.", "ai": [], "trainer": []}
for ep in db.execute("SELECT id,source,task_id,total_ms,started_at,ended_at FROM episode_log WHERE id>? ORDER BY id", (SINCE,)):
    events = [(r["kind"], json.loads(r["data"])) for r in db.execute("SELECT kind,data FROM trajectory_event WHERE episode_id=? ORDER BY event_seq", (ep["id"],))]
    roles = {}; seen = set(); tools = collections.Counter(); total = collections.Counter(); ibl_codes = []
    for kind, data in events:
        if kind == "supervision.tool.started":
            tools[data.get("name", "unknown")] += 1
            if data.get("name") == "execute_ibl":
                code = ((data.get("input") or {}).get("code") or "")
                ibl_codes.append(code[:120].replace("\n", " ⏎ "))
        if kind != "model.usage" or data.get("accounting") != "billable_usage": continue
        key = (data.get("call_id"), data.get("round_index"), data.get("role"))
        if key in seen: continue
        seen.add(key); r = roles.setdefault(data.get("role", "unknown"), collections.Counter())
        for f in ("input", "output", "cache_read", "cache_create"):
            r[f] += data.get(f, 0) or 0; total[f] += data.get(f, 0) or 0
    report["ai"].append({**dict(ep), "tools": dict(tools), "usage": dict(total), "roles": {k: dict(v) for k, v in roles.items()},
        "recall_presented": sum(k == "recall.presented" for k, _ in events), "recall_used": sum(k == "recall.used" for k, _ in events),
        "compactions": sum(k == "context.compacted" for k, _ in events), "ibl_heads": ibl_codes[:60]})
for p in sorted((OUT / "runs").glob("*.json")):
    d = json.loads(p.read_text()); r = d.get("response", {})
    if "run_status" not in r: continue
    report["trainer"].append({"label": p.stem, "wall_s": round(d.get("ended", 0) - d.get("started", 0), 3), "success": r.get("success"),
        "usage": {k: (r.get("usage") or {}).get(k) for k in ("steps", "rows", "elapsed_ms")}})
(HERE / "evidence/metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
for a in report["ai"]: print(a["id"], a["source"], a["task_id"], a["total_ms"], a["tools"], a["usage"], "compact", a["compactions"])
