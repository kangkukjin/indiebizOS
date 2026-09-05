"""
quiescent_reload.py - 도는 턴이 0 일 때만 재기동하는 리로더 (2026-09-02)

★왜: 수리 경로(red_apply)는 도는 턴 0 을 확인하고 관문을 세운 뒤에야 쓴다 — 그런데
backend/*.py 를 바꾸는 손은 그것만이 아니다. 08-22 이후 리로드 416건 중 210건이 어떤
수리 세션에도 없는 파일이었다: Claude Code 세션의 Edit, `[self:script]`, `run_command`,
git checkout. 그 손들에게 하나씩 협조를 요구하면 손이 하나 늘 때마다 그물이 샌다
([[hand-picked-sweep-leaks]]). 그물은 **리로드 한 자리**에 친다 — 누가 썼든 파일 변경은
결국 이 리로더의 `restart()` 를 지나고, 여기서 도는 턴 0 을 기다린 뒤 관문을 세우고
재기동하면 편집자가 누구든 같은 규율을 받는다.

배선: api.py `__main__` 이 `uvicorn.run(...)` 직전에 `install()` 을 부른다 — uvicorn.main 의
`ChangeReload` 이름을 이 클래스로 바꿔 끼운다. uvicorn.run 호출 자체는 그대로다(가드
test_reload_scope 가 그 호출의 인자를 읽는다 — 기동 지점을 옮기지 않는다). 이음매가
살아 있는지는 test_quiescent_reload Q3 가 설치된 uvicorn 소스로 실측한다.

대기 규율(red_apply.wait_quiescent 와 같은 모양):
  - /health 의 live_turns 가 비면 → 관문(written)을 세우고 재기동. 새 몸이 부팅에서 회수.
  - 도는 턴이 있으면 기다린다(폴링 2초). 그 사이 들어온 새 턴도 정상 처리된다(리로드가
    양보한다). 상한 RELOAD_QUIESCE_CAP_S(600초)에 닿으면 강행하되 잘릴 수 있는 턴을
    로그에 이름으로 남긴다 — 상한은 안전망이지 시간표가 아니다.
  - 몸이 안 닿으면(부팅 중·죽음) 자를 턴이 없다 — 곧바로 재기동.
"""
import json
import os
import time
import urllib.request

QUIESCE_CAP_S = float(os.environ.get("RELOAD_QUIESCE_CAP_S", 600))
POLL_S = float(os.environ.get("RELOAD_QUIESCE_POLL_S", 2))
GATE_SETTLE_S = float(os.environ.get("RELOAD_GATE_SETTLE_S", 0.5))


def _log(msg: str):
    print(f"[reload {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def probe_live_turns(health_url: str, timeout: float = 3.0):
    """(닿았나, live_turns | None). None = 옛 몸(칸이 없다) — 판정 불능은 '없다'가 아니다."""
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as r:
            if r.status != 200:
                return False, None
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return False, None
    if not isinstance(data, dict) or "live_turns" not in data:
        return True, None
    ids = data.get("live_turns")
    return True, (list(ids) if isinstance(ids, list) else None)


def wait_for_quiet(health_url: str, probe=None, cap_s: float = None, poll_s: float = None) -> dict:
    """도는 턴이 0 이 될 때까지 → {"outcome": observed|cap|no_body|unknown, "live", "waited_s"}.

    unknown = 몸은 살아 있는데 live_turns 를 모른다(옛 몸) — 기다릴 근거가 없으니 진행.
    """
    probe = probe or (lambda: probe_live_turns(health_url))
    cap_s = QUIESCE_CAP_S if cap_s is None else cap_s
    poll_s = POLL_S if poll_s is None else poll_s
    t0 = time.time()
    live = []
    while True:
        reached, live = probe()
        if not reached:
            return {"outcome": "no_body", "live": [], "waited_s": int(time.time() - t0)}
        if live is None:
            return {"outcome": "unknown", "live": [], "waited_s": int(time.time() - t0)}
        if not live:
            return {"outcome": "observed", "live": [], "waited_s": int(time.time() - t0)}
        if time.time() - t0 >= cap_s:
            return {"outcome": "cap", "live": list(live), "waited_s": int(time.time() - t0)}
        time.sleep(poll_s)


def ledger_path(base_path: str) -> str:
    return os.path.join(str(base_path), "data", "world_pulse.db")


def close_cut_turns(base_path: str, ids, reason: str) -> int:
    """강행 재기동이 자를 턴을 원장에서 닫는다 — 표식·모양은 episode_logger 가 소유한다."""
    try:
        from episode_logger import close_cut_episodes
        n = close_cut_episodes(ids, reason, db_path=ledger_path(base_path))
        if n:
            _log(f"잘리는 턴 {list(ids)} 원장 닫음({n}건, CUT 표식) — 적용 대기가 이 행을 기다리지 않게")
        return n
    except Exception as e:
        _log(f"잘리는 턴 닫기 실패(계속): {e!r}")
        return 0


def prepare_restart(base_path: str, health_url: str, key: str, probe=None,
                    cap_s: float = None, poll_s: float = None, settle_s: float = None) -> dict:
    """재기동 직전 의례 — 도는 턴 0 대기 → 관문(written) → 되묻기(직후 진입 턴엔 양보).

    반환 = wait_for_quiet 결과 + "gate": bool. 관문은 새 몸이 부팅에서 회수한다
    (EpisodeLogger.install → reload_gate.clear_at_boot). 이 프로세스가 죽어도 TTL 이 닫는다.
    """
    import reload_gate
    settle_s = GATE_SETTLE_S if settle_s is None else settle_s
    probe = probe or (lambda: probe_live_turns(health_url))
    t0 = time.time()
    while True:
        q = wait_for_quiet(health_url, probe=probe, cap_s=cap_s, poll_s=poll_s)
        if q["outcome"] != "observed":
            break
        # 0 을 봤다 — 관문을 세우고, 관문이 보이기 전에 들어온 턴이 없는지 한 번 더 묻는다.
        reload_gate.raise_gate(base_path, key, phase="written")
        if settle_s:
            time.sleep(settle_s)
        reached, again = probe()
        if not reached or not again:
            break
        reload_gate.lower_gate(base_path, key)       # 그 턴을 살린다 — 리로드가 양보한다
        _log(f"관문 직후 턴 진입 {again} — 관문 내리고 다시 기다림")
        remaining = (QUIESCE_CAP_S if cap_s is None else cap_s) - (time.time() - t0)
        if remaining <= 0:
            q = {"outcome": "cap", "live": list(again), "waited_s": int(time.time() - t0)}
            break
        cap_s = remaining
    if q["outcome"] in ("cap", "unknown"):
        reload_gate.raise_gate(base_path, key, phase="written")   # 강행이어도 새 턴은 되돌린다
    if q["outcome"] == "cap":
        # 자르는 쪽이 닫는다(2026-09-06 ep2891): 이 재기동에 잘릴 턴은 END 를 못 쓰고, 부팅 회수는
        # 궤적이 신선해 건너뛴다 — 그러면 red_apply 가 그 행이 닫히길 상한(900초)까지 기다린다.
        q["cut"] = close_cut_turns(base_path, q["live"], f"reload {key}")
    q["gate"] = q["outcome"] != "no_body"
    q["waited_s"] = int(time.time() - t0)
    return q


def make_reloader(base_path: str, health_url: str):
    """uvicorn 의 WatchFilesReload 서브클래스를 만든다 — restart() 앞에 의례를 끼운다."""
    from uvicorn.supervisors.watchfilesreload import WatchFilesReload

    class QuiescentReload(WatchFilesReload):
        _base_path = base_path
        _health_url = health_url

        def restart(self) -> None:
            key = f"reload-{int(time.time())}"
            try:
                q = prepare_restart(self._base_path, self._health_url, key)
            except Exception as e:     # 의례 실패가 리로드를 막아선 안 된다 — 종전 동작으로
                _log(f"정적 대기 실패(계속, 종전대로 재기동): {e!r}")
                q = {"outcome": "error", "live": [], "waited_s": 0}
            if q["outcome"] == "cap":
                _log(f"★정적 대기 상한({QUIESCE_CAP_S:.0f}초) — 도는 턴 {q['live']} 이 남은 채 "
                     f"강행. 그 턴은 이 재기동에 잘릴 수 있다(주행기록 고아 확인).")
            elif q["outcome"] == "observed":
                _log(f"도는 턴 0 확인({q['waited_s']}초 대기) — 재기동 관문 세움, 재기동")
            elif q["outcome"] == "no_body":
                _log("몸이 안 닿음 — 자를 턴 없음, 재기동")
            super().restart()

    return QuiescentReload


def install(base_path, health_url: str = None) -> bool:
    """uvicorn.main 의 ChangeReload 를 갈아 끼운다. 이음매가 없으면 False(종전 리로더)."""
    try:
        # ★`import uvicorn.main as um` 은 모듈이 아니라 click Command `main` 을 준다
        #   (uvicorn/__init__ 이 같은 이름을 덮는다) — 모듈 객체는 sys.modules 로 받는다.
        import importlib
        um = importlib.import_module("uvicorn.main")
        if not hasattr(um, "ChangeReload"):
            _log("uvicorn.main.ChangeReload 이음매가 없다 — 종전 리로더로 기동")
            return False
        port = os.environ.get("INDIEBIZ_API_PORT", "8765")
        url = health_url or f"http://127.0.0.1:{port}/health"
        um.ChangeReload = make_reloader(str(base_path), url)
        return True
    except Exception as e:
        _log(f"리로더 설치 실패(종전 리로더로 기동): {e!r}")
        return False
