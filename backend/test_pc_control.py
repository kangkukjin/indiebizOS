"""PC 제어: 인수·실행 경계·검증 결과·OS별 대상 선택 회귀."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "data/instruments" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pc = module("pc_control")


@pytest.mark.parametrize("payload", [
    {"action": "unknown"}, {"action": "status", "value": 1},
    {"action": "volume", "device_id": "", "value": 10},
    *({"action": "volume", "device_id": "output", "value": value}
      for value in [-1, 101, True, 1.5, "30", float("nan")]),
    {"action": "mute", "device_id": "output", "enabled": "false"},
    *({"action": "open_url", "url": value} for value in [
        "file:///tmp/x", "javascript:alert(1)", "https://user:secret@example.com", "https://x/\nfoo"]),
])
def test_invalid_request_is_rejected_before_transport(payload):
    with pytest.raises(ValueError):
        pc.prepare({"platform": "windows", "source": "native", "request": payload})


def test_input_is_data_and_does_not_enter_shell_command():
    url = 'https://example.com/?x=$(touch%20x)&a="quoted"'
    plan = pc.prepare({"platform": "windows", "source": "native", "request": {"action": "open_url", "url": url}})
    assert url not in plan["command"] and url not in plan["stdin"]
    assert plan["request"]["url"] == url
    assert len(plan["source_sha256"]) == 64


def test_mutation_requires_matching_readback():
    plan = pc.prepare({"platform": "darwin", "source": "native", "request": {"action": "volume", "device_id": "a", "value": 30}})
    state = {"protocol": pc.PROTOCOL, "platform": "darwin", "action": "volume",
             "request_id": plan["request"]["request_id"], "success": True, "verified": True,
             "device": {"id": "a", "volume": 30}}
    emit = lambda value: pc.MARKER + json.dumps(value)
    assert pc.decode("diagnostic\n" + emit(state), plan)["device"]["volume"] == 30
    for override in [{"request_id": "old"}, {"platform": "windows"}, {"action": "status"},
                     {"verified": False}, {"device": {"id": "b", "volume": 30}},
                     {"device": {"id": "a", "volume": 99}}, {"success": False}]:
        with pytest.raises(ValueError):
            pc.decode(emit({**state, **override}), plan)
    for output in ["", emit(state) + "\n" + emit(state)]:
        with pytest.raises(ValueError):
            pc.decode(output, plan)


def test_wrong_local_os_never_starts_process(monkeypatch):
    monkeypatch.setattr(pc.sys, "platform", "darwin")
    monkeypatch.setattr(pc.subprocess, "run", lambda *a, **k: pytest.fail("wrong OS executed"))
    with pytest.raises(ValueError, match="본체 OS"):
        pc.run({"op": "local", "platform": "windows", "source": "native"})


def test_mac_url_is_one_argument_and_never_claims_playback(monkeypatch):
    mac = module("pc_control_mac")
    monkeypatch.setattr(mac.sys, "platform", "darwin")
    calls = []
    monkeypatch.setattr(mac.subprocess, "run", lambda argv, **kw: calls.append(argv))
    url = "https://example.com/?q=a&b=c"
    result = mac.run({"action": "open_url", "url": url})
    assert calls == [["/usr/bin/open", url]]
    assert result["verified"] is False


def test_pc_picker_and_response_guards():
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const ts=require('./frontend/node_modules/typescript'),m={exports:{}};
vm.runInNewContext(ts.transpile(fs.readFileSync('frontend/src/lib/pc-control.ts','utf8'),{module:ts.ModuleKind.CommonJS}),{exports:m.exports,require:()=>({})});
const api=m.exports;
const row=(id,os,extra={})=>({device_id:id,alias:id,connected:true,registration:{state:'active',capabilities:{os,shell:true}},...extra});
const value={host:{success:true,host_platform:'Darwin'},limbs:[row('win','windows'),row('mac','darwin'),row('old','windows',{revoked:true}),row('phone','android'),row('removed','windows',{registration:{state:'removed',capabilities:{os:'windows',shell:true}}})]};
assert.equal(api.pcTargets(value,'windows').map(p=>p.id).join(','),'win');
assert.equal(api.pcTargets(value,'darwin').map(p=>p.id).join(','),'__local__,mac');
value.limbs[0].registration.paused=true;
assert.equal(api.pcTargets(value,'windows')[0].ready,false);
assert.throws(()=>api.pcState({success:false,error:'lost'},'windows','status'));
assert.throws(()=>api.pcState({success:true,protocol:'pc-control/1',platform:'darwin',action:'status',devices:[]},'windows','status'));
const code=api.pcCommandCode('remote','windows','volume',{device_id:'a"b',value:30});
assert.ok(code.includes('stdin:$p.stdin'));assert.ok(code.includes('op:"decode"'));
assert.ok(!code.includes('%BASE%'));assert.ok(!code.includes('localhost'));
'''
    result = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_control_guide_mapping_is_data_and_requires_real_file(tmp_path, monkeypatch):
    import guide_registry as registry
    monkeypatch.setattr(registry, "DATA_PATH", tmp_path)
    monkeypatch.setattr(registry, "GUIDES_DIR", tmp_path / "guides")
    (tmp_path / "guides").mkdir()
    (tmp_path / "guides/control.md").write_text("guide")
    (tmp_path / "guide_db.json").write_text(json.dumps({"guides": [
        {"file": "control.md", "control_platforms": ["Darwin", "windows"]},
        {"file": "missing.md", "control_platforms": ["other"]},
        {"file": "../outside.md", "control_platforms": ["unsafe"]}]}))
    assert registry.device_control_guides() == {"darwin": "control.md", "windows": "control.md"}


def test_both_app_sources_are_available():
    import api_launcher_web
    for app in ("mac_control", "windows_control"):
        source = api_launcher_web.app_source(app)
        assert source["kind"] == "component"
        assert "PCControlInstrument" in source["code"]


@pytest.mark.parametrize("guide", ["android_control.md", "pc_control.md", "tv_control.md"])
def test_hardware_guide_ibl_examples_compile(guide):
    import re
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    text = (ROOT / "data/guides" / guide).read_text()
    blocks = re.findall(r"```ibl\n(.*?)```", text, re.S)
    assert blocks
    for code in blocks:
        if not code.startswith("#!ibl"):
            code = "#!ibl edition=2\n" + code
        compile_program(code, load_registry(), inputs={
            "f": {"path": "example.py"}, "os": "darwin", "native": {"text": "source"}})


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
