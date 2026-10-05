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
    app = declaration["nodes"]["sense"]["actions"]["radio"]["app"]
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
