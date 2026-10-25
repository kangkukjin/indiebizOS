"""외부 런타임의 import 면제는 지정된 실행 파일에만 적용한다."""
from pathlib import Path

import pytest

import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("runtime_path", "module"), [
    ("backend/services/phone_native_control.py", "indiebiz_android"),
    ("data/packages/installed/tools/house-designer/render_blender.py", "bpy"),
    ("data/packages/installed/tools/house-designer/render_blender.py", "mathutils"),
])
@pytest.mark.parametrize("statement", ["import {module}", "from {module} import call"])
def test_external_runtime_exemption_is_file_scoped(
        tmp_path, monkeypatch, runtime_path, module, statement):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import check_import_coverage as audit

    runtime = tmp_path / runtime_path
    runtime.parent.mkdir(parents=True)
    runtime.write_text(statement.format(module=module) + "\nimport missing_dependency\n")
    desktop = tmp_path / "backend" / "desktop.py"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(statement.format(module=module) + "\n")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "SCAN_ROOTS", [tmp_path / "backend", tmp_path / "data"])
    monkeypatch.setattr(audit, "SCAN_FILES", [])

    imports = audit.collect_imports()
    assert imports[module] == ["backend/desktop.py:1"]
    assert imports["missing_dependency"] == [f"{runtime_path}:2"]
    assert module not in audit.ALLOW_MISSING


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
