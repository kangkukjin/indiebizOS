"""Schema audit follows active focus consumers, including non-executor paths."""
import importlib.util
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('consciousness_schema_check', ROOT / 'scripts/consciousness_schema_check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


@pytest.mark.parametrize('source', [
    'def render_for_executor(env):\n out = project_framing(env["output"])\n cf = out.get("capability_focus") or {}\n return cf.get("highlight_actions")',
    'def tool_context(controller):\n return ((controller.framing or {}).get("capability_focus") or {}).get("highlight_actions", [])',
    'def _validate_member_framing(value):\n for key in ("capability_focus", "ibl_focus"):\n  focus = value.get(key)\n  actions = focus.get("highlight_actions")',
    'def use(framing):\n co = project_framing(framing)\n alias = co\n return alias["capability_focus"]["highlight_actions"]',
])
def test_focus_drift_is_detected_in_all_entry_shapes(tmp_path, source):
    path = tmp_path / 'consumer.py'
    path.write_text(source)
    _, reads = check.scan_consumer(path)
    assert any(key == 'highlight_actions' for key, _ in reads)
    assert 'highlight_actions' not in check.load_producer_schema()[1]


def test_current_consumers_are_covered_and_match_the_producer():
    assert {p.name for p in check.CONSUMER_FILES} >= {
        'reframe.py', 'supervisor_runtime.py', 'member_runner.py', 'framing_inheritance.py', 'consciousness_agent.py'}
    assert check.load_producer_schema()[1] == {'hint'}
    assert check.main() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
