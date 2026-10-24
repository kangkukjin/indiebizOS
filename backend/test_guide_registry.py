"""Driver discovery briefs use current guide sections, not duplicated contracts."""
import json

import boot_paths  # noqa: F401
import guide_registry as guides
import pytest


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    directory = tmp_path / "guides"
    directory.mkdir()
    monkeypatch.setattr(guides, "DATA_PATH", tmp_path)
    monkeypatch.setattr(guides, "GUIDES_DIR", directory)

    def write(entries, files):
        (tmp_path / "guide_db.json").write_text(json.dumps({"guides": entries}))
        for name, content in files.items():
            (directory / name).write_text(content)
    return write


def test_briefs_are_opt_in_selected_deduplicated_and_live(catalog):
    entries = [{"file": "robot.md", "control_brief_section": "Call"},
               {"file": "other.md", "control_brief_section": "Call"},
               {"file": "plain.md"}]
    files = {"robot.md": "# Robot\n## Call\nDo & verify.\n## Details\nPRIVATE LONG DETAILS",
             "other.md": "## Call\nUnrelated driver", "plain.md": "## Call\nNot opted in"}
    catalog(entries, files)
    first = guides.device_control_briefs(["robot.md", "robot.md", "plain.md"])
    assert len(first) == 1 and first[0]["text"] == "## Call\nDo & verify."
    assert first[0]["section"] == "Call" and len(first[0]["content_hash"]) == 64
    files["robot.md"] = files["robot.md"].replace("Do & verify.", "New contract; verify.")
    catalog(entries, files)
    second = guides.device_control_briefs(["robot.md"])[0]
    assert "New contract" in second["text"]
    assert second["content_hash"] != first[0]["content_hash"]
    assert guides.device_control_briefs([]) == []


@pytest.mark.parametrize("content", [
    "## Different\nNo exact match", "## Call\nA\n## Call\nB",
    "## Call\n" + "x" * 1800,
])
def test_invalid_or_oversize_brief_is_omitted_whole(catalog, content):
    catalog([{"file": "robot.md", "control_brief_section": "Call"}], {"robot.md": content})
    assert guides.device_control_briefs(["robot.md"]) == []


def test_briefs_refuse_catalog_conflicts_and_unsafe_paths(catalog):
    catalog([{"file": "robot.md", "control_brief_section": "Call"}] * 2 + [
        {"file": "../outside.md", "control_brief_section": "Call"},
        {"file": "missing.md", "control_brief_section": "Call"}],
        {"robot.md": "## Call\nDo & verify."})
    assert guides.device_control_briefs(["robot.md", "../outside.md", "missing.md"]) == []


def test_briefs_bound_total_without_cutting_a_contract(catalog):
    files = {f"{i}.md": "## Call\n" + "x" * 1490 for i in range(4)}
    catalog([{"file": name, "control_brief_section": "Call"} for name in files], files)
    result = guides.device_control_briefs(files)
    assert len(result) == 2
    assert all(b["text"] == files[b["file"]] for b in result)


def test_published_android_brief_fits_budget_and_compiles_call_examples():
    import re
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_store import installed_definitions
    briefs = guides.device_control_briefs(["android_control.md"])
    assert len(briefs) == 1
    calls = re.findall(r'`(\[(?:fn|limbs):[^`]+)`', briefs[0]["text"])
    assert len(calls) >= 3
    for call in calls:
        plan = compile_program("#!ibl edition=2\nreturn " + call,
                               load_registry(str(guides.DATA_PATH.parent)),
                               inputs={"폰": "selected-device", "원결과": {}},
                               definitions=installed_definitions())
        assert not plan.issues, plan.report()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
