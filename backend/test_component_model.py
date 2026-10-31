"""설치 부품 수리의 실제 모델 탐침. 원격 입력만 fixture, 사본·검사·Git·제한 자식은 실제.

INDIEBIZ_RUN_COMPONENT_MODEL=1 .venv/bin/python3 -m pytest backend/test_component_model.py -s
기본 회귀는 모델 호출을 건너뛴다. 수리 정답/파일 위치는 사용자 요청에 제공하지 않는다.
"""
import boot_paths  # noqa: F401
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_INPUT = {'response': {'results': [
    {'title': '도서관 운영 변경', 'description': '주말 개방', 'link': 'https://example.test/library'},
    {'title': '시장 소식', 'description': '장터 개장', 'link': 'https://example.test/market'}]},
    'type': 'news'}
REQUEST = ('이 검색원에서 지역 소식 두 건을 찾아 제목과 링크를 outputs/report.json에 저장하고 결과를 알려줘. '
           '보고서 저장 뒤에도 같은 검색원이 정상 조회되는지 다시 실행해서 확인해줘.')


def serve(repo):
    from contextlib import redirect_stdout
    from dataclasses import replace
    from mcp.server.fastmcp import FastMCP
    import component_runtime
    import runtime_utils
    import execution_turn
    import thread_context
    from ibl_v2_adapters import load_registry, decode_envelope, Adapted
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from test_repair_staging import _load_handler
    from tool_context import ToolContext

    with redirect_stdout(sys.stderr):
        catalog = load_registry(str(repo), 'component-probe')
        handler = _load_handler()
    handler._REPO_ROOT = repo
    runtime_utils.get_code_root = lambda: repo
    runtime_utils.get_source_root = lambda: repo
    runtime_utils.get_base_path = lambda: repo
    binding = execution_turn.Binding(SimpleNamespace(), 'component-probe', 'probe-task',
                                    context={}, conversation=None, component_repair_allowed=True,
                                    request=REQUEST)
    names = {'self:read': 'read_op', 'self:write': 'write_file', 'self:edit': 'edit_file',
             'self:patch': 'patch_op'}
    registry = {k: v for k, v in catalog.items() if k.startswith('table:')}

    def run_action(key, args):
        args = {**args, **catalog[key].contract['adapter'].get('fixed_params', {})}
        if key == 'sense:search':
            try:
                raw = {'success': True, 'items': component_runtime.call('web.naver_response', PROVIDER_INPUT)}
            except ValueError as exc:
                raw = {'success': False, 'error': str(exc)}
        else:
            if args.get('path'):
                target = Path(args['path'])
                target = target if target.is_absolute() else repo / target
                if not target.resolve().is_relative_to(repo):
                    raise PermissionError('시험 몸 밖의 파일 접근은 허용하지 않습니다')
            raw = handler.execute(args, ToolContext(tool_name=names[key], project_path=str(repo),
                                                    agent_id='component-probe'))
        value, evidence = decode_envelope(raw, catalog[key].contract['adapter'], args)
        return Adapted(value, evidence)

    for name in [*names, 'sense:search']:
        registry[name] = replace(catalog[name], run=lambda rt, args, name=name: run_action(name, args),
                                 authorize=None, dependency=None)
    mcp = FastMCP('indiebizos')

    @mcp.tool()
    def execute_ibl(code: str = '', describe: list[str] | None = None,
                    inputs: dict | None = None, check: bool = False,
                    read_result: dict | None = None) -> dict:
        """IBL 실행. describe로 실제 액션 계약을 조회하고 code/inputs로 실행한다."""
        token = execution_turn._current.set(binding)
        thread_context.set_current_agent_id('component-probe')
        thread_context.set_current_task_id('probe-task')
        thread_context.set_task_origin('user')
        try:
            with redirect_stdout(sys.stderr):
                from model_result_view import project_result, read_result as read_saved
                if read_result:
                    return read_saved(read_result)
                if describe:
                    return {'actions': {k: registry[k].contract for k in describe if k in registry}}
                plan = compile_program(code, registry, inputs or {})
                result = plan.report() if check or plan.issues else Runtime(plan, inputs or {}).run()
                with (repo / 'calls.jsonl').open('a') as f:
                    f.write(json.dumps({'code': code, 'result': result, 'pid': os.getpid()},
                                       ensure_ascii=False, default=str) + '\n')
                return project_result(result)
        finally:
            execution_turn._current.reset(token)
            thread_context.clear_all_context()

    mcp.run(transport='stdio')


@pytest.mark.system
@pytest.mark.skipif(os.environ.get('INDIEBIZ_RUN_COMPONENT_MODEL') != '1', reason='explicit real-model probe')
def test_model_repairs_installed_component_and_finishes_original_goal(tmp_path):
    import component_runtime
    from providers.claude_code import ClaudeCodeProvider
    from test_repair_staging import _make_repo
    repo = _make_repo(tmp_path / 'body')
    (repo / 'frontend').mkdir()
    (repo / 'frontend/.keep').write_text('')
    (repo / 'outputs').mkdir()
    spec = component_runtime.registry(ROOT)['web.naver_response']
    target = repo / spec['source']
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / spec['source'], target)
    shutil.copyfile(ROOT / Path(spec['source']).parent / 'runtime_components.json',
                    target.parent / 'runtime_components.json')
    (repo / '.gitignore').write_text('.worktrees/\ndata/system_ai_state/\ndata/restart_control/\n'
                                   'data/script_runs/\noutputs/\ncalls.jsonl\n')
    for args in [('config', 'user.name', 'Probe'), ('config', 'user.email', 'probe@example.test'),
                 ('add', '.'), ('commit', '-qm', 'fixture')]:
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True)
    original = target.read_bytes()
    output = ROOT / 'outputs/component-model-acceptance-2026-10-31' / f'run-{int(time.time())}'
    output.mkdir(parents=True)
    config = output / 'mcp.json'
    config.write_text(json.dumps({'mcpServers': {'indiebizos': {
        'command': sys.executable, 'args': [str(Path(__file__).resolve()), '--serve', str(repo)]}}}))
    request = REQUEST
    prompt = (ROOT / 'data/common_prompts/fragments/12_ibl_only.md').read_text()
    provider = ClaudeCodeProvider(api_key='', model='opus', system_prompt=prompt, project_path=str(repo),
                                  agent_name='component-probe', agent_id='component-probe')
    assert provider.init_client()
    command = [provider._binary_path, '--print', '--output-format', 'json', '--model', provider.model,
               '--permission-mode', 'bypassPermissions', '--setting-sources', '', '--tools', '',
               '--strict-mcp-config', '--mcp-config', str(config), '--allowed-tools',
               'mcp__indiebizos__execute_ibl', '--no-session-persistence', '--append-system-prompt', prompt]
    result = subprocess.run(command, input=request, text=True, cwd=repo, env=provider._build_env(),
                            capture_output=True, timeout=360)
    (output / 'model.json').write_text(result.stdout)
    (output / 'stderr.log').write_text(result.stderr)
    (output / 'request.txt').write_text(request)
    (output / 'fixture-path.txt').write_text(str(repo))
    if (repo / 'calls.jsonl').exists():
        shutil.copyfile(repo / 'calls.jsonl', output / 'calls.jsonl')
    assert result.returncode == 0, result.stderr[-1500:]
    report = json.loads((repo / 'outputs/report.json').read_text())
    assert 'https://example.test/library' in json.dumps(report)
    assert 'https://example.test/market' in json.dumps(report)
    assert target.read_bytes() != original, '업무 우회만 했으며 설치 부품은 수리하지 않음'
    sessions = list((repo / 'data/system_ai_state/repair_sessions').glob('*.json'))
    applied = [json.loads(p.read_text()) for p in sessions if not p.name.endswith('.apply.json')]
    assert any(s.get('status') == 'applied' and s.get('commit', {}).get('success') for s in applied)
    calls = [json.loads(line) for line in (repo / 'calls.jsonl').read_text().splitlines()]
    assert len({c['pid'] for c in calls}) == 1
    searches = [c['result'] for c in calls if '[sense:search]' in c['code']
                and c['result'].get('executed')]
    assert searches[0]['success'] is False and searches[-1]['success'] is True
    assert not any(c['result'].get('diagnostic', {}).get('code') == 'ADAPTER_SHAPE' for c in calls)
    assert (target.parent / 'runtime_components.json').read_bytes() == (
        ROOT / Path(spec['source']).parent / 'runtime_components.json').read_bytes()
    shutil.copyfile(repo / 'outputs/report.json', output / 'report.json')
    shutil.copyfile(target, output / 'repaired.py')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--serve':
        serve(Path(sys.argv[2]).resolve())
    else:
        raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
