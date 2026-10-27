"""세대 기반 재기동의 실제 프로세스 시험(G1·G2·G6). 임시 git 저장소·격리 데이터·loopback·실제 자식 프로세스.

- 커밋 없이 저장한 변경이 정착 뒤 봉인 세대로 자동 교체되고, 현역 세대의 바이트는 저장으로 바뀌지 않는다.
- 새 세대의 부팅 실패는 직전 세대 복구로 끝나고 실패한 원천은 변경 전까지 재시도하지 않는다.
- 제어 기반(제어자 코드) 변경은 새 기반을 봉인·검증한 뒤 소유권을 인계한다. 인계 실패는 이전 기반이 계속 소유한다.
외부 송신 없음. 실행: .venv/bin/python3 -m pytest backend/test_restart_generation_process.py -q
"""
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
import boot_paths  # noqa: F401
import control_base
import generation_store as gens
from restart_process import alive, signal_owned
from restart_protocol import atomic_json, control_dir, read_json, request
from test_restart_process import SERVER, http

pytestmark = pytest.mark.system

ROOT = Path(__file__).resolve().parents[1]
RUNNER = '''
import os, sys
sys.path.insert(0, sys.argv[2])
import boot_paths
import control_base
from restart_controller import Controller
ctl = Controller(sys.argv[1], sys.argv[1])
if len(sys.argv) > 3 and sys.argv[3]:
    ctl.control_base_id = sys.argv[3]
raise SystemExit(ctl.run(start=True))
'''


def eventually(fn, timeout=30):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = fn()
            if last:
                return last
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise AssertionError(f"condition timed out: {last}")


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def runtime(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    repo = tmp_path / "repo"
    backend = repo / "backend"
    (backend / "base").mkdir(parents=True)
    shutil.copy(ROOT / "backend/base/restart_child.py", backend / "base/restart_child.py")
    # 스텁 boot_paths: 정본 저장소의 층을 바라본다(가짜 저장소에는 서버 부품이 없다).
    backend.joinpath("boot_paths.py").write_text(
        "import sys\n" + "\n".join(f"sys.path.insert(0, {str(ROOT / 'backend' / d)!r})"
                                  for d in ("", "base", "datastore", "services", "surface")))
    # 부팅 실패 주입은 세대 안의 파일로 — 저장이 다음 세대를 만드는 것과 같은 길.
    backend.joinpath("api.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "if (Path(__file__).with_name('boot_flag.py')).read_text().strip() == 'fail':\n"
        "    raise RuntimeError('injected boot failure')\n" + SERVER.replace(
            'if os.environ.get("FAIL_BOOT"):\n    raise RuntimeError("injected boot failure")\n', ""))
    backend.joinpath("boot_flag.py").write_text("ok\n")
    backend.joinpath("feature.py").write_text("VALUE = 1\n")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.test")
    git(repo, "config", "user.name", "T")
    (repo / ".gitignore").write_text("data/\n__pycache__/\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "fixture")
    runner = tmp_path / "runner.py"
    runner.write_text(RUNNER)
    processes = []
    env = dict(os.environ, INDIEBIZ_API_PORT=str(port))
    env.pop("INDIEBIZ_PRODUCTION", None)
    log = (tmp_path / "controller.log").open("ab")

    def launch(control_id="", **extra):
        proc = subprocess.Popen([sys.executable, str(runner), str(repo), str(ROOT / "backend"), control_id],
                                env=dict(env, **extra), stdout=log, stderr=log)
        processes.append(proc)
        return proc

    def state():
        return read_json(control_dir(repo) / "state.json", {})

    # Shared control/worker modules belong to the initial generation, not a live setup edit.
    _control_fixture(repo)
    launch()
    eventually(lambda: state().get("phase") == "ACTIVE", timeout=40)
    yield repo, port, launch, state
    atomic_json(repo / "data/.intentional_shutdown", {})
    try:
        if any(p.poll() is None for p in processes):
            eventually(lambda: state().get("phase") == "STOPPED", timeout=30)
    finally:
        for worker in (control_dir(repo) / "workers").glob("*.json"):
            ident = read_json(worker)
            if ident:
                signal_owned(ident, force=True)
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        log.close()


def test_saved_edit_swaps_generation_and_active_bytes_are_frozen(runtime):
    repo, port, launch, state = runtime
    first = state()
    assert first["generation_dir"] and gens.sealed(first["generation_dir"])
    assert http(port, "/health")["status"] == "healthy"
    # 현역 세대의 바이트는 봉인 때 그대로이고 정본 편집이 그것을 바꾸지 않는다(G1).
    (repo / "backend/feature.py").write_text("VALUE = 2\n")
    assert (Path(first["generation_dir"]) / "backend/feature.py").read_text() == "VALUE = 1\n"
    eventually(lambda: state().get("phase") == "ACTIVE" and state()["generation_dir"] != first["generation_dir"], timeout=40)
    second = state()
    assert (Path(second["generation_dir"]) / "backend/feature.py").read_text() == "VALUE = 2\n"
    assert second["previous"]["generation_dir"] == first["generation_dir"]
    assert second["last_result"]["outcome"] == "restarted" and second["source_digest"] == gens.execution_inventory(repo)["digest"]
    gens.verify(first["generation_dir"])
    assert not alive(first["worker"]) and alive(second["worker"])
    # 커밋은 필요 없었다 — 정본은 dirty 그대로.
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    assert "backend/feature.py" in status


def test_bad_boot_rolls_back_to_previous_generation_and_marks_source(runtime):
    repo, port, launch, state = runtime
    first = state()
    (repo / "backend/boot_flag.py").write_text("fail\n")
    eventually(lambda: (state().get("last_result") or {}).get("outcome") == "rolled_back", timeout=90)
    after = state()
    assert after["phase"] == "ACTIVE" and after["generation_dir"] == first["generation_dir"]
    assert alive(after["worker"]) and after["worker"] != first["worker"]
    assert gens.execution_inventory(repo)["digest"] in after["failed_sources"]
    assert http(port, "/health")["status"] == "healthy"
    # 고장난 정본은 다시 후보가 되지 않는다. 고치면 다음 세대가 된다.
    time.sleep(5)
    assert state()["generation_dir"] == first["generation_dir"]
    (repo / "backend/boot_flag.py").write_text("ok\n")
    (repo / "backend/feature.py").write_text("VALUE = 3\n")
    eventually(lambda: state().get("phase") == "ACTIVE" and state()["generation_dir"] != first["generation_dir"]
               and (state().get("last_result") or {}).get("outcome") == "restarted", timeout=60)
    assert (Path(state()["generation_dir"]) / "backend/feature.py").read_text() == "VALUE = 3\n"


def test_syntax_error_in_source_keeps_active_generation(runtime):
    repo, port, launch, state = runtime
    first = state()
    (repo / "backend/feature.py").write_text("VALUE = (\n")
    eventually(lambda: state().get("failed_sources"), timeout=30)
    failed = next(iter(state()["failed_sources"].values()))
    assert failed["outcome"] == "check_failed" and "SyntaxError" in failed["note"]
    assert state()["generation_dir"] == first["generation_dir"] and alive(first["worker"])
    assert http(port, "/health")["status"] == "healthy"


def _control_fixture(repo):
    """가짜 저장소에 정본의 제어 파일을 심어 기반(control_base)을 만들 수 있게 한다(스텁 boot_paths 유지)."""
    for src, dst in control_base._entries():
        if src == "backend/boot_paths.py":
            continue
        target = repo / src
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / src, target)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "control files")


def test_control_base_handover_keeps_worker_and_survives_failed_takeover(runtime):
    repo, port, launch, state = runtime
    base_id, note = control_base.ensure(repo, repo, support_root=repo)
    assert base_id, note
    # 기반 id 를 아는 제어자로 바꿔 띄운다(이전 제어자는 종료).
    first = state()
    signal_owned(first["controller"], force=True)
    eventually(lambda: not alive(first["controller"]))
    launch(base_id)
    eventually(lambda: state().get("controller") and state()["controller"] != first["controller"]
               and state().get("phase") == "ACTIVE", timeout=40)
    before = state()
    worker = before["worker"]
    # 1) 인계 실패: 새 기반의 인수가 거절되면 이전 제어자가 계속 소유하고 기반은 실패로 기록된다.
    (repo / "backend/services/restart_controller.py").write_text(
        (repo / "backend/services/restart_controller.py").read_text() + "\n# control change 1\n")
    failing = control_base.inventory(repo)["digest"]
    os.environ["INDIEBIZ_CONTROL_TAKEOVER_FAULT"] = "1"  # 자식 제어자가 상속한다(이 제어자의 환경은 테스트 프로세스 환경)
    try:
        # 제어자 프로세스는 이미 떠 있어 환경을 상속하지 않는다 — 결함 주입은 새 제어자 스폰 시점의 old 제어자 환경이다.
        # 그래서 old 제어자를 결함 환경으로 다시 띄운다.
        signal_owned(before["controller"], force=True)
        eventually(lambda: not alive(before["controller"]))
        launch(base_id, INDIEBIZ_CONTROL_TAKEOVER_FAULT="1")
        eventually(lambda: (state().get("control_update") or {}).get("status") == "takeover_failed", timeout=90)
    finally:
        os.environ.pop("INDIEBIZ_CONTROL_TAKEOVER_FAULT", None)
    failed_state = state()
    assert failed_state["control_base"] == base_id and alive(failed_state["worker"]) and failed_state["worker"] == worker
    assert failing in control_base.read_current(repo)["failed"]
    assert http(port, "/health")["status"] == "healthy"
    # 2) 정상 인계: 또 한 번 바꾸면 새 기반이 봉인·검증·인수되고 워커는 그대로다.
    old_controller = failed_state["controller"]
    signal_owned(old_controller, force=True)
    eventually(lambda: not alive(old_controller))
    launch(base_id)
    eventually(lambda: state().get("controller") and state()["controller"] != old_controller and state().get("phase") == "ACTIVE", timeout=40)
    (repo / "backend/services/restart_controller.py").write_text(
        (repo / "backend/services/restart_controller.py").read_text() + "\n# control change 2\n")
    new_id = control_base.inventory(repo)["digest"]
    eventually(lambda: state().get("control_base") == new_id and not state().get("control_handover"), timeout=120)
    handed = state()
    assert handed["worker"] == worker and alive(worker) and handed["phase"] == "ACTIVE"
    assert alive(handed["controller"]) and handed["controller"]["pid"] != old_controller["pid"]
    assert control_base.read_current(repo)["current"] == new_id
    assert (control_dir(repo) / f"state.pre-{new_id}.json").exists()
    assert http(port, "/health")["status"] == "healthy"
    # Wait beyond a full source quiet period: control-only edits must not trigger a later worker swap.
    time.sleep(5)
    assert state()["worker"] == worker and alive(worker) and state()["phase"] == "ACTIVE"
    # 새 제어자가 교체도 소유한다.
    (repo / "backend/feature.py").write_text("VALUE = 9\n")
    eventually(lambda: (Path(state()["generation_dir"]) / "backend/feature.py").read_text() == "VALUE = 9\n", timeout=60)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
