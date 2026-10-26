"""읽기 전용 관측자(T1 동안). 10초 간격으로 전이만 기록한다 — 파일·원장·설정을 바꾸지 않는다."""
import json, os, subprocess, sys, time, glob, hashlib
from pathlib import Path
ROOT = Path("/Users/kangkukjin/Desktop/AI/indiebizOS")
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-26_97회차/ai/observe.jsonl"
SUBJECT = ROOT / "backend/test_repair_training_subject.py"
deadline = time.time() + float(sys.argv[1]) if len(sys.argv) > 1 else time.time() + 1500
prev = None
def snap():
    st = json.loads((ROOT / "data/restart_control/state.json").read_text())
    sessions = {}
    for p in glob.glob(str(ROOT / "data/system_ai_state/repair_sessions/*.json")):
        if p.endswith(".apply.json"):
            continue
        try:
            s = json.loads(Path(p).read_text())
        except Exception:
            continue
        if s.get("created_at", "") >= "2026-10-26T20:00":
            sessions[s.get("key")] = {"status": s.get("status"), "scheduled_at": s.get("scheduled_at"),
                                       "applied_at": s.get("applied_at"), "commit": (s.get("commit") or {}).get("commit") if isinstance(s.get("commit"), dict) else s.get("commit"),
                                       "files": [r.get("rel") for r in (s.get("files") or {}).values()]}
    conts = {}
    for p in glob.glob(str(ROOT / "data/system_ai_state/repair_continuations/*.json")):
        r = json.loads(Path(p).read_text())
        if (r.get("updated_at") or r.get("created_at") or "") >= "2026-10-26T20:00" or r.get("status") not in ("completed","blocked","cancelled","continued"):
            conts[r.get("task_id")] = {"status": r.get("status"), "phase": r.get("phase"), "repair_policy": r.get("repair_policy")}
    head = subprocess.run(["git", "log", "-1", "--format=%h %s"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--short", "--", "backend/test_repair_training_subject.py"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    keeper = (ROOT / "data/backend_keeper_off").exists()
    return {"phase": st.get("phase"), "generation": st.get("generation"), "worker": (st.get("worker") or {}).get("pid"),
            "controller": (st.get("controller") or {}).get("pid"), "request": (st.get("request") or {}).get("request_id") if isinstance(st.get("request"), dict) else st.get("request"),
            "last_outcome": (st.get("last_result") or {}).get("outcome"), "red_outcome": st.get("red_outcome"),
            "subject_sha": hashlib.sha256(SUBJECT.read_bytes()).hexdigest()[:16], "subject_mtime": int(SUBJECT.stat().st_mtime),
            "sessions": sessions, "continuations": conts, "head": head, "subject_dirty": dirty, "keeper_off": keeper}
with OUT.open("a") as f:
    while time.time() < deadline:
        try:
            cur = snap()
        except Exception as exc:
            cur = {"error": str(exc)}
        if cur != prev:
            f.write(json.dumps({"t": time.strftime("%H:%M:%S"), **cur}, ensure_ascii=False) + "\n"); f.flush()
            prev = cur
        time.sleep(10)
