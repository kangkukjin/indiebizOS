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


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=T7tCIDC84EE",
    "https://youtu.be/T7tCIDC84EE?t=30",
    "https://music.youtube.com/playlist?list=example",
    "https://m.youtube.com/shorts/example",
    "https://youtube.com/live/example",
    "https://www.youtube-nocookie.com/embed/example",
    "https://WWW.YOUTUBE.COM./%77atch?v=example",
])
@pytest.mark.parametrize("platform", ["darwin", "windows"])
def test_youtube_playback_never_uses_unmanaged_url_launch(url, platform, monkeypatch):
    monkeypatch.setattr(pc.subprocess, "run", lambda *a, **kw: pytest.fail("launched another player"))
    for op in ("prepare", "local"):
        with pytest.raises(ValueError, match="기존 영상과 겹칠"):
            pc.run({"op": op, "platform": platform, "source": "native",
                    "request": {"action": "open_url", "url": url}})


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/", "https://www.youtube.com/results?search_query=rain",
    "https://example.com/watch?v=example", "https://youtube.com.example.org/watch",
])
def test_general_web_browsing_remains_available(url):
    assert pc.prepare({"platform": "windows", "source": "native",
                       "request": {"action": "open_url", "url": url}})["request"]["url"] == url


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


@pytest.mark.parametrize('platform', ['darwin', 'windows'])
def test_audio_status_exposes_read_only_verification_scope(platform):
    plan = pc.prepare({'platform': platform, 'source': 'native', 'request': {'action': 'status'}})
    state = {'protocol': pc.PROTOCOL, 'platform': platform, 'action': 'status',
             'request_id': plan['request']['request_id'], 'success': True, 'verified': True,
             'devices': []}
    result = pc.decode(pc.MARKER + json.dumps(state), plan)
    assert result['verification_scope'] == 'os_state_readback'
    contract = pc.run({'op': 'contract'})['audio_capabilities']
    assert result['audio_capabilities'] == contract
    assert result['audio_capabilities']['scope'] == 'os_api_support'
    assert contract['setter_tested_by_status'] is False
    assert contract['physical_sound_verified'] is False


@pytest.mark.parametrize('settable', [True, False])
def test_mac_capabilities_keep_property_evidence(monkeypatch, settable):
    mac = module('pc_control_mac')
    audio = object.__new__(mac.Audio)
    monkeypatch.setattr(audio, 'slots', lambda *args: [(0, 0.5, settable)])
    monkeypatch.setattr(audio, 'text', lambda device, prop: prop)
    result = audio.describe(1, 1)
    assert result['can_set_volume'] is settable and result['can_mute'] is settable
    assert result['capability_basis'] == 'coreaudio_property_settable'


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
assert.ok(code.includes('[fn:PC제어]'));assert.ok(!code.includes('stdin:'));
assert.ok(code.includes('device_id'));
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
        from ibl_v2_store import definitions
        plan = compile_program(code, load_registry(), definitions=definitions(), inputs={
            "f": {"path": "example.py"}, "os": "darwin", "native": {"text": "source"}})
        assert not plan.issues, plan.report()


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def youtube_fixture():
    request = {"action": "youtube_replace", "url": "https://youtu.be/abcdefghijk?t=20",
               "title": "Test video", "duration_seconds": 120, "fullscreen": True}
    plan = pc.prepare({"platform": "windows", "source": "native", "request": request})
    state = {"protocol": pc.PROTOCOL, "platform": "windows", "action": "youtube_replace",
             "request_id": plan["request"]["request_id"], "success": True, "verified": True,
             "previous_stopped": True, "playback_verified": True, "fullscreen_verified": True,
             "tab_count_before": 3, "tab_count_after": 3,
             "playback": {"url": "https://youtube.com/watch?v=abcdefghijk", "video_id": "abcdefghijk",
                          "title": "Test video", "duration": 120, "ad": False, "playing": True,
                          "position": 10, "previous_position": 8}}
    return plan, state


def test_youtube_replacement_requires_correlated_playback_evidence():
    plan, state = youtube_fixture()
    assert plan["request"]["url"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert "-STA" in plan["command"]
    assert pc.decode(pc.MARKER + json.dumps(state), plan)["playback_verified"] is True
    for override in ({"ad": True}, {"playing": False}, {"video_id": "wrong_video"},
                     {"url": "https://example.com/watch?v=abcdefghijk"}, {"title": "Another video"},
                     {"duration": 30}, {"position": 8}, {"position": 99},
                     {"position": float("nan")}, {"previous_position": None}):
        with pytest.raises(ValueError, match="본영상"):
            pc.decode(pc.MARKER + json.dumps({**state, "playback": {**state["playback"], **override}}), plan)
    for override in ({"previous_stopped": False}, {"verified": False}, {"playback_verified": False}, {"fullscreen_verified": False},
                     {"tab_count_after": 4}, {"tab_count_before": None, "tab_count_after": None},
                     {"tab_count_before": True, "tab_count_after": True}, {"request_id": "stale"}):
        with pytest.raises(ValueError):
            pc.decode(pc.MARKER + json.dumps({**state, **override}), plan)


@pytest.mark.parametrize("override", [
    {"url": "http://youtube.com/watch?v=abcdefghijk"}, {"url": "https://example.com/watch?v=abcdefghijk"},
    {"url": "https://youtube.com/playlist?list=abcdefghijk"}, {"duration_seconds": 0},
    {"duration_seconds": True}, {"duration_seconds": 120.5}, {"title": ""}, {"fullscreen": "true"},
])
def test_youtube_unknown_video_metadata_is_not_executed(override):
    plan, _ = youtube_fixture()
    request = {k: v for k, v in plan["request"].items() if k != "request_id"}
    with pytest.raises(ValueError):
        pc.prepare({"platform": "windows", "source": "native", "request": {**request, **override}})


def test_mac_does_not_claim_automatic_browser_replacement():
    with pytest.raises(ValueError, match="Windows"):
        pc.prepare({"platform": "darwin", "source": "native", "request": {"action": "youtube_status"}})


def test_native_failure_keeps_advertisement_observation():
    plan, state = youtube_fixture()
    state.update(success=False, verified=False, error="본영상 미확인",
                 last_observation={"state": "advertisement", "ad": True, "duration": 104})
    with pytest.raises(pc.ControlFailure) as failure:
        pc.decode(pc.MARKER + json.dumps(state), plan)
    assert failure.value.state["last_observation"]["ad"] is True


def test_generated_youtube_flow_waits_before_decoding_and_compiles(tmp_path):
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const ts=require('./frontend/node_modules/typescript'),m={exports:{}};
let request;
vm.runInNewContext(ts.transpile(fs.readFileSync('frontend/src/lib/pc-control.ts','utf8'),{module:ts.ModuleKind.CommonJS}),
 {exports:m.exports,require:()=>({iblExecuteApp:async code=>{request=code;return {success:true,items:[
 {url:'https://youtube.com/watch?v=abcdefghijk',title:'Video',duration:'2:39:46'},
 {url:'https://youtube.com/watch?v=abcdefghijk',title:'Live',duration:'LIVE'}]};}})});
(async()=>{
 const videos=await m.exports.searchPCVideos('rain');
 assert.equal(videos.length,1);assert.equal(videos[0].duration_seconds,9586);
 const code=m.exports.pcCommandCode('registered-device','windows','youtube_replace',{...videos[0],fullscreen:true});
 assert.ok(code.includes('[fn:PC제어]'));
 assert.ok(!code.includes('pc_youtube_windows.ps1'));
 assert.ok(code.includes('youtube_replace'));
 process.stdout.write(JSON.stringify([request,code,m.exports.pcCommandCode('registered-device','windows','youtube_status')]));
})().catch(e=>{console.error(e);process.exit(1)});
'''
    output = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert output.returncode == 0, output.stderr
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    codes = json.loads(output.stdout)
    registry = load_registry(str(tmp_path))
    for code in codes:
        from ibl_v2_store import definitions
        plan = compile_program(code, registry, definitions=definitions())
        assert not plan.issues, plan.report()


# ---------------------------------------------------------------- 본체 OS 조작면 (2026-10-20 1층)
# 설계 docs/CONTROL_DRIVER_DESIGN_2026_10_20.md §17. OS 명령 이름은 실행 파일에만 두고 이 시험은
# 출력 텍스트 대역과 허브 계약만 다룬다.

mac_native = module("pc_control_mac")

HOST_ACTIONS = ["display", "brightness", "power", "presence", "apps", "launch", "quit", "clipboard",
                "clipboard_write", "network", "wifi", "shortcuts", "shortcut", "keep_awake", "allow_sleep", "sleep"]
HOST_PAYLOAD = {"brightness": {"value": 40}, "launch": {"app": "TextEdit"}, "quit": {"app": "com.apple.TextEdit"},
                "clipboard_write": {"text": "x"}, "wifi": {"enabled": True}, "shortcut": {"name": "s"},
                "keep_awake": {"seconds": 10}}


def test_every_action_declares_platforms_and_conditions_without_needs_front():
    for action in pc.CONTRACT["actions"]:
        assert pc.CONTRACT["action_platforms"][action], action
        condition = pc.CONTRACT["conditions"][action]
        assert condition["needs_front"] is False, action
        assert isinstance(condition["shared_state"], bool) and condition["verification_scope"], action
    for action in HOST_ACTIONS:
        assert pc.CONTRACT["action_platforms"][action] == ["darwin", "windows"]


WINDOWS_SOURCE = (Path(__file__).resolve().parents[1] / "data/instruments/pc_control_windows.ps1").read_text(encoding="utf-8")


@pytest.mark.parametrize("action", HOST_ACTIONS)
def test_host_actions_plan_for_both_os_and_windows_source_declares_them(action):
    """§18 Windows 동형: 허브 계약·select·prepare·실행 파일 넷이 같은 동작 집합을 말해야 한다."""
    request = {"action": action, **HOST_PAYLOAD.get(action, {})}
    for platform in ("darwin", "windows"):
        plan = pc.prepare({"platform": platform, "source": "native", "request": request})
        assert plan["request"]["action"] == action and plan["platform"] == platform
    assert pc.prepare({"platform": "windows", "source": "native", "request": request})["command"].startswith("powershell.exe")
    chosen = pc.select_target({"target": "pc-w", "request": request, "limbs": [{
        "device_id": "pc-w", "connected": True, "registration": {
            "state": "active", "capabilities": {"os": "windows", "shell": True}}}]})
    assert chosen["source_path"].endswith("pc_control_windows.ps1") and action in chosen["supported_actions"]
    assert f"'{action}'" in WINDOWS_SOURCE, f"Windows 실행 파일에 {action} 분기가 없습니다"


def test_windows_source_keeps_admin_free_bases_honest():
    # 관리자만 읽히는 값(powercfg /requests)·공개 API 가 없는 값(화면 꺼짐·뚜껑)은 null+basis 로 남긴다.
    assert "powercfg_requests_requires_admin" in WINDOWS_SOURCE
    assert "lid_closed = $null" in WINDOWS_SOURCE and "display_asleep = $null" in WINDOWS_SOURCE
    quit_body = WINDOWS_SOURCE.split("function Stop-App")[1].split("function Read-ClipboardText")[0]
    assert "CloseMainWindow" in quit_body and "Stop-Process" not in quit_body  # quit 은 닫기 요청만, 강제 종료 없음
    assert "LockWorkStation" in WINDOWS_SOURCE and "SetSuspendState" in WINDOWS_SOURCE


@pytest.mark.parametrize("payload", [
    {"action": "brightness", "value": 101}, {"action": "brightness", "value": True},
    {"action": "brightness", "value": 10, "display_id": -1}, {"action": "brightness", "value": 10, "foo": 1},
    {"action": "launch", "app": ""}, {"action": "launch", "app": "a\nb"}, {"action": "quit"},
    {"action": "clipboard_write", "text": 1}, {"action": "clipboard_write", "text": "x" * 100_001},
    {"action": "wifi", "enabled": "on"}, {"action": "shortcut", "name": " "},
    {"action": "keep_awake", "seconds": 0}, {"action": "keep_awake", "seconds": 86401},
    {"action": "keep_awake", "seconds": 5, "display": "yes"}, {"action": "sleep", "value": 1},
])
def test_host_action_arguments_are_validated(payload):
    with pytest.raises(ValueError):
        pc.validate(payload)


def test_validated_launch_request_survives_prepare_revalidation():
    # select 가 app_kind 를 붙인 요청이 prepare 로 되돌아온다. 재검증이 그 파생 칸을 거절하면 launch·quit 은 어느 OS 에서도 접수되지 않는다.
    for action in ("launch", "quit"):
        chosen = pc.validate({"action": action, "app": "notepad.exe"})
        assert chosen["app_kind"] == "bundle"
        plan = pc.prepare({"platform": "windows", "source": "native", "request": chosen})
        assert plan["request"]["app"] == "notepad.exe" and plan["request"]["app_kind"] == "bundle"
    with pytest.raises(ValueError):
        pc.validate({"action": "launch", "app": "x", "app_kind": "name", "extra": 1})


def test_app_argument_is_classified_as_bundle_or_name():
    assert pc.validate({"action": "launch", "app": "com.apple.TextEdit"})["app_kind"] == "bundle"
    assert pc.validate({"action": "launch", "app": " TextEdit "}) == {"action": "launch", "app": "TextEdit", "app_kind": "name"}
    assert pc.validate({"action": "quit", "app": "Visual Studio Code"})["app_kind"] == "name"
    assert pc.validate({"action": "keep_awake", "seconds": 30, "display": True})["display"] is True


def _plan_and_state(request, **state):
    plan = pc.prepare({"platform": "darwin", "source": "native", "request": request})
    base = {"protocol": pc.PROTOCOL, "platform": "darwin", "action": request["action"],
            "request_id": plan["request"]["request_id"], "success": True, "verified": True}
    return plan, {**base, **state}


@pytest.mark.parametrize("request_, state, ok", [
    ({"action": "brightness", "value": 40}, {"display": {"id": 3, "brightness": 41}}, True),
    ({"action": "brightness", "value": 40}, {"display": {"id": 3, "brightness": 50}}, False),
    ({"action": "brightness", "value": 40, "display_id": 3}, {"display": {"id": 4, "brightness": 40}}, False),
    ({"action": "launch", "app": "TextEdit"}, {"app": {"running": True}}, True),
    ({"action": "launch", "app": "TextEdit"}, {"app": {"running": False}}, False),
    ({"action": "quit", "app": "TextEdit"}, {"app": {"running": False}}, True),
    ({"action": "quit", "app": "TextEdit"}, {"app": {"running": True}}, False),
    ({"action": "clipboard_write", "text": "abc"}, {"length": 3}, True),
    ({"action": "clipboard_write", "text": "abc"}, {"length": 2}, False),
    ({"action": "wifi", "enabled": False}, {"wifi": {"enabled": False}}, True),
    ({"action": "wifi", "enabled": False}, {"wifi": {"enabled": True}}, False),
    ({"action": "keep_awake", "seconds": 5}, {"keep_awake": {"pid": 12}}, True),
    ({"action": "keep_awake", "seconds": 5}, {"keep_awake": {"pid": None}}, False),
    ({"action": "power"}, {"verified": False}, False),
    ({"action": "power"}, {}, True),
])
def test_host_mutations_require_matching_readback(request_, state, ok):
    plan, native = _plan_and_state(request_, **state)
    emit = pc.MARKER + json.dumps(native)
    if ok:
        decoded = pc.decode(emit, plan)
        assert decoded["verification_scope"] == pc.CONTRACT["conditions"][request_["action"]]["verification_scope"]
        assert decoded["condition"] == {"needs_front": False, "shared_state": pc.CONTRACT["conditions"][request_["action"]]["shared_state"]}
    else:
        with pytest.raises(ValueError):
            pc.decode(emit, plan)


def test_native_failure_keeps_observation_for_host_action():
    plan, native = _plan_and_state({"action": "brightness", "value": 40}, success=False, verified=False,
                                   error="이 화면은 밝기 변경을 지원하지 않습니다")
    with pytest.raises(pc.ControlFailure) as info:
        pc.decode(pc.MARKER + json.dumps(native), plan)
    assert info.value.state["error"].startswith("이 화면은")


APP_LIST_SAMPLE = '''
 1) "loginwindow" ASN:0x0-0x1001: 
    bundleID="com.apple.loginwindow"
    bundle path="/System/Library/CoreServices/loginwindow.app"
    pid = 168 type="UIElement" flavor=3 Version="3085.6.3" fileType="APPL" creator="lgnw" Arch=ARM64 
 2) "universalaccessd" ASN:0x0-0x7007: 
    bundleID=[ NULL ] 
    bundle path="/usr/sbin/universalaccessd"
    pid = 363 !signalled type="BackgroundOnly" flavor=3 Version=[ NULL ]  fileType="????" creator="????" Arch=ARM64 
 3) "텍스트 편집기" ASN:0x0-0x9a09a: 
    bundleID="com.apple.TextEdit"
    bundle path="/System/Applications/TextEdit.app"
    executable path="/System/Applications/TextEdit.app/Contents/MacOS/TextEdit"
    pid = 77892 type="Foreground" flavor=3 Version="1.20" fileType="APPL" creator="ttxt" Arch=ARM64 
'''


def test_native_app_list_parsing_and_localized_name_matching():
    rows = mac_native.parse_app_list(APP_LIST_SAMPLE)
    assert [r["pid"] for r in rows] == [168, 363, 77892]
    assert rows[1]["bundle_id"] is None and rows[1]["type"] == "BackgroundOnly"
    textedit = rows[2]
    assert textedit["bundle_id"] == "com.apple.TextEdit" and textedit["type"] == "Foreground"
    assert mac_native.app_names(textedit) == {"텍스트 편집기", "textedit.app", "textedit"}
    by_bundle = pc.validate({"action": "quit", "app": "com.apple.textedit"})
    by_name = pc.validate({"action": "launch", "app": "TextEdit"})
    by_local = pc.validate({"action": "launch", "app": "텍스트 편집기"})
    assert [mac_native.match_app(rows, r)[0]["pid"] for r in (by_bundle, by_name, by_local)] == [77892] * 3
    assert mac_native.match_app(rows, pc.validate({"action": "launch", "app": "Nothing"})) == []
    info = mac_native.parse_app_info('"pid"=9806\n"CFBundleIdentifier"="com.example.app"\n"LSDisplayName"="예시 앱"\n')
    assert info == {"pid": 9806, "bundle_id": "com.example.app", "name": "예시 앱"}


ASSERTIONS_SAMPLE = '''2026-10-20 20:01:47 +0900 
Assertion status system-wide:
   BackgroundTask                 0
   UserIsActive                   1
   PreventUserIdleDisplaySleep    0
   PreventSystemSleep             0
   PreventUserIdleSystemSleep     1
Listed by owning process:
   pid 72348(IndieBiz): [0x003e6353000196e3] 00:52:47 PreventUserIdleSystemSleep named: "handling Apple event"  
   pid 20222(Claude): [0x003e6ee900019812] 00:03:22 NoIdleSleepAssertion named: "Electron"  
   pid 76471(sleepless): [0x003e6fbf0001981e] 00:00:00 PreventUserIdleSystemSleep named: "command-line tool"  
	Details: asserting for 4 secs
   pid 165(WindowServer): [0x003e43b000098d74] 00:00:00 UserIsActive named: "tickle"  
Kernel Assertions: 0x104=USB,MAGICWAKE
'''


def test_native_power_and_presence_parsers():
    parsed = mac_native.parse_assertions(ASSERTIONS_SAMPLE)
    assert parsed["flags"] == {"UserIsActive": 1, "PreventUserIdleDisplaySleep": 0,
                               "PreventUserIdleSystemSleep": 1, "PreventSystemSleep": 0}
    assert [h["pid"] for h in parsed["sleep_holders"]] == [72348, 20222, 76471]
    assert parsed["sleep_holders"][2] == {"pid": 76471, "process": "sleepless", "kind": "PreventUserIdleSystemSleep", "name": "command-line tool"}
    assert mac_native.parse_battery("Now drawing from 'AC Power'\n") == {"power_source": "AC Power", "battery": None}
    laptop = mac_native.parse_battery("Now drawing from 'Battery Power'\n -InternalBattery-0 (id=123)\t87%; discharging; 3:10 remaining present: true\n")
    assert laptop == {"power_source": "Battery Power", "battery": {"percent": 87, "state": "discharging", "remaining": "3:10 remaining present: true"}}
    assert mac_native.parse_idle_seconds('  |   "HIDIdleTime" = 222951666\n') == 0.2
    assert mac_native.parse_idle_seconds("nothing") is None
    assert mac_native.parse_clamshell('      "AppleClamshellState" = Yes\n') is True
    assert mac_native.parse_clamshell("") is None


def test_native_network_parsers_treat_redacted_ssid_as_unknown():
    ports = "Hardware Port: Ethernet\nDevice: en0\nEthernet Address: aa\n\nHardware Port: Wi-Fi\nDevice: en1\nEthernet Address: bb\n"
    assert mac_native.parse_wifi_port(ports) == "en1"
    assert mac_native.parse_wifi_port("Hardware Port: Ethernet\nDevice: en0\n") is None
    assert mac_native.parse_wifi_power("Wi-Fi Power (en1): On\n") is True
    assert mac_native.parse_wifi_power("Wi-Fi Power (en1): Off\n") is False
    assert mac_native.parse_ssid("  SSID : <redacted>\n") is None
    assert mac_native.parse_ssid("  SSID : HomeNet 5G\n") == "HomeNet 5G"


def test_native_keep_awake_record_reports_dead_process(tmp_path, monkeypatch):
    monkeypatch.setattr(mac_native, "KEEP_AWAKE_FILE", str(tmp_path / "keep.json"))
    assert mac_native.keep_awake_record() is None
    (tmp_path / "keep.json").write_text(json.dumps({"pid": 2 ** 22 - 1, "seconds": 5}), encoding="utf-8")
    record = mac_native.keep_awake_record()
    assert record["alive"] is False and record["seconds"] == 5
    assert mac_native.allow_sleep() == {"keep_awake": None, "verified": True, "message": "잠들지 않기를 끄고 프로세스 종료를 확인했습니다."}
    assert not (tmp_path / "keep.json").exists()


def test_native_run_host_dispatches_every_host_action(monkeypatch):
    seen = []
    for action in HOST_ACTIONS:
        if action == "sleep":
            monkeypatch.setattr(mac_native, "sh", lambda argv, **kw: seen.append(argv) or "")
        else:
            name = {"display": None, "brightness": None, "power": "power_status", "presence": "presence", "apps": "apps_status",
                    "launch": "launch_app", "quit": "quit_app", "clipboard": "clipboard_read", "clipboard_write": "clipboard_write",
                    "network": "network_status", "wifi": "wifi_set", "shortcuts": "shortcuts_list", "shortcut": "shortcut_run",
                    "keep_awake": "keep_awake", "allow_sleep": "allow_sleep"}[action]
            if name:
                monkeypatch.setattr(mac_native, name, lambda *a, _n=action, **kw: {"verified": True, "did": _n})
        if action in {"display", "brightness"}:
            continue
        out = mac_native.run_host({"action": action, **HOST_PAYLOAD.get(action, {})})
        assert out["verified"] is (action != "sleep"), action
    assert seen and seen[0][-1] == "sleepnow"
    assert mac_native.run_host({"action": "status"}) is None
