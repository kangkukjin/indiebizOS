"""제어 드라이버(CONTROL_DRIVER_DESIGN_2026_10_20) — 발견 경로·실행 전 검사·관측 원장·Safari 부품. 실기기 없음."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- §5.2 매핑 칸

def test_surface_mapping_is_data_requires_real_file_and_refuses_conflicts(tmp_path, monkeypatch):
    import guide_registry as registry
    monkeypatch.setattr(registry, "DATA_PATH", tmp_path)
    monkeypatch.setattr(registry, "GUIDES_DIR", tmp_path / "guides")
    (tmp_path / "guides").mkdir()
    for name in ("safari.md", "site.md", "dup_a.md", "dup_b.md", "os.md"):
        (tmp_path / "guides" / name).write_text("guide")
    (tmp_path / "guide_db.json").write_text(json.dumps({"guides": [
        {"file": "safari.md", "control_surfaces": ["App:com.apple.Safari"], "supported_platforms": ["Darwin"]},
        {"file": "site.md", "control_surfaces": ["site:Example.com"]},
        {"file": "dup_a.md", "control_surfaces": ["app:dup"]},
        {"file": "dup_b.md", "control_surfaces": ["app:dup"]},
        {"file": "missing.md", "control_surfaces": ["app:missing"]},
        {"file": "../out.md", "control_surfaces": ["app:unsafe"]},
        {"file": "os.md", "control_platforms": ["darwin"]},
    ]}))
    assert registry.surface_control_guides() == {"app:com.apple.safari": "safari.md", "site:example.com": "site.md"}
    assert registry.surface_control_entries()["app:com.apple.safari"]["supported_platforms"] == ["darwin"]
    # OS 대표 가이드 칸은 그대로 — 앱 가이드가 OS 가이드를 가리지 않는다.
    assert registry.device_control_guides() == {"darwin": "os.md"}
    assert registry.surface_control_guide("app", "com.apple.Safari")["control_guide"] == "safari.md"
    assert registry.surface_control_guide("site", "m.example.com")["surface"] == "site:example.com"
    assert registry.surface_control_guide("site", "example.org") is None
    assert registry.surface_control_guide("app", "") is None


def test_real_catalog_binds_safari_driver_without_shadowing_os_guides():
    import guide_registry as registry
    surfaces = registry.surface_control_guides()
    assert surfaces["app:com.apple.safari"] == "safari_control.md"
    assert registry.device_control_guides()["darwin"] == "pc_control.md"
    catalog = json.loads((ROOT / "data/guide_db.json").read_text())
    entry = next(g for g in catalog["guides"] if g["file"] == "safari_control.md")
    assert "control_platforms" not in entry and entry["supported_platforms"] == ["darwin"]


# ---------------------------------------------------------------- §6 실행 전 검사

@pytest.fixture
def origin(monkeypatch):
    import thread_context
    def set_origin(value):
        monkeypatch.setattr(thread_context, "get_task_origin", lambda: value)
    return set_origin


@pytest.mark.parametrize("value,available", [("user", True), ("training", True), ("test", True),
                                             ("scheduler", False), (None, False), ("member", False)])
def test_screen_context_follows_actor_origin(origin, value, available):
    import control_conditions
    origin(value)
    ctx = control_conditions.screen_context()
    assert ctx["available"] is available
    if not available:
        assert ctx["reason"]


def test_refusal_only_for_needs_front_in_unavailable_context():
    import control_conditions
    unavailable = {"available": False, "origin": "scheduler", "reason": "정기·배경 실행"}
    front = control_conditions.declare(needs_front=True, shared_state=True)
    assert control_conditions.refusal("click", front, unavailable)["error_code"] == "SCREEN_CONTEXT_UNAVAILABLE"
    assert control_conditions.refusal("click", front, {"available": True}) is None
    background = control_conditions.declare(needs_front=False, shared_state=True, isolated_resources=["screen"])
    assert control_conditions.refusal("open", background, unavailable) is None   # shared_state 는 요청된 효과면 실행
    with pytest.raises(ValueError):
        control_conditions.declare(needs_front=False, shared_state=False, isolated_resources=["wifi"])


@pytest.fixture
def screen(monkeypatch):
    mod = _load("control_driver_screen_handler", "data/packages/installed/tools/computer-use/handler.py")
    calls = []
    monkeypatch.setattr(mod, "_get_pyautogui", lambda: NS(click=lambda *a, **k: calls.append(("click", a)),
                                                            write=lambda *a, **k: calls.append(("write", a)),
                                                            press=lambda *a, **k: calls.append(("press", a)),
                                                            hotkey=lambda *a, **k: calls.append(("hotkey", a)),
                                                            size=lambda: (1280, 800), position=lambda: (1, 1)))
    monkeypatch.setattr(mod, "_capture_screenshot", lambda region=None: {"base64": "QUJD", "media_type": "image/png"})
    monkeypatch.setattr(mod, "_capture_png", lambda: "x.png")
    monkeypatch.setattr(mod, "_ocr_lines", lambda p: [])
    monkeypatch.setattr(mod, "_ax_elements", lambda pid: [])
    mod._calls = calls
    return mod


@pytest.mark.parametrize("op,params", [("click", {"x": 1, "y": 1}), ("type", {"text": "a"}), ("key", {"key": "enter"}),
                                       ("snapshot", {}), ("screenshot", {}), ("wait", {"expect_app": "Safari"})])
def test_scheduler_context_refuses_needs_front_ops_before_any_input(screen, origin, tmp_path, op, params):
    from tool_context import ToolContext
    origin("scheduler")
    out = json.loads(screen.execute({"op": op, **params}, ToolContext(str(tmp_path), "computer_op")))
    assert out["success"] is False and out["error_code"] == "SCREEN_CONTEXT_UNAVAILABLE"
    assert out["condition"]["needs_front"] is True and out["context"]["origin"] == "scheduler"
    assert screen._calls == []


def test_user_context_runs_and_background_safe_ops_are_never_refused(screen, origin, tmp_path):
    from tool_context import ToolContext
    origin("scheduler")
    info = json.loads(screen.execute({"op": "screen_info"}, ToolContext(str(tmp_path), "computer_op")))
    assert info["success"] and info["conditions"]["click"]["needs_front"] is True
    assert info["screen_context"]["available"] is False
    origin("user")
    out = json.loads(screen.execute({"op": "click", "x": 1, "y": 1, "screenshot_after": False},
                                    ToolContext(str(tmp_path), "computer_op")))
    assert out["success"] is True and screen._calls[0][0] == "click"


def test_snapshot_announces_driver_for_mapped_app(screen, origin, monkeypatch, tmp_path):
    from tool_context import ToolContext
    import guide_registry
    origin("user")
    monkeypatch.setattr(screen, "_frontmost_app", lambda: {"name": "Safari", "pid": 7, "bundle_id": "com.apple.Safari"})
    monkeypatch.setattr(guide_registry, "surface_control_guide",
                        lambda kind, ident: {"surface": "app:com.apple.safari", "control_guide": "safari_control.md",
                                             "supported_platforms": ["darwin"]} if ident == "com.apple.Safari" else None)
    out = json.loads(screen.execute({"op": "snapshot"}, ToolContext(str(tmp_path), "computer_op")))
    assert out["control_guide"] == "safari_control.md" and out["driver"]["surface"] == "app:com.apple.safari"
    assert "observations" in out["driver"]
    monkeypatch.setattr(screen, "_frontmost_app", lambda: {"name": "Other", "pid": 8, "bundle_id": "com.x.other"})
    out = json.loads(screen.execute({"op": "snapshot"}, ToolContext(str(tmp_path), "computer_op")))
    assert "control_guide" not in out


def test_browser_shared_state_reroutes_auto_and_refuses_explicit_chrome(origin, monkeypatch, tmp_path):
    """Chrome MCP 는 사용자의 탭을 그대로 쓴다 — 화면 없는 문맥의 공유 상태 변경은 부수 간섭(L48-1)."""
    import asyncio
    from tool_context import ToolContext
    mod = _load("control_driver_browser_handler", "data/packages/installed/tools/browser-action/handler.py")
    seen = {}
    async def fake_route(params, tool_name, owner, is_owner, chrome_connected):
        seen["chrome_connected"] = chrome_connected
        return ("chrome" if chrome_connected else "playwright"), None
    async def fake_owned(params, context, owner):
        seen["driver"] = params["driver"]
        return json.dumps({"success": True})
    monkeypatch.setattr(mod, "load_singleton", lambda *a: NS(route=fake_route))
    monkeypatch.setattr(mod, "_owned_execute", fake_owned)
    monkeypatch.setattr(mod, "_is_chrome_connected", lambda: True)
    ctx = ToolContext(str(tmp_path), "browser_op")
    unavailable = {"available": False, "origin": "scheduler", "reason": "정기·배경 실행"}
    # auto + 공유 상태 변경 → 간섭 없는 통로(Playwright)
    asyncio.run(mod._route_execute({"op": "navigate", "url": "https://x"}, ctx, "o", True, unavailable))
    assert seen["chrome_connected"] is False and seen["driver"] == "playwright"
    # 명시 chrome → 거절, 아무 통로도 타지 않음
    seen.clear()
    out = json.loads(asyncio.run(mod._route_execute({"op": "tab", "mode": "switch", "driver": "chrome"}, ctx, "o", True, unavailable)))
    assert out["success"] is False and out["error_code"] == "SCREEN_CONTEXT_UNAVAILABLE" and seen == {}
    # 읽기 동작은 Chrome 그대로
    asyncio.run(mod._route_execute({"op": "snapshot"}, ctx, "o", True, unavailable))
    assert seen["chrome_connected"] is True and seen["driver"] == "chrome"
    # 입회 문맥은 바꾸지 않는다
    seen.clear()
    asyncio.run(mod._route_execute({"op": "navigate", "url": "https://x"}, ctx, "o", True, {"available": True}))
    assert seen["chrome_connected"] is True and seen["driver"] == "chrome"


# ---------------------------------------------------------------- §3·§12① 관측 원장

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    import control_observations as obs
    monkeypatch.setattr(obs, "STORE_PATH", tmp_path / "control_observations.json")
    return obs


def _row(**over):
    base = {"observed_at": "2026-10-20T10:00", "version": "Safari 26.6", "environment": {"device": "__local__"},
            "fact": "숨은 Safari 첫 창 만들기 응답 20초 지연", "source": "test"}
    base.update(over)
    return base


def test_observation_rows_require_time_and_environment_and_are_never_deleted(ledger):
    with pytest.raises(ledger.ObservationError):
        ledger.record("app:com.apple.Safari", [_row(observed_at=None)])
    with pytest.raises(ledger.ObservationError):
        ledger.record("app:com.apple.Safari", [_row(environment={})])
    with pytest.raises(ledger.ObservationError):
        ledger.record("tv1", [_row()])          # 접두사 없는 식별자
    first = ledger.record("app:com.apple.Safari", [_row(observation_id="obs_1")])
    assert first["count"] == 1 and ledger.count("app:com.apple.safari") == 1
    # 정정: 상태만 바뀌고 fact·시각은 그대로. fact 를 바꾸는 정정은 거절(새 행 + supersedes).
    ledger.record("app:com.apple.Safari", [{"observation_id": "obs_1", "observed_at": "2026-10-20T10:00",
                                            "environment": {"device": "__local__"}, "fact": "숨은 Safari 첫 창 만들기 응답 20초 지연", "status": "recheck"}])
    assert ledger.rows("app:com.apple.Safari")[0]["status"] == "recheck"
    with pytest.raises(ledger.ObservationError):
        ledger.record("app:com.apple.Safari", [_row(observation_id="obs_1", fact="다른 사실")])
    # 대체: 새 행이 옛 ID 를 가리키면 옛 행은 superseded 로 남는다.
    ledger.record("app:com.apple.Safari", [_row(observation_id="obs_2", fact="두 번째 창부터는 0.5초", supersedes="obs_1")])
    rows = {r["observation_id"]: r for r in ledger.rows("app:com.apple.Safari")}
    assert rows["obs_1"]["status"] == "superseded" and rows["obs_2"]["status"] == "valid" and len(rows) == 2
    with pytest.raises(ledger.ObservationError):
        ledger.record("app:com.apple.Safari", [_row(supersedes="obs_none")])
    assert ledger.counts() == {"app:com.apple.safari": 2}


def test_applicable_marks_other_version_as_recheck_without_writing(ledger):
    ledger.record("site:example.com", [_row(observation_id="o1", version="unknown", environment={"site": "example.com", "account": "none"}),
                                       _row(observation_id="o2", version="v1", environment={"site": "example.com"}),
                                       _row(observation_id="o3", version="v1", status="refuted", environment={"site": "example.com"})])
    rows = ledger.applicable("site:example.com", version="v2")
    by = {r["observation_id"]: r for r in rows}
    assert by["o1"]["status"] == "valid"            # 판본 모름 = 시각·환경이 판본 자리
    assert by["o2"]["status"] == "recheck" and "recheck_reason" in by["o2"]
    assert "o3" not in by
    assert ledger.rows("site:example.com")[1]["status"] == "valid"   # 읽기는 쓰지 않는다


def test_device_observations_live_in_registration_record(ledger, monkeypatch):
    import limb_keys
    import hardware_registry
    store = {"registration": {"state": "active", "observations": []}}
    monkeypatch.setattr(limb_keys, "get_by_device", lambda d: store if d == "pc-1" else None)
    monkeypatch.setattr(hardware_registry, "contains", lambda t: False)
    monkeypatch.setattr(hardware_registry, "devices", lambda: [])
    written = {}
    monkeypatch.setattr(limb_keys, "resident_update", lambda d, **ch: written.update({d: ch}))
    out = ledger.record("device:pc-1", [_row(environment={"device": "pc-1"})])
    assert out["count"] == 1 and list(written) == ["pc-1"] and len(written["pc-1"]["observations"]) == 1
    assert not ledger.STORE_PATH.exists()        # 기기 행은 파일 원장에 남지 않는다
    with pytest.raises(ledger.ObservationError):
        ledger.record("device:nope", [_row()])
    # 본체는 등록 기록이 없어 파일 원장이 맡는다
    ledger.record("device:__local__", [_row()])
    assert ledger.count("device:__local__") == 1


def test_limb_register_with_observations_is_the_write_channel(ledger, monkeypatch):
    handler = _load("control_driver_limb_handler", "data/packages/installed/tools/guest-helper/handler.py")
    out = handler._OP_DISPATCHERS["limb_op"]["register"](
        {"op": "register", "target": "app:com.apple.Safari", "observations": [_row()]})
    assert out["success"] and out["count"] == 1 and out["observations"][0]["fact"].startswith("숨은 Safari")
    bad = handler._OP_DISPATCHERS["limb_op"]["register"]({"op": "register", "target": "app:x", "observations": [{"fact": "시각 없음"}]})
    assert bad["success"] is False and "observed_at" in bad["error"]
    missing = handler._OP_DISPATCHERS["limb_op"]["register"]({"op": "register", "observations": [_row()]})
    assert missing["success"] is False
    local = handler._OP_DISPATCHERS["limb_op"]["register"]({"op": "register", "target": "__local__", "observations": [_row()]})
    assert local["success"] and local["surface"] == "device:__local__"


def test_registration_stores_accept_observation_column(tmp_path, monkeypatch):
    import limb_keys
    with pytest.raises(ValueError):
        limb_keys.resident_update("x", observations="not-a-list")


# ---------------------------------------------------------------- 걸음 3 Safari 부품 (사전 호출 모의)

@pytest.fixture
def safari(monkeypatch):
    mod = _load("control_driver_safari", "data/scripts/safari_control.py")
    monkeypatch.setattr(mod.sys, "platform", "darwin")
    state = {"running": True, "windows": [[223970], ["about:blank"], [1]],
             "tabs": {223970: [[1], ["about:blank"], ["about:blank"]]}, "calls": [], "fail": None, "hang": None}

    def fmt(v):
        if isinstance(v, list):
            return "{" + ", ".join(fmt(x) for x in v) + "}"
        if isinstance(v, str):
            return json.dumps(v)
        return str(v)

    def fake_apple_event(script, timeout=10):
        state["calls"].append(script)
        hang = bool(state["hang"] and state["hang"] in script)   # 효과는 나고 응답만 유실되는 경우
        if hang:
            state["hang"] = None
        if state["fail"] and state["fail"][0] in script:
            code, msg = state["fail"][1], state["fail"][2]
            state["fail"] = None
            if code == -1743:
                raise mod.Failure("PERMISSION_REQUIRED", msg, os_error=code)
            raise mod.Failure("TARGET_MISSING", msg, os_error=code)
        if "is running" in script:
            return "true" if state["running"] else "false"
        if "of every window" in script:
            return fmt(state["windows"]) if state["windows"] else "{{}, {}, {}}"
        if "of every tab" in script:
            wid = int(script.split("window id ")[1].split(" ")[0])
            return fmt(state["tabs"][wid])
        if "make new tab" in script:
            wid = int(script.split("window id ")[1].split(" ")[0])
            url = script.split("URL:")[1].rstrip("}")
            t = state["tabs"][wid]
            n = len(t[0]) + 1
            t[0].append(n); t[1].append(json.loads(url)); t[2].append("new")
            if hang:
                raise subprocess.TimeoutExpired(script, timeout)
            return "tab %d of window id %d" % (n, wid)
        if "set current tab" in script:
            wid = int(script.split("window id ")[1].split(" ")[0]); n = int(script.rsplit("tab ", 1)[1])
            if not state.get("user_races"):
                state["windows"][2][state["windows"][0].index(wid)] = n
            if hang:
                raise subprocess.TimeoutExpired(script, timeout)
            return ""
        if "close tab" in script:
            wid = int(script.split("window id ")[1].split(" ")[0]); n = int(script.rsplit("tab ", 1)[1])
            t = state["tabs"][wid]; i = t[0].index(n)
            for col in t: col.pop(i)
            t[0][:] = list(range(1, len(t[0]) + 1))
            return ""
        raise AssertionError(script)
    monkeypatch.setattr(mod, "apple_event", fake_apple_event)
    mod._state = state
    return mod


def test_safari_contract_declares_conditions_and_refuses_bad_arguments(safari):
    c = safari.run({"op": "contract"})
    assert c["surface"] == "app:com.apple.Safari" and c["supported_platforms"] == ["darwin"]
    assert all({"needs_front", "shared_state", "isolated_resources", "verification_scope"} <= set(a) for a in c["actions"].values())
    assert c["actions"]["switch"]["shared_state"] is True and c["actions"]["open"]["needs_front"] is False
    for bad in ({"op": "open"}, {"op": "open", "url": "ftp://x"}, {"op": "open", "url": "https://u:p@x.com/"},
                {"op": "switch", "window_id": 1}, {"op": "close", "window_id": 1, "tab": 0}, {"op": "fly"},
                {"op": "status", "url": "https://x"}):
        with pytest.raises(safari.Failure) as e:
            safari.run(bad)
        assert e.value.code == "INVALID_ARGUMENT"
    assert safari._state["calls"] == []       # 검증 실패는 사전을 부르지 않는다


def test_safari_open_is_background_tab_and_verified_by_readback(safari):
    out = safari.run({"op": "open", "url": "https://example.com", "window_id": 223970})
    assert out["success"] and out["verified"] and out["verification_scope"] == "applescript_tab_readback"
    assert out["tab"] == 2 and out["current_tab"] == 1 and out["current_tab_unchanged"] is True
    assert out["window_created"] is False and out["condition"]["shared_state"] is False
    assert not any("activate" in c for c in safari._state["calls"])


def test_safari_switch_and_close_report_requested_shared_state_effects(safari):
    safari.run({"op": "open", "url": "https://example.com", "window_id": 223970})
    sw = safari.run({"op": "switch", "window_id": 223970, "tab": 2})
    assert sw["verified"] and sw["current_tab"] == 2 and sw["previous_tab"] == 1 and sw["condition"]["shared_state"] is True
    cl = safari.run({"op": "close", "window_id": 223970, "tab": 2})
    assert cl["verified"] and cl["closed_tab"]["url"] == "https://example.com" and cl["tab_count"] == 1
    last = safari.run({"op": "close", "window_id": 223970, "tab": 1})
    assert last["verified"] and last["tab_count"] == 0


def test_safari_target_missing_permission_and_lost_response(safari):
    # 대상 소실 — Safari 미실행은 실행 전 검사가 거절, launch 없이는 띄우지 않는다
    safari._state["running"] = False
    with pytest.raises(safari.Failure) as e:
        safari.run({"op": "open", "url": "https://example.com"})
    assert e.value.code == "TARGET_MISSING" and not any("make new" in c for c in safari._state["calls"])
    assert safari.run({"op": "status"})["running"] is False
    safari._state["running"] = True
    with pytest.raises(safari.Failure) as e:
        safari.run({"op": "switch", "window_id": 999, "tab": 1})
    assert e.value.code == "TARGET_MISSING"
    with pytest.raises(safari.Failure) as e:
        safari.run({"op": "close", "window_id": 223970, "tab": 9})
    assert e.value.code == "TARGET_MISSING"
    # 권한 부족 — 첫 사전 호출의 -1743
    safari._state["fail"] = ("of every window", -1743, "Not authorized")
    with pytest.raises(safari.Failure) as e:
        safari.run({"op": "status"})
    assert e.value.code == "PERMISSION_REQUIRED"
    # 응답 유실 — 효과는 났고 응답만 늦음 → 재조회로 verified, response_lost 표시, 재전송 0
    safari._state["hang"] = "make new tab"
    out = safari.run({"op": "open", "url": "https://late.example", "window_id": 223970})
    assert out["verified"] and out["response_lost"] is True
    assert sum("make new tab" in c for c in safari._state["calls"]) == 1
    # 응답 유실 + 효과 불명 → unknown 유지
    safari._state["hang"] = "set current tab"
    safari._state["user_races"] = True
    out = safari.run({"op": "switch", "window_id": 223970, "tab": 2})
    assert out["success"] is False and out["status"] == "unknown" and out["failure"]["code"] == "UNKNOWN"
    # 사용자 동시 조작 — 응답은 왔지만 현재 탭이 다름 → NOT_APPLIED, 자동 재시도 없음
    before = len(safari._state["calls"])
    out = safari.run({"op": "switch", "window_id": 223970, "tab": 2})
    assert out["success"] is False and out["failure"]["code"] == "NOT_APPLIED"
    assert sum("set current tab" in c for c in safari._state["calls"][before:]) == 1


def test_safari_refuses_other_platforms_before_any_call(safari, monkeypatch):
    monkeypatch.setattr(safari.sys, "platform", "win32")
    with pytest.raises(safari.Failure) as e:
        safari.run({"op": "status"})
    assert e.value.code == "UNSUPPORTED_PLATFORM" and safari._state["calls"] == []


def test_safari_script_registered_and_guide_examples_compile():
    import yaml
    reg = yaml.safe_load((ROOT / "data/scripts/registry.yaml").read_text())
    entry = reg["Safari제어"]
    assert entry["file"] == "safari_control.py" and entry["callable_contract"]["enums"]["op"] == ["contract", "status", "open", "switch", "close"]
    import re
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_store import definitions
    text = (ROOT / "data/guides/safari_control.md").read_text()
    blocks = re.findall(r"```ibl\n(.*?)```", text, re.S)
    assert blocks
    for code in blocks:
        plan = compile_program(code, load_registry(), definitions=definitions(), inputs={})
        assert not plan.issues, plan.report()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
