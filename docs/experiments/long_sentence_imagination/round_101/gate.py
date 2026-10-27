"""100회차 운영 관문 — 백엔드가 ACTIVE·healthy 가 될 때까지 기다리고 현재 세대 digest 를 돌려준다(타 세션 편집으로 개발 세대 교체가 연쇄 중)."""
import json, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
def state():
    d = json.loads((ROOT / "data/restart_control/state.json").read_text()); lr = d.get("last_result") or {}
    return {"phase": d.get("phase"), "generation": d.get("generation"), "code_digest": d.get("code_digest"), "outcome": lr.get("outcome"), "request_id": (d.get("request") or {}).get("payload", {}).get("generation_dir", "")[-32:] if d.get("request") else None}
def healthy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3) as r: return json.load(r).get("status") == "healthy"
    except Exception: return False
def wait(max_s=240):
    t0 = time.time()
    while time.time() - t0 < max_s:
        s = state()
        if s["phase"] == "ACTIVE" and healthy(): return {"waited_s": round(time.time() - t0, 1), **s, "at": time.strftime("%H:%M:%S")}
        time.sleep(2)
    return {"waited_s": round(time.time() - t0, 1), "timeout": True, **state(), "at": time.strftime("%H:%M:%S")}
if __name__ == "__main__":
    print(json.dumps(wait(int(sys.argv[1]) if len(sys.argv) > 1 else 240), ensure_ascii=False))
