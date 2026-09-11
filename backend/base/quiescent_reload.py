"""이전 개발 리로더의 요청 어댑터와 관측 도구.

재기동/강제중단 권한은 restart_controller만 갖는다. /health episode 관측은
진단용이며 미도달·UNKNOWN·상한은 작업 0 또는 재기동 허가가 아니다.
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
    if (not isinstance(data, dict) or "live_turns" not in data
            or data.get("live_turns_observation") == "unknown"):
        return True, None
    ids = data.get("live_turns")
    return True, (list(ids) if isinstance(ids, list) else None)


def wait_for_quiet(health_url: str, probe=None, cap_s: float = None, poll_s: float = None) -> dict:
    """도는 턴이 0 이 될 때까지 → {"outcome": observed|cap|no_body|unknown, "live", "waited_s"}.

    unknown = 몸은 살아 있는데 live_turns 를 모른다. 자동 교체를 보류한다.
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
    """호환 관측 함수. episode 0은 실제 drain 증거가 아니므로 재기동 권한을 주지 않는다."""
    q = wait_for_quiet(health_url, probe=probe, cap_s=cap_s, poll_s=poll_s)
    return dict(q, gate=False, restart_allowed=False)


def submit_restart(base_path, key):
    from restart_protocol import code_manifest, request
    manifest = code_manifest(base_path)
    return request(base_path, "legacy_reloader", request_id=key,
                   artifact_digest=manifest["digest"])


def make_reloader(base_path: str, health_url: str):
    """uvicorn 의 WatchFilesReload 서브클래스를 만든다 — restart() 앞에 의례를 끼운다."""
    from uvicorn.supervisors.watchfilesreload import WatchFilesReload

    class QuiescentReload(WatchFilesReload):
        _base_path = base_path
        _health_url = health_url

        def restart(self) -> None:
            # 이 호환 입구도 요청만 제출한다. 부모 restart()를 부르는 경쟁 소유자는 없다.
            submit_restart(self._base_path, f"reload-{time.time_ns()}")

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
