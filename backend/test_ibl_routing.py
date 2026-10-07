"""Project target resolution preserves an explicit author's destination."""
import boot_paths  # noqa: F401
import pytest


@pytest.mark.parametrize('fallback', [None, '/caller-workspace'])
def test_unknown_explicit_id_does_not_use_another_project(fallback, monkeypatch):
    import ibl_routing
    monkeypatch.setattr(ibl_routing, '_resolve_project_id', lambda key: None)
    assert ibl_routing.resolve_project_path(
        fallback, {'project_id': 'missing', 'project_path': '/another-workspace'}) is None


def test_valid_id_wins_and_omitted_id_keeps_caller_path(monkeypatch):
    import ibl_routing
    monkeypatch.setattr(ibl_routing, '_resolve_project_id', lambda key: '/selected')
    assert ibl_routing.resolve_project_path('/caller', {'project_id': 'valid'}) == '/selected'
    assert ibl_routing.resolve_project_path('/caller', {}) == '/caller'


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
