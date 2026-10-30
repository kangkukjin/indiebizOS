"""제어 기반과 워커 파일 감시의 소유권: 인계 전 배포 금지·전용 변경 무교체·공유 변경 적용."""
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
import control_base
from restart_candidates import Watcher
from test_restart_generations import setup  # noqa: F401
from test_restart_controller import ticks


@pytest.fixture
def managed(setup, monkeypatch):
    ctl, adapter, clock = setup
    for rel in ("backend/services/restart_controller.py", "backend/services/restart_candidates.py",
                "backend/services/restart_helper.py", "backend/base/restart_protocol.py"):
        path = ctl.base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("VALUE = 1\n")
    ctl.control_base_id = control_base.snapshot(ctl.base, ctl.base)["id"]
    candidate = ctl.prepare_candidate("fixture")
    ctl.save(code_digest=candidate["generation"], generation_dir=candidate["generation_dir"],
             source_digest=candidate["source_digest"])
    # The tests advance the accepted control base explicitly, including a delayed/failed handover.
    monkeypatch.setattr(ctl, "_control_watch", lambda: None)
    return ctl, adapter, clock


def scan(ctl, clock):
    watcher = Watcher(ctl)
    for _ in range(3):
        clock[0] += 3
        watcher.tick()


@pytest.mark.parametrize("name", ["restart_controller", "restart_candidates", "restart_helper"])
def test_control_only_changes_do_not_replace_worker_before_or_after_handover(managed, name):
    ctl, adapter, clock = managed
    before = ctl.state["generation_dir"]
    (ctl.base / f"backend/services/{name}.py").write_text("VALUE = 2\n")
    scan(ctl, clock)
    assert not ctl.pending()
    ctl.control_base_id = control_base.snapshot(ctl.base, ctl.base)["id"]
    scan(ctl, clock)
    ticks(ctl, 12)
    assert not ctl.pending() and adapter.spawns == adapter.stops == 0
    assert ctl.state["generation_dir"] == before


@pytest.mark.parametrize("change", ["shared", "mixed"])
def test_worker_changes_wait_for_control_acceptance_then_still_deploy(managed, change):
    ctl, adapter, clock = managed
    rel = "backend/base/restart_protocol.py" if change == "shared" else "backend/app.py"
    (ctl.base / rel).write_text("VALUE = 2\n")
    if change == "mixed":
        (ctl.base / "backend/services/restart_controller.py").write_text("VALUE = 2\n")
    prepared = control_base.snapshot(ctl.base, ctl.base)["id"]
    control_base.write_current(ctl.base, {"current": prepared})
    # Even an approved snapshot is insufficient until the running owner accepts it.
    scan(ctl, clock)
    assert not ctl.pending() and adapter.spawns == 0
    ctl.control_base_id = prepared
    scan(ctl, clock)
    assert ctl.pending()
    ticks(ctl, 12)
    assert ctl.state["phase"] == "ACTIVE" and adapter.spawns == 1
    assert (Path(ctl.state["generation_dir"]) / rel).read_text() == "VALUE = 2\n"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


def test_verified_component_publication_does_not_restart_worker(managed):
    import json
    import component_registry as components
    ctl, adapter, clock = managed
    rel = 'data/packages/installed/tools/fixture/fixture_transform.py'
    path = ctl.base / rel
    path.parent.mkdir(parents=True)
    path.write_text('def transform(x): return x\n')
    spec = {'id': 'fixture.transform', 'source': rel, 'text_fields': [], 'fixtures': [], 'protocol': 'pure-json/1'}
    path.with_name('runtime_components.json').write_text(json.dumps([spec]))
    candidate = ctl.prepare_candidate('component-fixture')
    ctl.save(code_digest=candidate['generation'], generation_dir=candidate['generation_dir'],
             source_digest=candidate['source_digest'])
    spec = components.registry(candidate['generation_dir'])['fixture.transform']
    replacement = b'def transform(x): return list(x)\n'
    version = components.store_object(ctl.base, replacement)
    components.publish(ctl.base, spec, version, receipt={'session': 'verified-fixture'})
    path.write_bytes(replacement)
    scan(ctl, clock)
    assert not ctl.pending() and adapter.spawns == adapter.stops == 0
    assert ctl.state['generation_dir'] == candidate['generation_dir']
    # 게시 영수증과 다른 바이트를 조용히 활성화된 것으로 취급하지 않는다.
    path.write_text('def transform(x): return [x]\n')
    scan(ctl, clock)
    assert ctl.pending()
