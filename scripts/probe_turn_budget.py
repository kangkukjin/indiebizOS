#!/usr/bin/env python3
"""턴 예산 회귀 고정물 — 같은 턴 묶음을 라이브 백엔드에 돌려 정답·차선·라운드·시간·비캐시 토큰을 단언한다.

★왜: 속도·토큰 최적화는 모델을 바꿔도 살아남아야 한다(2026-09-02 사용자 원칙). 최적화의 형태가
안전을 주지 않는다 — 같은 턴 묶음이 관문으로 서 있어야 모델 교체 날 먼저 빨갛게 된다.
정본 묶음: data/turn_budget_fixtures.yaml. 읽는 곳: WS end 이벤트(turn_tokens·turn_cache_read),
cognition 이벤트(차선), /episode-summaries(execution_rounds·total_ms). 로그 긁기 없음.
기어는 인자로 고르고 끝나면 반드시 복원한다(측정이 몸 상태를 바꿔선 안 된다).
"""
import argparse, asyncio, json, re, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "backend"))
import boot_paths  # noqa: E402,F401  (backend 층 경로 — 독립 스크립트 규약)
API = "http://localhost:8765"


def _req(method, path, body=None, timeout=15):
    r = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Content-Type": "application/json"}, method=method)
    return json.loads(urllib.request.urlopen(r, timeout=timeout).read())


def _placeholders(s: str) -> str:
    now = datetime.now()
    wd = "월화수목금토일"[now.weekday()]
    return (s.replace("{today_ymd}", now.strftime("%Y-%m-%d"))
             .replace("{today_md}", f"{now.month}월 {now.day}일|{now.month:02d}월 {now.day:02d}일")
             .replace("{weekday}", wd))


async def _run_turn(message: str, timeout_s: float) -> dict:
    import websockets
    out = {"response": "", "lane": None, "turn_tokens": None, "turn_cache_read": None, "end": None}
    t0 = time.time()
    async with websockets.connect(f"ws://localhost:8765/ws/chat/probe_turn_budget", max_size=None,
                                  open_timeout=60) as ws:
        await ws.send(json.dumps({"type": "system_ai_stream", "message": message}))
        while time.time() - t0 < timeout_s + 30:
            ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout_s + 30))
            t = ev.get("type")
            if t == "cognition":
                d = str(ev.get("decision") or "")
                out["lane"] = {"execute": "EXECUTE", "reflex": "EXECUTE", "think": "THINK"}.get(d, d.upper())
            elif t == "response":
                out["response"] = ev.get("content") or out["response"]
            elif t in ("end", "error", "cancelled"):
                out["end"] = t
                out["turn_tokens"] = ev.get("turn_tokens")
                out["turn_cache_read"] = ev.get("turn_cache_read")
                break
    out["wall_s"] = round(time.time() - t0, 1)
    return out


def _episode_for(message: str) -> dict:
    try:
        rows = _req("GET", "/xray/episode-summaries?limit=5").get("summaries") or []
    except Exception:
        try:
            rows = _req("GET", "/episode-summaries?limit=5").get("summaries") or []
        except Exception:
            return {}
    for r in rows:
        if (r.get("user_message") or "").strip() == message.strip():
            return r
    return rows[0] if rows else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gear", default=None, help="측정 기어(절약/균형/최대). 기본=고정물 defaults.gear")
    ap.add_argument("--only", default=None, help="이 이름의 턴만")
    ap.add_argument("--fixtures", default=str(BASE / "data" / "turn_budget_fixtures.yaml"))
    args = ap.parse_args()
    import yaml
    spec = yaml.safe_load(Path(args.fixtures).read_text(encoding="utf-8"))
    defaults = spec.get("defaults") or {}
    gear = args.gear or defaults.get("gear")
    try:
        orig_gear = _req("GET", "/model-gear")["current_gear"]
    except Exception as e:
        print(f"[probe] 백엔드(:8765)에 닿지 않음 — {e}")
        return 2
    if gear and gear != orig_gear:
        _req("PUT", "/model-gear", {"gear": gear})
    print(f"[probe] 기어={gear or orig_gear} (원래 {orig_gear})")
    failures = []
    rows = []
    try:
        for t in spec.get("turns") or []:
            if args.only and t.get("name") != args.only:
                continue
            lim = {k: t.get(k, defaults.get(k)) for k in ("max_total_s", "max_rounds", "max_uncached_tokens")}
            res = asyncio.run(_run_turn(t["message"], float(lim["max_total_s"] or 60)))
            time.sleep(1.0)
            ep = _episode_for(t["message"])
            rounds = ep.get("execution_rounds")
            total_ms = ep.get("total_ms")
            uncached = (None if res["turn_tokens"] is None
                        else int(res["turn_tokens"]) - int(res["turn_cache_read"] or 0))
            probs = []
            if res["end"] != "end":
                probs.append(f"종료={res['end']}")
            for pat in t.get("expect") or []:
                if not re.search(_placeholders(pat), res["response"] or ""):
                    probs.append(f"정답 불일치 /{_placeholders(pat)}/")
            if t.get("expect_lane") and res["lane"] and res["lane"] != t["expect_lane"]:
                probs.append(f"차선 {res['lane']}≠{t['expect_lane']}")
            if lim["max_total_s"] and res["wall_s"] > float(lim["max_total_s"]):
                probs.append(f"시간 {res['wall_s']}s>{lim['max_total_s']}")
            if lim["max_rounds"] and rounds is not None and int(rounds) > int(lim["max_rounds"]):
                probs.append(f"라운드 {rounds}>{lim['max_rounds']}")
            if lim["max_uncached_tokens"] and uncached is not None and uncached > int(lim["max_uncached_tokens"]):
                probs.append(f"비캐시 {uncached}>{lim['max_uncached_tokens']}")
            if res["turn_tokens"] is None:
                probs.append("턴 예산 미수신(end 이벤트에 turn_tokens 없음)")
            rows.append((t["name"], res["wall_s"], rounds, res["turn_tokens"], res["turn_cache_read"], uncached, res["lane"], probs))
            if probs:
                failures.append((t["name"], probs, (res["response"] or "")[:200]))
    finally:
        if gear and gear != orig_gear:
            for _ in range(10):
                try:
                    _req("PUT", "/model-gear", {"gear": orig_gear}); break
                except Exception:
                    time.sleep(3)
            print(f"[probe] 기어 복원 → {orig_gear}")
    print(f"{'턴':8s} {'시간s':>6s} {'라운드':>5s} {'토큰':>8s} {'캐시적중':>8s} {'비캐시':>7s} {'차선':8s} 판정")
    for name, wall, rounds, tok, hit, unc, lane, probs in rows:
        print(f"{name:8s} {wall:6.1f} {str(rounds):>5s} {str(tok):>8s} {str(hit):>8s} {str(unc):>7s} {str(lane):8s} "
              f"{'OK' if not probs else '; '.join(probs)}")
    if failures:
        print("\n[probe] 실패:")
        for name, probs, resp in failures:
            print(f"  - {name}: {'; '.join(probs)}\n    응답: {resp!r}")
        return 1
    print("\n[probe] 전부 통과 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
