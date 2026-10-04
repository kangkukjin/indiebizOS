"""scripts/select_tests.py — 변경 파일 → 전이 소비자 시험 선택기의 계약."""
import importlib.util
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def selector():
    spec = importlib.util.spec_from_file_location("select_tests", ROOT / "scripts/select_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tree(tmp_path: Path, files: dict) -> Path:
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body))
    return tmp_path


def test_transitive_consumers_and_direct_test_are_selected(tmp_path, selector):
    root = _tree(tmp_path, {
        "backend/leaf.py": "X = 1\n",
        "backend/datastore/mid.py": "from leaf import X\n",
        "backend/test_mid.py": "import mid\n",
        "backend/test_top.py": "from backend.datastore import mid\n",
        "backend/test_far.py": "import json\n",
        "backend/test_self.py": "import json\n",
    })
    r = selector.select(["backend/leaf.py", "backend/test_self.py"], root, threshold=0.9)
    assert r["selected"] == ["test_mid", "test_self", "test_top"]
    assert r["full"] is False and r["hubs"] == []


def test_hub_exceeding_threshold_falls_back_to_full_run(tmp_path, selector):
    root = _tree(tmp_path, {
        "backend/hub.py": "",
        **{f"backend/test_{i}.py": "import hub\n" for i in range(5)},
        "backend/test_other.py": "import json\n",
    })
    r = selector.select(["backend/hub.py"], root, threshold=0.4)
    assert r["full"] is True and r["hubs"] == ["hub"]


def test_string_path_reference_selects_gate_consumer(tmp_path, selector):
    root = _tree(tmp_path, {
        "backend/test_gate.py": "P = 'scripts/check_thing.py'\n",
        "backend/test_guide.py": "P = ROOT / 'data/guides/thing.md'\n",
        "backend/test_none.py": "import json\n",
    })
    r = selector.select(["scripts/check_thing.py", "data/guides/thing.md"], root, threshold=0.9)
    assert r["selected"] == ["test_gate", "test_guide"]
    assert r["path_hits"]["test_gate"] == ["scripts/check_thing.py"]


def test_cli_prints_pytest_args_and_refuses_empty_change(tmp_path, selector, capsys):
    root = _tree(tmp_path, {"backend/a.py": "", "backend/test_a.py": "import a\n", "backend/test_b.py": ""})
    assert selector.main(["--root", str(root), "--threshold", "0.9", "--files", "backend/a.py"]) == 0
    assert capsys.readouterr().out.strip() == "backend/test_a.py"
    assert selector.main(["--root", str(root), "--files"]) == 5


def test_live_repo_recent_commit_narrows_or_names_hubs(selector):
    """실 저장소: 선택은 전수보다 좁거나, 넓으면 허브를 이름 부른다(침묵 전수 금지)."""
    import subprocess
    rev = subprocess.run(["git", "log", "-1", "--format=%h"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    changed = subprocess.run(["git", "show", "--name-only", "--format=", "--diff-filter=ACMR", rev], cwd=ROOT, capture_output=True, text=True).stdout.split()
    r = selector.select(changed, ROOT)
    assert r["total"] > 100
    if r["full"]:
        assert r["hubs"], "전수로 번졌는데 허브를 못 짚음"
    else:
        assert len(r["selected"]) < r["total"]


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23 규약)
    import sys
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
