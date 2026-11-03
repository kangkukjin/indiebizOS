"""경로에서 파생한 층 소속과 모든 정책 소비자의 계약."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('checked_layers', Path(__file__).resolve().parents[1] / 'scripts/check_backend_layers.py')
layers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layers)


def test_layer_guard_synthetic_and_actual_graph():
    assert layers.self_test() == 0


@pytest.mark.parametrize('relative', ['wrong/new.py', 'ibl/nested/new.py', 'new.py', 'base/api.py', 'ibl/test_wrong.py'])
def test_wrong_locations_are_errors(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('')
    assert layers.misplaced_modules(str(tmp_path))


def test_private_guard_derives_new_language_modules_and_checks_packages(tmp_path):
    backend = tmp_path / 'backend'
    (backend / 'ibl').mkdir(parents=True)
    (backend / 'ibl/newly_added.py').write_text('')
    tools = tmp_path / 'data/packages/installed/tools/a'
    tools.mkdir(parents=True)
    (tools / 'handler.py').write_text('from newly_added import _secret')
    found = layers.private_symbol_leaks(str(backend))
    assert len(found) == 1 and 'newly_added' in found[0]
    (tools / 'handler.py').write_text('def ???')
    with pytest.raises(ValueError, match='handler.py'):
        layers.private_symbol_leaks(str(backend))


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
