"""R1 이전 리로더 호환 입구: 관측은 진단, 재기동 권한은 외부 제어자만 소유."""
import ast
import importlib
from pathlib import Path

import pytest
import quiescent_reload as qr
import reload_gate as gate
from restart_protocol import atomic_json, code_manifest, control_dir, read_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("probe,outcome", [
    (lambda: (True, []), "observed"),
    (lambda: (True, [5]), "cap"),
    (lambda: (True, None), "unknown"),
    (lambda: (False, None), "no_body"),
])
def test_Q1_observation_does_not_authorize_restart(tmp_path, probe, outcome):
    result = qr.prepare_restart(tmp_path, "http://unused", "request", probe=probe,
                                cap_s=0, poll_s=0, settle_s=0)
    assert result["outcome"] == outcome
    assert not result["gate"] and not result["restart_allowed"]
    assert gate.read_gate(tmp_path) is None
    assert "cut" not in result


def test_Q2_waits_until_observed():
    observations = iter([(True, [7]), (True, [7]), (True, [])])
    result = qr.wait_for_quiet("http://unused", probe=lambda: next(observations), cap_s=1, poll_s=0)
    assert result["outcome"] == "observed"


def test_Q3_legacy_reloader_only_submits_request(tmp_path, monkeypatch):
    from uvicorn.supervisors.watchfilesreload import WatchFilesReload
    manifest = code_manifest(tmp_path)
    atomic_json(control_dir(tmp_path) / "state.json", {"generation": "g", "code_digest": manifest["digest"]})
    def forbidden(self):
        pytest.fail("legacy reloader must not stop/restart the worker")
    monkeypatch.setattr(WatchFilesReload, "restart", forbidden)
    cls = qr.make_reloader(str(tmp_path), "http://unused")
    object.__new__(cls).restart()
    files = list((control_dir(tmp_path) / "requests").glob("*.json"))
    assert len(files) == 1
    assert read_json(files[0])["expected_generation"] == "g"


def test_Q4_installed_uvicorn_adapter():
    um = importlib.import_module("uvicorn.main")
    original = um.ChangeReload
    try:
        assert qr.install(ROOT)
        assert um.ChangeReload is not original
    finally:
        um.ChangeReload = original


def test_Q5_api_delegates_before_import_side_effects():
    src = (ROOT / "backend/api.py").read_text()
    assert src.index("controller_main(code_root=") < src.index("from fastapi import")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "uvicorn" and n.func.attr == "run"]
    assert len(calls) == 1
    assert isinstance(calls[0].args[0], ast.Name) and calls[0].args[0].id == "app"
    assert next(kw.value.value for kw in calls[0].keywords if kw.arg == "reload") is False


def test_Q6_legacy_gate_boot_recovery_preserved(tmp_path):
    gate.mark_written(tmp_path, "old")
    assert gate.clear_at_boot(tmp_path)
    gate.raise_gate(tmp_path, "writer")
    assert not gate.clear_at_boot(tmp_path)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
