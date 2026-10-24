"""Windows Chrome 창·탭 드라이버(PC제어 chrome_* 동작, pc_chrome_windows.ps1) — 허브 계약·검증·배정·복호. 실기기 없음(실측은 설계 §18)."""
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

pytestmark = pytest.mark.usefixtures("installed_functions")

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pc_control_chrome_test", ROOT / "data/scripts/pc_control.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)
CHROME_ACTIONS = ["chrome_launch", "chrome_status", "chrome_open", "chrome_switch", "chrome_close"]
TAB = "87D37BE6C1A24F0B9E3D5A7C8B1F2E4D"
REV = hashlib.sha256(b"x").hexdigest()
SOURCE = (ROOT / "data/instruments/pc_chrome_windows.ps1").read_text(encoding="utf-8")
LIMB_WIN = [{"device_id": "tv1", "connected": True, "registration": {"state": "active", "capabilities": {"os": "windows", "shell": True}}}]
LIMB_MAC = [{"device_id": "mac12", "connected": True, "registration": {"state": "active", "capabilities": {"os": "macos", "shell": True}}}]


def test_chrome_actions_are_windows_only_background_and_declared_in_source():
    for action in CHROME_ACTIONS:
        assert pc.CONTRACT["action_platforms"][action] == ["windows"]
        c = pc.CONTRACT["conditions"][action]
        assert c["needs_front"] is False and c["verification_scope"]
        assert f"'{action}'" in SOURCE, f"Windows 실행 파일에 {action} 분기가 없습니다"
    assert pc.CONTRACT["conditions"]["chrome_open"]["shared_state"] is False, "배경 탭 생성은 공유 상태를 바꾸지 않는다"
    assert pc.CONTRACT["conditions"]["chrome_switch"]["shared_state"] is True
    assert "--remote-debugging-port=0" in SOURCE and "DevToolsActivePort" in SOURCE and "IndieBiz\\ChromeProfile" in SOURCE
    assert "background=$true" in SOURCE, "열기는 CDP background 생성"
    assert "document.visibilityState" in SOURCE, "현재 탭은 표시 상태로 판별"


def test_select_routes_chrome_to_dedicated_instrument_and_refuses_mac():
    chosen = pc.select_target({"target": "tv1", "request": {"action": "chrome_status"}, "limbs": LIMB_WIN})
    assert chosen["source_path"].endswith("pc_chrome_windows.ps1") and chosen["timeout"] == 30
    assert set(CHROME_ACTIONS) <= set(chosen["supported_actions"])
    launch = pc.select_target({"target": "tv1", "request": {"action": "chrome_launch"}, "limbs": LIMB_WIN})
    assert launch["timeout"] == 120 and launch["wait"] == 150
    with pytest.raises(ValueError, match="windows"):
        pc.select_target({"target": "mac12", "request": {"action": "chrome_status"}, "limbs": LIMB_MAC})
    plan = pc.prepare({"platform": "windows", "source": "native", "request": {"action": "chrome_open", "url": "about:blank"}})
    assert plan["command"].startswith("powershell.exe") and plan["request"]["url"] == "about:blank"
    with pytest.raises(ValueError):
        pc.prepare({"platform": "darwin", "source": "native", "request": {"action": "chrome_status"}})


@pytest.mark.parametrize("payload", [
    {"action": "chrome_open"}, {"action": "chrome_open", "url": "ftp://x"}, {"action": "chrome_open", "url": "https://u:p@x.test/"},
    {"action": "chrome_open", "url": "https://www.youtube.com/watch?v=BzYnNdJhZQw"}, {"action": "chrome_open", "url": "https://youtu.be/BzYnNdJhZQw"},
    {"action": "chrome_open", "url": "https://x.test/", "expected": REV}, {"action": "chrome_open", "url": "https://x.test/", "launch": "yes"},
    {"action": "chrome_switch", "window_id": 1, "tab": 2, "expected": REV}, {"action": "chrome_switch", "window_id": 1, "tab": TAB},
    {"action": "chrome_switch", "window_id": 0, "tab": TAB, "expected": REV}, {"action": "chrome_close", "window_id": 1, "tab": TAB.lower(), "expected": REV},
    {"action": "chrome_close", "window_id": 1, "tab": TAB, "expected": "abc"}, {"action": "chrome_status", "tab": TAB},
    {"action": "chrome_launch", "shortcut": 1},
])
def test_invalid_chrome_requests_are_rejected_before_transport(payload):
    with pytest.raises(ValueError):
        pc.validate(payload)


def test_valid_chrome_requests_keep_tab_as_target_id_not_position():
    r = pc.validate({"action": "chrome_close", "window_id": 1378650243, "tab": TAB, "expected": REV})
    assert r == {"action": "chrome_close", "window_id": 1378650243, "tab": TAB, "expected": REV}
    r = pc.validate({"action": "chrome_open", "url": "https://news.hada.io/", "window_id": 7, "expected": REV, "launch": True})
    assert r["launch"] is True and r["expected"] == REV
    assert pc.validate({"action": "chrome_open", "url": "https://www.youtube.com/"})["url"] == "https://www.youtube.com/"  # 영상 아닌 유튜브 홈은 허용


def _decode(action, state, **req):
    plan = pc.prepare({"platform": "windows", "source": "native", "request": {"action": action, **req}})
    body = {"protocol": "pc-control/1", "platform": "windows", "action": action, "request_id": plan["request"]["request_id"],
            "success": True, "surface": "app:com.google.Chrome", **state}
    return pc.decode("noise\n" + pc.MARKER + json.dumps(body) + "\n", plan)


def test_decode_requires_verified_and_action_specific_checks():
    assert _decode("chrome_status", {"verified": True, "windows": []})["windows"] == []
    with pytest.raises(ValueError):
        _decode("chrome_status", {"verified": True})
    ok = _decode("chrome_open", {"verified": True, "checks": {"created_tab_identified": True, "existing_state_preserved": True}}, url="about:blank")
    assert ok["verified"] is True
    with pytest.raises(ValueError, match="보존"):
        _decode("chrome_open", {"verified": True, "checks": {"created_tab_identified": True, "existing_state_preserved": False}}, url="about:blank")
    with pytest.raises(ValueError):
        _decode("chrome_switch", {"verified": True, "checks": {"current_tab_matches": False}}, window_id=1, tab=TAB, expected=REV)
    with pytest.raises(ValueError):
        _decode("chrome_close", {"verified": True, "checks": {}}, window_id=1, tab=TAB, expected=REV)


def test_native_failure_keeps_failure_code_and_state_for_recovery():
    plan = pc.prepare({"platform": "windows", "source": "native", "request": {"action": "chrome_close", "window_id": 1, "tab": TAB, "expected": REV}})
    body = {"protocol": "pc-control/1", "platform": "windows", "action": "chrome_close", "request_id": plan["request"]["request_id"],
            "success": False, "surface": "app:com.google.Chrome", "verified": False, "error": "STATE_CHANGED: 바뀜", "error_code": "STATE_CHANGED",
            "failure": {"code": "STATE_CHANGED", "message": "바뀜", "next": "다시 선택", "state": {"window_id": 1}}}
    with pytest.raises(pc.ControlFailure) as e:
        pc.decode(pc.MARKER + json.dumps(body, ensure_ascii=False), plan)
    assert e.value.state["failure"]["code"] == "STATE_CHANGED" and e.value.state["source_sha256"] == plan["source_sha256"]


def test_guides_name_the_windows_route_and_compile():
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_store import definitions
    pc_guide = (ROOT / "data/guides/pc_control.md").read_text(encoding="utf-8")
    chrome_guide = (ROOT / "data/guides/chrome_control.md").read_text(encoding="utf-8")
    assert "chrome_open" in pc_guide and "pc_chrome_windows.ps1" in pc_guide
    assert "chrome_status" in chrome_guide, "맥 가이드가 Windows 경로(PC제어 chrome_*)를 안내해야 한다"
    for text in (pc_guide, chrome_guide):
        for code in re.findall(r"```ibl\n(.*?)```", text, re.S):
            plan = compile_program(code, load_registry(), definitions=definitions(), inputs={})
            assert not plan.issues, plan.report()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def test_native_chrome_snapshot_skips_only_minimized_page_visibility():
    import base64
    import shutil
    import subprocess
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell required; same fixture can run on registered Windows PC')
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-File',
        str(ROOT / 'backend/fixtures/pc_chrome_snapshot.ps1'), '-DriverBase64',
        base64.b64encode(SOURCE.encode()).decode()], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PC_CHROME_SNAPSHOT_OK' in result.stdout
