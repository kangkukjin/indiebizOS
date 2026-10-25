"""Explicit project targets cannot silently fall back to another workspace."""
import asyncio

import boot_paths  # noqa: F401
import pytest


@pytest.mark.parametrize('extra', [
    {'continuation': {'reuse_args': {'reuse': {'run_id': 'previous'}}}},
    {'bogus_key': 1}, {'reues': {'run_id': 'previous'}},
])
def test_unknown_execute_keys_rejected_before_any_execution(monkeypatch, extra):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_ibl

    monkeypatch.setattr('system_tools._execute_ibl_unified',
                        lambda *a, **k: pytest.fail('invalid request executed'))
    app = FastAPI()
    app.include_router(api_ibl.router)
    with TestClient(app) as client:
        response = client.post('/ibl/execute', json={'code': 'return 1', **extra})
    assert response.status_code == 422
    errors = response.json()['detail']
    assert {e['loc'][-1] for e in errors if e['type'] == 'extra_forbidden'} == set(extra)


def test_reuse_args_merge_reaches_executor(tmp_path, monkeypatch):
    from api_ibl import IBLRequest, execute_ibl_code
    captured = []

    def execute(request, *args, **kwargs):
        captured.append(request)
        return {'success': True}

    monkeypatch.setattr('system_tools._execute_ibl_unified', execute)
    continuation = {'reuse_args': {'reuse': {'run_id': 'previous', 'models': False}}}
    request = {'code': 'return 1', 'project_path': str(tmp_path), **continuation['reuse_args']}
    assert asyncio.run(execute_ibl_code(IBLRequest(**request)))['success']
    assert captured[0]['reuse'] == {'run_id': 'previous', 'models': False}


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


def test_catalog_preserves_request_scope_in_worker(monkeypatch):
    import api_ibl
    import thread_context
    before = thread_context.snapshot()
    try:
        thread_context.set_allowed_nodes({'table'})
        monkeypatch.setattr(api_ibl, '_build_actions_catalog',
                            lambda: thread_context.get_allowed_nodes())
        assert asyncio.run(api_ibl.get_actions_catalog()) == {'table'}
        assert thread_context.get_allowed_nodes() == {'table'}
    finally:
        thread_context.restore(before)


def test_catalog_teaches_same_current_contract_as_describe():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_ibl
    from model_result_view import describe_actions
    app = FastAPI()
    app.include_router(api_ibl.router)
    with TestClient(app) as client:
        response = client.get('/ibl/actions/catalog')
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['total'] == sum(n['count'] for n in catalog['nodes'].values())
    names = ['table:filter', 'table:select', 'table:each', 'self:write', 'self:script']
    for row in describe_actions(names, {'table', 'self'}, edition=2)['actions']:
        node, action = row['action'].split(':')
        shown = catalog['nodes'][node]['actions'][action]
        current = row['definition']
        assert shown['callable_contract'] == current['callable_contract']
        if current.get('target_description'):
            assert shown['target_description'] == current['target_description']
        assert '$return' not in shown['target_description']
        assert '기본 20' not in shown['target_description']
        assert not shown['implementation']
        assert not shown['target_key'] or shown['target_key'] in current['callable_contract']['params']
        if 'op' in current['callable_contract']['params']:
            assert (shown['ops'] or {}).get('values', {}) == current['operations']
        else:
            assert shown['ops'] is None



def test_manual_learning_uses_recorded_current_call(monkeypatch):
    from api_ibl import DistillRequest, distill_ibl
    import ibl_continuations, ibl_usage_rag
    call = {'tool_name': 'execute_ibl', 'input': {'edition': 2, 'code': 'return 7'},
            'result': {'success': True, 'executed': True, 'source_complete': True, 'value': 7}}
    captured = []
    monkeypatch.setattr(ibl_continuations, 'completed_call', lambda ref, source: call if source == 'return 7' else None)
    monkeypatch.setattr(ibl_usage_rag, 'distill_experience', lambda intent, calls, score: captured.append(calls) or True)
    assert asyncio.run(distill_ibl(DistillRequest(intent='seven', code='return 7', task_ref={})))['distilled']
    assert captured == [[call]]
    assert not asyncio.run(distill_ibl(DistillRequest(intent='eight', code='return 8', task_ref={})))['distilled']
    assert len(captured) == 1


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
