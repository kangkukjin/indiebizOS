"""Chrome 창·탭 드라이버(chrome_control.py) — Chrome 사전 고유 사항(문자열 id·영구 탭 id·새 탭 활성 복원)과 등록·가이드. 실기기 없음."""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("control_driver_chrome", ROOT / "data/scripts/chrome_control.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def chrome(monkeypatch):
    """Chrome 사전 모의: 창·탭 id 는 문자열, 탭에 index 없음, make new tab 은 새 탭을 활성으로 만든다(실측 155)."""
    mod = _load()
    monkeypatch.setattr(mod.sys, "platform", "darwin")
    state = {"running": True, "calls": [], "hang": None, "restore": True,
             "windows": {"99058850": {"name": "w", "active": 2, "mode": "normal", "minimized": False,
                                      "tabs": [["99058851", "https://a.test/", "A"], ["99058852", "https://b.test/", "B"],
                                               ["99058853", "https://b.test/", "B2"]]}},
             "next_id": 99062800}

    def fmt(v):
        if isinstance(v, list):
            return "{" + ", ".join(fmt(x) for x in v) + "}"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            return json.dumps(v)
        return str(v)

    def guard_ok(script, w):
        ids = re.search(r"if \(id of every tab of w\) is not equal to (\{[^}]*\})", script)
        active = re.search(r"\(active tab index of w\) is not equal to (\d+) then error", script)
        if ids and json.loads("[" + ids[1][1:-1] + "]") != [t[0] for t in w["tabs"]]:
            raise mod.Failure("STATE_CHANGED", "guard")
        if active and int(active[1]) != w["active"]:
            raise mod.Failure("STATE_CHANGED", "guard")

    def fake_apple_event(script, timeout=10):
        state["calls"].append(script)
        hang = bool(state["hang"] and state["hang"] in script)
        if hang:
            state["hang"] = None
        if "is running" in script:
            return "true" if state["running"] else "false"
        if "chrome_snapshot_v1" in script:
            m = re.search(r"set selectedWindows to \{window id (\d+)\}", script)
            rows = [[wid, w["name"], w["active"], w["mode"], w["minimized"], [list(c) for c in zip(*w["tabs"])]]
                    for wid, w in state["windows"].items() if not m or wid == m[1]]
            return fmt(rows)
        wid = re.search(r"window id (\d+)", script)
        w = state["windows"].get(wid[1]) if wid else None
        if w is None:
            raise mod.Failure("TARGET_MISSING", "no window", os_error=-1728)
        guard_ok(script, w)
        if "make new tab" in script:
            url = json.loads(re.search(r"URL:(\"(?:[^\"\\]|\\.)*\")", script)[1])
            tid = str(state["next_id"]); state["next_id"] += 1
            w["tabs"].append([tid, url, "new"])
            w["active"] = len(w["tabs"])                     # Chrome 이 새 탭을 활성으로
            restore = re.search(r"then set active tab index of w to (\d+)", script)
            if restore and state["restore"]:
                w["active"] = int(restore[1])
            if hang:
                raise subprocess.TimeoutExpired(script, timeout)
            return fmt([wid[1], tid, w["active"]])
        if "set active tab index of w to" in script:
            w["active"] = int(re.search(r"set active tab index of w to (\d+)", script)[1])
            if hang:
                raise subprocess.TimeoutExpired(script, timeout)
            return ""
        if "close tab id" in script:
            tid = json.loads(re.search(r"close tab id (\"\d+\")", script)[1])
            pos = [t[0] for t in w["tabs"]].index(tid)
            w["tabs"].pop(pos)
            if not w["tabs"]:
                del state["windows"][wid[1]]
            else:
                w["active"] = min(w["active"] - (pos + 1 < w["active"]), len(w["tabs"]))
            return ""
        raise AssertionError(script)

    monkeypatch.setattr(mod, "apple_event", fake_apple_event)
    mod._state = state
    return mod


def test_contract_declares_conditions_and_platform(chrome, monkeypatch):
    c = chrome.run({"op": "contract"})
    assert c["surface"] == "app:com.google.Chrome" and c["supported_platforms"] == ["darwin"]
    assert all({"needs_front", "shared_state", "isolated_resources", "verification_scope"} <= set(a) for a in c["actions"].values())
    assert not any(a["needs_front"] for a in c["actions"].values())
    for bad in ({"op": "open"}, {"op": "open", "url": "ftp://x"}, {"op": "switch", "window_id": 1},
                {"op": "close", "window_id": 1, "tab": 0}, {"op": "fly"}, {"op": "status", "url": "https://x"}):
        with pytest.raises(chrome.Failure):
            chrome.run(bad)
    monkeypatch.setattr(chrome.sys, "platform", "win32")
    with pytest.raises(chrome.Failure) as e:
        chrome.run({"op": "status"})
    assert e.value.code == "UNSUPPORTED_PLATFORM" and chrome._state["calls"] == []


def test_status_normalizes_text_ids_and_revision_ignores_urls(chrome):
    s = chrome.run({"op": "status"})
    w = s["windows"][0]
    assert s["verified"] and w["window_id"] == 99058850 and w["mode"] == "normal" and w["minimized"] is False
    assert [t["tab_id"] for t in w["tabs"]] == [99058851, 99058852, 99058853]
    assert [t["index"] for t in w["tabs"]] == [1, 2, 3] and w["current_tab"] == 2
    # 탭 안의 페이지 이동(URL 변화)은 판본을 깨지 않는다 — 신원은 탭 id 다.
    chrome._state["windows"]["99058850"]["tabs"][0][1] = "https://a.test/moved"
    assert chrome.run({"op": "status"})["windows"][0]["revision"] == w["revision"]
    # 같은 URL 탭이 둘이어도 순서가 바뀌면 판본이 바뀐다.
    tabs = chrome._state["windows"]["99058850"]["tabs"]
    tabs[1], tabs[2] = tabs[2], tabs[1]
    assert chrome.run({"op": "status"})["windows"][0]["revision"] != w["revision"]


def test_open_restores_previous_active_tab_in_same_script(chrome):
    w = chrome.run({"op": "status"})["windows"][0]
    o = chrome.run({"op": "open", "url": "https://c.test/", "window_id": w["window_id"], "expected": w["revision"]})
    assert o["verified"] is True and o["tab"] == 4 and o["tab_id"] == 99062800 and o["current_tab"] == 2
    assert o["checks"]["activation_restored"] is True and o["checks"]["creation_receipt"] is True
    script = next(c for c in chrome._state["calls"] if "make new tab" in c)
    assert "set active tab index of w to 2" in script, "복원은 같은 AppleScript 안에서"
    assert o["target"] == {"window_id": 99058850, "tab": 4, "expected": o["state"]["revision"]}


def test_open_without_restoration_is_not_verified(chrome):
    chrome._state["restore"] = False
    w = chrome.run({"op": "status"})["windows"][0]
    o = chrome.run({"op": "open", "url": "https://c.test/", "window_id": w["window_id"], "expected": w["revision"]})
    assert o["success"] is False and o["error_code"] == "POSTCONDITION_FAILED"
    assert o["checks"]["created_tab_identified"] is True and o["checks"]["activation_restored"] is False
    assert o["recovery"]["retry_change"] is False and o["state"]["current_tab"] == 4


def test_close_targets_durable_tab_id_not_position(chrome):
    w = chrome.run({"op": "status"})["windows"][0]
    c = chrome.run({"op": "close", "window_id": w["window_id"], "tab": 3, "expected": w["revision"]})
    assert c["verified"] is True and c["closed_tab"]["tab_id"] == 99058853
    assert any('close tab id "99058853" of w' in s for s in chrome._state["calls"])
    assert [t["tab_id"] for t in c["state"]["tabs"]] == [99058851, 99058852] and c["state"]["current_tab"] == 2


def test_stale_revision_refuses_before_any_mutation(chrome):
    w = chrome.run({"op": "status"})["windows"][0]
    chrome._state["windows"]["99058850"]["tabs"].insert(0, ["99058000", "https://z.test/", "Z"])
    with pytest.raises(chrome.Failure) as e:
        chrome.run({"op": "close", "window_id": w["window_id"], "tab": 2, "expected": w["revision"]})
    assert e.value.code == "STATE_CHANGED"
    assert not any("close tab" in s or "set active tab" in s for s in chrome._state["calls"])


def test_native_guard_catches_change_between_read_and_write(chrome):
    w = chrome.run({"op": "status"})["windows"][0]
    original = chrome.apple_event

    def race(script, timeout=10):
        if "set active tab index of w to 3" in script and "CHROME_STATE_CHANGED" in script:
            chrome._state["windows"]["99058850"]["active"] = 1   # 사용자가 그 사이 탭을 바꿈
        return original(script, timeout)
    chrome.apple_event = race
    with pytest.raises(chrome.Failure) as e:
        chrome.run({"op": "switch", "window_id": w["window_id"], "tab": 3, "expected": w["revision"]})
    assert e.value.code == "STATE_CHANGED"


def test_switch_lost_response_reconciles_by_readback(chrome):
    w = chrome.run({"op": "status"})["windows"][0]
    chrome._state["hang"] = "set active tab index of w to 3"
    a = chrome.run({"op": "switch", "window_id": w["window_id"], "tab": 3, "expected": w["revision"]})
    assert a["verified"] is True and a["response_lost"] is True and a["current_tab"] == 3
    assert sum("set active tab index of w to 3" in s for s in chrome._state["calls"]) == 1, "재전송 없음"


def test_missing_window_or_tab_is_target_missing(chrome):
    with pytest.raises(chrome.Failure) as e:
        chrome.run({"op": "status", "window_id": 123})
    assert e.value.code == "TARGET_MISSING"
    w = chrome.run({"op": "status"})["windows"][0]
    with pytest.raises(chrome.Failure) as e:
        chrome.run({"op": "switch", "window_id": w["window_id"], "tab": 9, "expected": w["revision"]})
    assert e.value.code == "TARGET_MISSING"


def test_registered_with_same_contract_as_safari_and_guide_compiles():
    import yaml
    reg = yaml.safe_load((ROOT / "data/scripts/registry.yaml").read_text())
    entry = reg["Chrome제어"]
    assert entry["file"] == "chrome_control.py" and entry["callable_contract"] == reg["Safari제어"]["callable_contract"]
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_store import definitions
    text = (ROOT / "data/guides/chrome_control.md").read_text()
    blocks = re.findall(r"```ibl\n(.*?)```", text, re.S)
    assert blocks
    for code in blocks:
        plan = compile_program(code, load_registry(), definitions=definitions(), inputs={})
        assert not plan.issues, plan.report()


def test_real_catalog_binds_chrome_surface_without_shadowing_os_guide():
    import guide_registry as registry
    surfaces = registry.surface_control_guides()
    assert surfaces["app:com.google.chrome"] == "chrome_control.md"
    assert surfaces["app:com.apple.safari"] == "safari_control.md"
    assert registry.device_control_guides()["darwin"] == "pc_control.md"
    catalog = json.loads((ROOT / "data/guide_db.json").read_text())
    entry = next(g for g in catalog["guides"] if g["file"] == "chrome_control.md")
    assert "control_platforms" not in entry and entry["supported_platforms"] == ["darwin"]
    assert (ROOT / "data/guides" / entry["file"]).exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
