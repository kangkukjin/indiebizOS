"""변형 B(Chrome): status → 바깥에서 탭 하나 추가(AppleScript) → 옛 판본으로 close → STATE_CHANGED 기대. 추가한 탭은 같은 스크립트로 닫는다."""
import json, subprocess, sys, uuid, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-20_87회차/probes"
def ibl(label, code, inputs):
    body = {"code": code, "inputs": inputs, "edition": 2, "origin": "training", "project_id": "study", "ticket": uuid.uuid4().hex}
    req = urllib.request.Request("http://127.0.0.1:8765/ibl/execute", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r: res = json.load(r)
    (OUT / f"{label}.json").write_text(json.dumps({"request": body, "response": res, "seconds": time.time() - t0}, ensure_ascii=False, indent=1))
    return res
st = ibl("chrome_b_status", '#!ibl edition=2\nreturn [self:script]{id:"Chrome제어",args:{op:"status"},timeout:60}', {})
w = st["value"]["windows"][0]
wid, rev, cur, n = w["window_id"], w["revision"], w["current_tab"], w["tab_count"]
print("before", wid, rev[:12], "current", cur, "tabs", n)
# 바깥 교란: 같은 창 끝에 about:blank 탭 추가 후 현재 탭 복원
osa = f'tell application "Google Chrome"\n set w to first window whose id is {wid}\n set t to make new tab at end of tabs of w with properties {{URL:"about:blank"}}\n set active tab index of w to {cur}\n return id of t\nend tell'
new_tab_id = subprocess.run(["osascript", "-e", osa], capture_output=True, text=True, timeout=30).stdout.strip()
print("external tab added", new_tab_id)
code = Path(ROOT / "docs/experiments/long_sentence_imagination/round_87/probe_chrome_b.ibl").read_text()
res = ibl("chrome_b_close_stale", code, {"window_id": wid, "tab": n, "expected": rev})
print("close with stale revision ->", json.dumps(res.get("value"), ensure_ascii=False)[:700])
# 정리: 추가한 탭을 같은 통로로 닫는다
osa2 = f'tell application "Google Chrome"\n set w to first window whose id is {wid}\n close (first tab of w whose id is "{new_tab_id}")\nend tell'
print("cleanup", subprocess.run(["osascript", "-e", osa2], capture_output=True, text=True, timeout=30).returncode)
st2 = ibl("chrome_b_status_after", '#!ibl edition=2\nreturn [self:script]{id:"Chrome제어",args:{op:"status"},timeout:60}', {})
w2 = st2["value"]["windows"][0]
print("after", w2["revision"][:12], "same_as_before", w2["revision"] == rev, "tabs", w2["tab_count"])
