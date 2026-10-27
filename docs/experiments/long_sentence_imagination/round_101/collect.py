"""101회차 — 보존 기록만 읽는다(world_pulse.db 읽기 전용). task_id 별 에피소드·역할별 billable usage(call_id 중복 제거)·도구 사건·cost.summary·
접근 기록(도구 입력 원문에서 금지 경로 검색). 사용: collect.py <out.json> <task_id>[,task_id...] [금지경로,...]"""
import collections, json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]; OUT = Path(sys.argv[1]); TASKS = sys.argv[2].split(","); FORBID = sys.argv[3].split(",") if len(sys.argv) > 3 else []
db = sqlite3.connect(f"file:{ROOT/'data/world_pulse.db'}?mode=ro", uri=True); db.row_factory = sqlite3.Row
report = {"usage_note": "model.usage accounting=billable_usage 를 call_id 로 중복 제거해 role·model 별 합산. input 에 캐시가 포함되는지는 공급자 계약(ClaudeCode: input/cache_read/cache_create 별도 보고)에 따르며 여기서 캐시를 다시 더하지 않는다. 훈련자(운영 세션) 토큰은 미측정.", "tasks": []}
for task_id in TASKS:
    eps = [dict(e) for e in db.execute("SELECT id,source,agent,task_id,total_ms,started_at,ended_at FROM episode_log WHERE task_id=? ORDER BY id", (task_id,))]
    rows = db.execute("SELECT run_id,event_seq,ts,kind,episode_id,data FROM trajectory_event WHERE task_id=? ORDER BY ts,event_seq", (task_id,)).fetchall()
    kinds = collections.Counter(); seen = set(); roles = {}; tools = []; cost = None; access = []; reads = []
    for r in rows:
        kind = r["kind"]; kinds[kind] += 1
        try: d = json.loads(r["data"])
        except Exception: continue
        if kind == "model.usage" and d.get("accounting") == "billable_usage":
            key = (d.get("call_id"), d.get("round_index"), d.get("role"))
            if key in seen: continue
            seen.add(key)
            k = f"{d.get('role')}|{d.get('model')}|{d.get('provider')}"
            a = roles.setdefault(k, {"calls": 0, "input": 0, "cache_read": 0, "cache_create": 0, "output": 0, "reasoning": 0, "latency_ms": 0})
            a["calls"] += 1
            for f in ("input", "cache_read", "cache_create", "output", "reasoning", "latency_ms"): a[f] += int(d.get(f) or 0)
        if kind == "supervision.tool.started":
            inp = d.get("input") or {}; full = None
            if isinstance(inp, dict) and inp.get("id") and d.get("store"):
                p = Path(d["store"]) / (inp["id"] + ".txt")
                if p.exists():
                    try: full = p.read_text(encoding="utf-8", errors="replace")
                    except Exception: full = None
            text = full if full is not None else (inp.get("excerpt") if isinstance(inp, dict) else str(inp))
            tools.append({"seq": r["event_seq"], "ts": r["ts"], "name": d.get("name"), "chars": (inp.get("chars") if isinstance(inp, dict) else None), "excerpt": (text or "")[:300], "full_available": full is not None})
            for f in FORBID:
                if f and text and f in text: access.append({"seq": r["event_seq"], "name": d.get("name"), "forbidden": f, "excerpt": text[:200]})
            for tok in ("inputs/A/", "inputs/B/", "ai_out/A/", "ai_out/B/"):
                if text and tok in text: reads.append({"seq": r["event_seq"], "name": d.get("name"), "path_token": tok})
        if kind == "supervision.cost.summary": cost = d.get("cost")
    report["tasks"].append({"task_id": task_id, "episodes": eps, "event_kinds": dict(kinds), "usage_by_role": roles, "usage_total": {f: sum(v[f] for v in roles.values()) for f in ("calls","input","cache_read","cache_create","output","reasoning")}, "tool_calls": len(tools), "tool_names": dict(collections.Counter(t["name"] for t in tools)), "tools": tools, "input_path_tokens": dict(collections.Counter(x["path_token"] for x in reads)), "forbidden_access": access, "cost_summary": cost})
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
for t in report["tasks"]: print(t["task_id"], "episodes", [e["id"] for e in t["episodes"]], "tools", t["tool_names"], "usage", t["usage_total"], "forbidden", len(t["forbidden_access"]), "paths", t["input_path_tokens"])
