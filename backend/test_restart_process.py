"""R1 실제 프로세스 장애 시험. 임시 코드/데이터, loopback, 로컬 효과 파일만 사용한다."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from restart_process import ProcessAdapter, alive, identity, signal_owned, tree
from restart_protocol import atomic_json, code_manifest, control_dir, read_json, request

ROOT = Path(__file__).resolve().parents[1]
SERVER = '''
import asyncio, os, time
from pathlib import Path
from fastapi import FastAPI
if os.environ.get("FAIL_BOOT"):
    raise RuntimeError("injected boot failure")
import runtime_work
runtime_work.install(os.environ["INDIEBIZ_RUNTIME_GENERATION"])
runtime_work.install_worker_tracking()
import boot_status
for phase in ("boot", "IBL", "lifespan"):
    boot_status.record(phase, True)
from api_runtime import router, RuntimeAdmission
app = FastAPI()
app.include_router(router)
app.add_middleware(RuntimeAdmission)
@app.post("/work")
async def run(seconds: float = 0.1):
    await asyncio.to_thread(time.sleep, seconds)
    with open(Path(os.environ["INDIEBIZ_BASE_PATH"]) / "effects", "a") as out:
        out.write("done\\n")
    return {"finished": True}
@app.post("/process")
async def tool_process():
    import subprocess, sys
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    return {"pid": child.pid}
@app.get("/health")
async def health(): return {"status": "healthy", "live_turns": []}
@app.post("/resident")
def resident():
    import subprocess, sys
    with runtime_work.service_scope(own_processes=True):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    return {"pid": child.pid}
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=int(os.environ["INDIEBIZ_API_PORT"]),
            log_level="error", proxy_headers=False)
'''
RUNNER = '''
import os, sys
sys.path.insert(0, sys.argv[2])
import boot_paths
from restart_controller import Controller
ctl = Controller(sys.argv[1], sys.argv[1])
def fault(edge, phase):
    if ((ctl.home / "requests/fault.json").exists() and edge == os.environ.get("FAULT_EDGE")
            and phase == os.environ.get("FAULT_PHASE")):
        os._exit(77)
ctl.fault = fault
raise SystemExit(ctl.run(start=True))
'''


def eventually(fn, timeout=15):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = fn()
            if last:
                return last
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.05)
    raise AssertionError(f"condition timed out: {last}")


@pytest.fixture
def runtime(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    backend = tmp_path / "backend"
    (backend / "base").mkdir(parents=True)
    shutil.copy(ROOT / "backend/base/restart_child.py", backend / "base/restart_child.py")
    backend.joinpath("boot_paths.py").write_text(
        "import sys\n" + "\n".join(f"sys.path.insert(0, {str(ROOT / 'backend' / d)!r})"
                                  for d in ("", "base", "datastore", "services", "surface")))
    backend.joinpath("api.py").write_text(SERVER)
    runner = tmp_path / "runner.py"
    runner.write_text(RUNNER)
    processes = []
    env = dict(os.environ, INDIEBIZ_API_PORT=str(port), INDIEBIZ_PRODUCTION="1")
    log = (tmp_path / "controller.log").open("ab")
    def launch(**fault):
        proc = subprocess.Popen([sys.executable, str(runner), str(tmp_path), str(ROOT / "backend")],
                                env=dict(env, **fault), stdout=log, stderr=log)
        processes.append(proc)
        return proc
    def state():
        return read_json(control_dir(tmp_path) / "state.json", {})
    launch()
    eventually(lambda: state().get("phase") == "ACTIVE")
    yield tmp_path, port, launch, state
    atomic_json(tmp_path / "data/.intentional_shutdown", {})
    try:
        if any(p.poll() is None for p in processes):
            eventually(lambda: state().get("phase") == "STOPPED")
    finally:
        s = state()
        for worker in (control_dir(tmp_path) / "workers").glob("*.json"):
            ident = read_json(worker)
            if ident:
                signal_owned(ident, force=True)
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        log.close()


def http(port, path, *, token=None, parent=None, payload=None, timeout=3, extra=None):
    headers = dict(extra or {})
    if token:
        headers["X-Runtime-Control"] = token
    if parent:
        headers["X-Runtime-Parent"] = parent
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=None if payload is None else json.dumps(payload).encode(),
                                 headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as response:
        return json.load(response)


def test_idle_anyio_and_resident_process_allow_restart_and_are_reaped(runtime):
    base, port, _, state = runtime
    initial = state()
    child = identity(http(port, "/resident", payload={})["pid"])
    snap = ProcessAdapter(base, base, port).status(initial)
    assert snap["active_roots"] == snap["active_children"] == snap["pending_finalizers"] == 0
    assert alive(child)
    request(base, "idle-resident-test", request_id="resident", policy={"drain_timeout_s": 2, "force": False})
    eventually(lambda: state().get("phase") == "ACTIVE" and state()["generation"] != initial["generation"])
    assert not alive(child)
    assert read_json(control_dir(base) / "results/resident.json")["outcome"] == "restarted"


@pytest.mark.parametrize("clock_shift", [-2, 2])
def test_clock_correction_preserves_worker_and_child_ownership(runtime, monkeypatch, clock_shift):
    """실제 시계는 건드리지 않고 장수 제어자가 보는 NTP 보정만 주입한다."""
    _psosx = pytest.importorskip("psutil._psosx")
    if not hasattr(_psosx, "INIT_BOOT_TIME"):
        pytest.skip("시계 보정 전 psutil 버전")

    base, port, _, state = runtime
    before = state()
    child = identity(http(port, "/process", payload={})["pid"])
    monkeypatch.setattr(_psosx, "INIT_BOOT_TIME", _psosx.boot_time() + clock_shift)

    assert identity(before["worker"]["pid"])["born"] == before["worker"]["born"]
    assert alive(before["worker"])
    members = tree(before["worker"])
    assert child in members and before["worker"] in members
    adapter = ProcessAdapter(base, base, port)
    adapter.stop({"stop_tree": [dict(child, born=child["born"] - 1)]}, force=True)
    assert alive(child), "PID가 재사용된 영수증은 여전히 거절해야 한다"
    adapter.stop({"stop_tree": [child]}, force=True)
    eventually(lambda: adapter.stopped({"stop_tree": [child]}))
    assert alive(before["worker"])


def test_real_timeout_drain_and_identical_request_after_controller_restart(runtime):
    base, port, launch, state = runtime
    initial = state()
    with pytest.raises(TimeoutError):
        http(port, "/work?seconds=1", payload={}, timeout=0.05)
    req = request(base, "test-timeout", request_id="one")
    # 표면 연결이 끊겨도 실제 작업은 남는다. 작업 종료 뒤에만 옛 워커를 멈춘다.
    adapter = ProcessAdapter(base, base, port)
    snap = adapter.status(initial)
    assert snap["active_roots"] + snap["active_children"] > 0
    eventually(lambda: state().get("phase") == "ACTIVE" and state().get("generation") != initial["generation"])
    assert (base / "effects").read_text().splitlines() == ["done"]
    generation = state()["generation"]
    ctl_identity = state()["controller"]
    signal_owned(ctl_identity, force=True)
    eventually(lambda: not alive(ctl_identity))
    launch()
    request(base, "test-timeout", request_id="one")
    time.sleep(0.8)
    assert state()["generation"] == generation
    assert (base / "effects").read_text().splitlines() == ["done"]


def test_real_worker_crash_reaps_orphan_tool_without_replay(runtime):
    base, port, _, state = runtime
    initial = state()
    result = http(port, "/process", payload={})
    child = identity(result["pid"])
    adapter = ProcessAdapter(base, base, port)
    eventually(lambda: adapter.status(initial).get("active_children", 0) > 0)
    signal_owned(initial["worker"], force=True)
    eventually(lambda: state().get("phase") == "ACTIVE" and state().get("generation") != initial["generation"])
    assert not alive(child)
    assert state()["last_result"]["effect_unknown"]
    assert not list((control_dir(base) / "requests").glob("*.json"))
    assert not (base / "effects").exists()


def test_real_auth_and_pid_reuse(runtime):
    base, port, launch, state = runtime
    s = state()
    for headers in ({}, {"X-Runtime-Control": s["control_token"], "X-Forwarded-For": "127.0.0.1"},
                    {"X-Runtime-Control": s["control_token"], "Forwarded": "for=127.0.0.1"}):
        with pytest.raises(urllib.error.HTTPError) as error:
            http(port, "/runtime/status", extra=headers)
        assert error.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as error:
        http(port, "/runtime/drain", token=s["control_token"], payload={"generation": "old"})
    assert error.value.code == 409
    wrong_identity = dict(s["worker"], born=s["worker"]["born"] - 1)
    signal_owned(wrong_identity, force=True)
    assert alive(s["worker"])


@pytest.mark.parametrize("edge", ["before", "after"])
@pytest.mark.parametrize("phase", ["CHECKING", "DRAINING", "STOPPING", "STARTING", "ACTIVE", "RECOVERING", "FAILED", "STOPPED"])
def test_real_controller_death_at_transition(runtime, edge, phase):
    base, port, launch, state = runtime
    first = state()
    ident = first["controller"]
    signal_owned(ident, force=True)
    eventually(lambda: not alive(ident))
    injected = launch(FAULT_EDGE=edge, FAULT_PHASE=phase,
                      FAIL_BOOT="1" if phase in {"RECOVERING", "FAILED"} else "")
    request(base, "fault-test", request_id="fault")
    if phase == "STOPPED":
        atomic_json(base / "data/.intentional_shutdown", {})
    eventually(lambda: injected.poll() is not None)
    assert injected.returncode == 77
    if phase in {"FAILED", "STOPPED"} and edge == "after":
        # 완료된 FAILED/STOPPED는 start가 아닌 serve로 읽어야 명시 재시도가 섞이지 않는다.
        return
    launch()
    if phase == "STOPPED":
        eventually(lambda: state().get("phase") == "STOPPED")
        return
    if phase in {"RECOVERING", "FAILED"}:
        eventually(lambda: state().get("phase") == "FAILED")
        return
    eventually(lambda: state().get("phase") == "ACTIVE" and state().get("generation") != first["generation"])
    current = state()["generation"]
    request(base, "fault-test", request_id="fault")
    time.sleep(0.6)
    assert state()["generation"] == current
    assert sum(alive(read_json(p)) for p in (control_dir(base) / "workers").glob("*.json")) == 1


def test_real_bad_boot_rolls_back_only_known_bytes(runtime):
    import hashlib
    base, port, launch, state = runtime
    initial = state()
    api = base / "backend/api.py"
    before = api.read_bytes()
    backup_dir = base / "data/system_ai_state/red_backups/fixture"
    backup_dir.mkdir(parents=True)
    backup = backup_dir / "api-before.py"
    backup.write_bytes(before)
    after = before.replace(b"import uvicorn", b"raise RuntimeError('injected bad config')\nimport uvicorn")
    api.write_bytes(after)
    manifest = backup_dir / "manifest.json"
    atomic_json(manifest, {"repo": str(base), "owner": "fixture", "files": {str(api): str(backup)},
                           "target_hashes": {str(api): hashlib.sha256(after).hexdigest()}})
    request(base, "bad-boot", operation="red_verify", request_id="rollback",
            artifact_digest=code_manifest(base)["digest"], payload={"manifest_path": str(manifest)})
    eventually(lambda: state().get("phase") == "ACTIVE" and state().get("generation") != initial["generation"], timeout=25)
    assert api.read_bytes() == before
    assert state()["last_result"]["outcome"] == "rolled_back"
    verdict = read_json(manifest.with_name("result.json"))
    assert verdict["outcome"] == "rolled_back" and verdict["recovered"] is True
    assert sum(alive(read_json(p)) for p in (control_dir(base) / "workers").glob("*.json")) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
