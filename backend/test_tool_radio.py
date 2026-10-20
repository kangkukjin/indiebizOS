"""라디오 앱의 즐겨찾기 행 → 재생 인자 계약."""
import boot_paths  # noqa: F401

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


ROOT = Path(__file__).resolve().parents[1]


def test_phone_radio_cannot_control_or_report_replacement_music(monkeypatch):
    import json
    from types import SimpleNamespace
    from common.pkg_utils import load_sibling
    radio = load_sibling(str(ROOT / 'data/packages/installed/tools/radio/handler.py'), 'tool_radio')
    monkeypatch.setenv('INDIEBIZ_PROFILE', 'phone')
    monkeypatch.setattr(radio, '_current_station', {'name': 'Radio', 'playback_id': 'old-radio'})
    calls = []
    def stop(pid):
        calls.append(pid)
        return json.dumps({'stopped': False})
    native = SimpleNamespace(
        streamStatus=lambda: json.dumps({'playing': True, 'playback_id': 'new-music'}),
        stopStreamIf=stop,
        setStreamVolumeIf=lambda pid, vol: json.dumps({'error': '재생 대상이 바뀌었습니다'}))
    monkeypatch.setattr(radio, '_phone_bridge', lambda: native)
    assert not json.loads(radio.radio_status())['playing']
    assert not json.loads(radio.set_radio_volume(20))['success']
    assert json.loads(radio.stop_radio())['success']
    assert calls == ['old-radio']


@pytest.mark.parametrize("row,expected", [
    ({"station_id": None, "stream_url": "https://example.test/live"},
     {"op": "play", "stream_url": "https://example.test/live"}),
    ({"station_id": "kbs_coolfm", "stream_url": None},
     {"op": "play", "station_id": "kbs_coolfm"}),
    ({"station_id": "kbs_coolfm", "stream_url": "https://example.test/old"},
     {"op": "play", "station_id": "kbs_coolfm"}),
])
def test_favorite_play_uses_only_available_identifier(row, expected):
    declaration = yaml.safe_load((ROOT / "data/packages/installed/tools/radio/ibl_actions.yaml").read_text())
    app = declaration["nodes"]["limbs"]["actions"]["radio"]["app"]
    favorites = next(mode for mode in app["modes"] if mode["name"] == "즐겨찾기")
    code = favorites["view"][0]["button"]["action"]
    registry = load_registry()
    calls = []

    def play(runtime, args, **kwargs):
        calls.append(args)
        return {"success": True}

    registry["limbs:radio"] = replace(registry["limbs:radio"], run=play, authorize=None)
    inputs = {"item": row}
    plan = compile_program(code, registry, inputs=inputs, declared_inputs=["item"])
    assert plan.report()["status"] != "invalid", plan.report()
    result = Runtime(plan, inputs=inputs).run()
    assert result["success"], result
    assert calls == [expected]


def test_stations_does_not_claim_unsupported_country(monkeypatch):
    from types import SimpleNamespace
    from common.pkg_utils import load_sibling
    h = load_sibling(str(ROOT/'data/packages/installed/tools/radio/tool_radio.py'), 'handler')
    calls = []
    monkeypatch.setattr(h, 'load_tool_radio', lambda: SimpleNamespace(get_korean_radio=lambda **kw: calls.append(kw) or {'items': []}))
    ctx = SimpleNamespace(tool_name='radio_op')
    assert not h.execute({'op':'stations','country':'US'},ctx)['success']
    assert calls == []
    assert h.execute({'op':'stations','country':'KR','broadcaster':'KBS'},ctx) == {'items':[]}
    assert calls == [{'broadcaster':'KBS'}]


def test_favorite_op_reaches_existing_store(monkeypatch):
    from types import SimpleNamespace
    from common.pkg_utils import load_sibling
    h = load_sibling(str(ROOT/'data/packages/installed/tools/radio/tool_radio.py'), 'handler')
    calls = []
    monkeypatch.setattr(h, 'load_tool_radio', lambda: SimpleNamespace(save_radio_favorite=lambda **kw: calls.append(kw) or {'success':True}))
    assert h.execute({'op':'favorite_add','station_id':'kbs_coolfm'}, SimpleNamespace(tool_name='radio_op'))['success']
    assert calls == [{'station_id':'kbs_coolfm','name':None,'stream_url':None}]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
