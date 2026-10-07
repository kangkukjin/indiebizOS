"""Explicit project targets cannot silently fall back to another workspace."""
import asyncio

import boot_paths  # noqa: F401
import pytest


@pytest.mark.parametrize('check', [False, True])
def test_unknown_explicit_project_rejected_before_execution(tmp_path, monkeypatch, check):
    from api_ibl import IBLRequest, execute_ibl_code
    from project_manager import ProjectManager
    monkeypatch.setattr(ProjectManager, 'get_project_path', lambda self, name: tmp_path / name)
    monkeypatch.setattr('system_tools._execute_ibl_unified',
                        lambda *a, **k: pytest.fail('wrong workspace executed'))
    req = IBLRequest(code='return 1', edition=2, project_id='missing-project',
                     project_path=str(tmp_path), check=check)
    result = asyncio.run(execute_ibl_code(req))
    assert not result['success'] and not result['executed']
    assert result['diagnostic']['code'] == 'PROJECT_NOT_FOUND'
    assert result['diagnostic']['details']['project_id'] == 'missing-project'


def test_system_project_is_provisioned_and_valid_project_wins(tmp_path, monkeypatch):
    from api_ibl import IBLRequest, execute_ibl_code
    from project_manager import ProjectManager
    monkeypatch.setattr(ProjectManager, 'get_project_path', lambda self, name: tmp_path / name)
    called = []
    def execute(*args, **kwargs):
        called.append((args, kwargs))
        return {'success': True, 'items': []}
    monkeypatch.setattr('system_tools._execute_ibl_unified', execute)
    req = IBLRequest(code='return 1', edition=2, project_id='수동모드',
                     project_path=str(tmp_path / 'other'))
    assert asyncio.run(execute_ibl_code(req))['success']
    assert (tmp_path / '수동모드').is_dir()
    assert str(tmp_path / '수동모드') in str(called)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
