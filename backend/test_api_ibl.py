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


@pytest.mark.parametrize('raises', [False, True])
def test_agent_reentry_restores_project_owner_on_reused_worker(tmp_path, monkeypatch, raises):
    # 실제 풀 스레드에 이전 신원을 남긴 뒤 MCP 경로 → 프로젝트 밖 경로를 연속 호출한다.
    import unicodedata
    from concurrent.futures import ThreadPoolExecutor
    from fastapi import HTTPException
    from api_ibl import IBLRequest, execute_ibl_code
    from red_report import current_owner
    from thread_context import get_current_project_id, set_current_project_id

    seen = []

    def execute(*args, **kwargs):
        seen.append(current_owner())
        if raises:
            raise ValueError('execution failed')
        return {'success': True}

    monkeypatch.setattr('system_tools._execute_ibl_unified', execute)
    project = tmp_path / 'projects' / unicodedata.normalize('NFD', '하드웨어')
    project.mkdir(parents=True)

    async def run():
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
        await asyncio.to_thread(set_current_project_id, '앱모드')
        for path in (project, tmp_path / 'data'):
            req = IBLRequest(code='return 1', edition=2, project_path=str(path), agent_id='agent_001')
            if raises:
                with pytest.raises(HTTPException):
                    await execute_ibl_code(req)
            else:
                assert (await execute_ibl_code(req))['success']
            assert await asyncio.to_thread(get_current_project_id) == '앱모드'

    asyncio.run(run())
    assert seen == ['하드웨어:agent_001', 'agent_001']


@pytest.mark.parametrize('explicit', [False, True])
def test_project_reentry_passes_own_repair_gate_but_rejects_other_owner(tmp_path, monkeypatch, explicit):
    import unicodedata
    from types import SimpleNamespace
    from api_ibl import IBLRequest, execute_ibl_code
    from project_manager import ProjectManager
    from repair_policy import VERSION, prepare

    project = tmp_path / 'projects' / '하드웨어'
    project.mkdir(parents=True)
    monkeypatch.setattr(ProjectManager, 'get_project_path', lambda self, name: project)
    controller = SimpleNamespace(cancelled=lambda: False,
                                 _final_criteria_contract={'criteria': [{'id': 'C1'}]})

    def execute(*args, **kwargs):
        # 빈 검사 계획에서 멈추므로 실제 파일 쓰기 없이 소유자 관문을 확인한다.
        own = prepare(controller, str(tmp_path),
                      {'owner': '하드웨어:agent_001', 'repair_policy': VERSION}, None, None)
        other = prepare(controller, str(tmp_path),
                        {'owner': '다른프로젝트:agent_001', 'repair_policy': VERSION}, None, None)
        assert own['stage'] == 'plan'
        assert other['stage'] == 'ownership'
        return {'success': True}

    monkeypatch.setattr('system_tools._execute_ibl_unified', execute)
    req = IBLRequest(code='return 1', edition=2, agent_id='agent_001',
                     project_path=str(project),
                     project_id=unicodedata.normalize('NFD', '하드웨어') if explicit else None)
    assert asyncio.run(execute_ibl_code(req))['success']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
