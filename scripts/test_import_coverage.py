"""외부 런타임 예외가 일반 .venv 의존성 결손을 숨기지 않는지 검증."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_import_coverage", Path(__file__).with_name("check_import_coverage.py"))
coverage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coverage)


def test_blender_exemption_is_scoped_to_entrypoint(tmp_path, monkeypatch):
    renderer = tmp_path / "data/packages/installed/tools/house-designer/render_blender.py"
    renderer.parent.mkdir(parents=True)
    renderer.write_text("import bpy\nfrom mathutils import Vector\nimport ezdxf\n")
    desktop = tmp_path / "backend/consumer.py"
    desktop.parent.mkdir()
    desktop.write_text("from bpy import context\nimport mathutils\nimport ezdxf\n")
    monkeypatch.setattr(coverage, "ROOT", tmp_path)
    monkeypatch.setattr(coverage, "SCAN_ROOTS", [tmp_path])
    monkeypatch.setattr(coverage, "SCAN_FILES", [])

    found = coverage.collect_imports()

    assert found["bpy"] == ["backend/consumer.py:1"]
    assert found["mathutils"] == ["backend/consumer.py:2"]
    assert len(found["ezdxf"]) == 2
