"""표면 언어 개정(2026-10-05): engine 뷰 + selection/saved 뷰-이벤트 검증기 회귀.

docs/APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md §3-c. engine 은 ref(작업 공간 자료) 필수, on 은 map/engine 전용이며
이벤트 집합이 뷰별로 갈린다. 두 렌더러(데스크탑·원격)가 engine 을 디스패치하는지는 빌드의 뷰-렌더러 가드가 본다.
"""
import importlib.util
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _appview():
    spec = importlib.util.spec_from_file_location("iblbuild_appview", ROOT / "scripts/iblbuild_appview.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    spec.loader.exec_module(module)
    return module


QUALIFIED = {"self:workspace", "table:ai", "self:read"}


def _block(view, action='[self:workspace]{op:"open", path:$path}'):
    # edition 2(2026-10-05 표면 바인딩 ①): 템플릿은 치환 없는 판본 2 원문 — $path·$resource·$dock 은 따옴표 없이 값 참조
    return {"edition": 2, "inputs": [{"key": "path", "type": "text"}], "action": action, "view": view}


def test_engine_declares_vocabulary_and_events():
    av = _appview()
    assert "engine" in av.APP_VIEW_TYPES
    assert {"selection", "saved"} <= av.APP_VIEW_EVENTS
    assert {"sel", "resource", "revision", "start", "end", "text", "sheet", "range"} <= av.APP_EVENT_VARS
    assert av.APP_ENGINE_EVENTS == {"selection", "saved"} and "selection" not in av.APP_MAP_EVENTS


def test_engine_block_with_selection_and_saved_is_valid():
    av = _appview()
    view = [{"type": "engine", "ref": "{data.resource}",
             "on": {"selection": "keep", "saved": '[self:workspace]{op:"versions", resource:$resource}'}},
            {"type": "form", "fields": [{"key": "지시", "type": "textarea",
                                        "ai_dock": {"action": '[fn:선택교정]{자료:$resource, 선택:$sel, 지시:$dock}'}}],
             "action": '[self:workspace]{op:"capabilities", resource:$resource}'}]
    issues = av._validate_app_block("t", _block(view), QUALIFIED)
    assert issues == [], issues


def test_engine_canvas_dock_is_valid_and_checked():
    """engine 뷰의 ai_dock(2026-10-05 문서 앱): 선택 페이로드와 $dock 을 받는 템플릿이 통과하고, 스키마는 form 독과 같은 검사를 받는다."""
    av = _appview()
    dock = {"action": '[fn:선택교정]{자료:$resource, 선택:$sel, 지시:$dock}', "modes": ["replace"]}
    ok = av._validate_app_block("t", _block([{"type": "engine", "ref": "{data.resource}", "ai_dock": dock}]), QUALIFIED)
    assert ok == [], ok
    no_action = av._validate_app_block("t", _block([{"type": "engine", "ref": "{data.resource}", "ai_dock": {}}]), QUALIFIED)
    assert any("ai_dock.action" in i for i in no_action), no_action
    elsewhere = av._validate_app_block("t", _block([{"type": "blocks", "from": "items", "ai_dock": dock}]), QUALIFIED)
    assert any("engine 뷰 또는 form" in i for i in elsewhere), elsewhere
    desktop = (ROOT / "frontend/src/components/generic/prims-engine.tsx").read_text(encoding="utf-8")
    assert "AiDockPanel" in desktop and "p.ai_dock" in desktop


def test_engine_requires_ref_and_rejects_foreign_events():
    av = _appview()
    missing = av._validate_app_block("t", _block([{"type": "engine"}]), QUALIFIED)
    assert any("ref" in i for i in missing), missing
    wrong = av._validate_app_block("t", _block([{"type": "engine", "ref": "{data.resource}", "on": {"moveend": "[self:read]{}"}}]), QUALIFIED)
    assert any("engine 뷰의 이벤트가 아니다" in i for i in wrong), wrong
    map_sel = av._validate_app_block("t", _block([{"type": "map", "from": "map_data", "on": {"selection": "keep"}}]), QUALIFIED)
    assert any("map 뷰의 이벤트가 아니다" in i for i in map_sel), map_sel
    blocks_on = av._validate_app_block("t", _block([{"type": "blocks", "from": "items", "on": {"selection": "keep"}}]), QUALIFIED)
    assert any("map/engine 전용" in i for i in blocks_on), blocks_on


def test_both_renderers_dispatch_engine():
    desktop = (ROOT / "frontend/src/components/GenericInstrument.tsx").read_text(encoding="utf-8")
    remote = (ROOT / "backend/surface/launcher_web_render.py").read_text(encoding="utf-8")
    assert "p.type === 'engine'" in desktop and "p.type==='engine'" in remote
    assert (ROOT / "frontend/src/components/generic/prims-engine.tsx").is_file()
    for doc in ("data/system_docs/ibl.md", "data/guides/new_action_checklist.md"):
        assert "view 프리미티브 16종" in (ROOT / doc).read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
