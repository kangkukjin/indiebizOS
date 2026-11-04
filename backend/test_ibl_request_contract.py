"""Public values survive MCP and HTTP forwarding without carrying actor authority."""
import asyncio
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from ibl_request_contract import EXECUTION_OPTION_FIELDS, project_execution_options

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OPTIONS = {
    'code': 'return $x', 'edition': 2, 'composition': 'boundary-probe',
    'completion': [{'id': 'c'}], 'repair': {'mode': 'inspect'},
    'function_refs': [{'id': 'f'}], 'value_protocols': ['v'],
    'inputs': {'x': {'flag': False, 'optional': None}}, 'check': True,
    'code_edits': [{'old': 'x', 'new': 'y'}], 'resume': {'run_id': 'resume'},
    'reuse': {'run_id': 'reuse', 'models': False}, 'budget': {'steps': 7},
    'describe': ['self:time'], 'read_result': {'id': 'probe', 'offset': 2, 'limit': 17},
}


def test_public_contract_matches_published_schema():
    from tool_loader import build_execute_ibl_tool
    assert set(EXECUTION_OPTION_FIELDS) == set(build_execute_ibl_tool()['input_schema']['properties'])


def test_projection_retains_values_without_surface_authority():
    original = {**OPTIONS, 'approval': 'private', 'agent_id': 'owner', 'ticket': 'private',
                'origin': 'user', 'completion_channel': 'private', 'declared_inputs': ['x']}
    before = json.dumps(original, sort_keys=True)
    assert project_execution_options(original) == OPTIONS
    assert json.dumps(original, sort_keys=True) == before
    assert project_execution_options({'code': '', 'check': False, 'inputs': {},
                                      'resume': {}, 'describe': [], 'edition': None}) == {
                                          'code': '', 'inputs': {}, 'resume': {}, 'describe': []}


@pytest.mark.parametrize('option', list(OPTIONS) + ['all', 'empty'])
def test_mcp_and_http_values_reach_common_executor(tmp_path, monkeypatch, option):
    import mcp_server as mcp
    import api_ibl
    import system_tools
    from mcp.server.fastmcp.utilities.func_metadata import func_metadata
    for name in ('AGENT_ID', 'TASK_ID', 'TASK_ORIGIN', 'EPISODE_ID', 'PARENT_RUN_ID'):
        monkeypatch.setattr(mcp, 'DEFAULT_' + name, '')
    monkeypatch.setattr(api_ibl, '_attach_steer', lambda value, *a: value)
    supplied = (dict(OPTIONS) if option == 'all' else
                {'code': '', 'inputs': {}, 'resume': {}, 'reuse': {}, 'describe': [], 'check': False}
                if option == 'empty' else {'code': 'return 1', option: OPTIONS[option]})
    seen = []
    monkeypatch.setattr(system_tools, '_execute_ibl_unified',
                        lambda request, *a, **kw: seen.append(request) or {'success': True})

    def post(path, payload, timeout):
        assert path == '/ibl/execute'
        req = api_ibl.IBLRequest(**{**payload, 'ticket': None})
        return json.dumps(asyncio.run(api_ibl.execute_ibl_code(req)))

    monkeypatch.setattr(mcp, '_post_backend', post)
    # Actual FastMCP argument validation, then MCP payload and actual HTTP worker.
    model = func_metadata(mcp.execute_ibl, skip_names=['ctx']).arg_model
    args = model.model_validate({**supplied, 'project_path': str(tmp_path)})
    asyncio.run(mcp.execute_ibl(**args.model_dump()))
    expected = {k: v for k, v in supplied.items() if k != 'check' or v}
    if 'edition' not in expected:
        expected['edition'] = 2
    assert seen == [expected]
    seen.clear()
    asyncio.run(api_ibl.execute_ibl_code(api_ibl.IBLRequest(
        **supplied, project_path=str(tmp_path), declared_inputs=['x'], approval='approval-probe')))
    rest_expected = {k: v for k, v in supplied.items() if k != 'check' or v}
    assert seen == [{**rest_expected, 'declared_inputs': ['x']}]


@pytest.mark.parametrize('code', ['#!ibl edition=2\nreturn 1', '$checked:probe', '$rejected:probe', ''])
def test_authoring_boundary_is_preserved(monkeypatch, tmp_path, code):
    import mcp_server as mcp
    from api_ibl import IBLRequest
    seen = []
    monkeypatch.setattr(mcp, '_post_backend', lambda path, payload, timeout:
                        seen.append(IBLRequest(**payload)) or json.dumps({'success': True}))
    asyncio.run(mcp.execute_ibl(code, project_path=str(tmp_path), check=False))
    assert seen[0].code == code
    assert seen[0].edition == (None if code.startswith('#!ibl') else 2)
    assert IBLRequest(code=code).edition is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
