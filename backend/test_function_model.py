"""실제 실행 모델이 저장 정의를 진단·개정·재호출하는 선택적 인수 검사.

INDIEBIZ_RUN_FUNCTION_MODEL=1 pytest backend/test_function_model.py -s
운영 정의나 외부 기기는 사용하지 않는다. 관리·컴파일·실행·판본 검사는 실제다.
"""
import boot_paths  # noqa: F401
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
BROKEN = '#!ibl edition=2\n[def:작업번호]($작업){return $작업.task_ref.task_id}'
REQUEST = ('등록된 작업번호 관용구는 접수증 {task_ref:{kind:"guestpc",task_id:"receipt-1"}}에서는 '
           '번호를 돌려주지만 작업 참조 {kind:"guestpc",task_id:"bare-2"}에서는 실패해. '
           '두 입력 모두 작업 번호를 반환하도록 관용구를 고쳐줘. 저장된 관용구를 다시 호출해 '
           '두 경우를 확인하고 결과를 알려줘.')


def serve(repo):
    from contextlib import redirect_stdout
    from dataclasses import replace
    from mcp.server.fastmcp import FastMCP
    import function_store
    from function_library import register, definitions
    from ibl_v2_adapters import load_registry, decode_envelope, Adapted
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import repair_workspace_scope
    from workflow_engine import execute_workflow_action

    (repo / 'data').mkdir(exist_ok=True)
    (repo / 'data/vocabulary_policy.yaml').write_bytes((ROOT / 'data/vocabulary_policy.yaml').read_bytes())
    os.environ['INDIEBIZ_CODE_ROOT'] = str(ROOT)
    os.environ['INDIEBIZ_SOURCE_ROOT'] = str(repo)
    os.environ['INDIEBIZ_BASE_PATH'] = str(repo)
    os.environ['INDIEBIZ_RUNTIME_STATE_DIR'] = str(repo / 'runtime')
    with redirect_stdout(sys.stderr):
        register('작업번호', BROKEN)
        catalog = load_registry(str(repo))
    registry = {k: v for k, v in catalog.items() if k.startswith('table:')}

    def workflow(rt, args):
        raw = execute_workflow_action('workflow', args, str(repo))
        value, evidence = decode_envelope(raw, catalog['self:workflow'].contract['adapter'], args)
        return Adapted(value, evidence)

    registry['self:workflow'] = replace(catalog['self:workflow'], run=workflow,
                                       authorize=None, dependency=None)
    before = compile_program('[fn:작업번호]{작업:{kind:"guestpc",task_id:"before"}}',
                             registry, definitions=definitions())
    baseline = {'valid': not bool(before.issues),
                'result': before.report() if before.issues else Runtime(before, {}).run(),
                'function_ref': function_store.reference(function_store.resolve('작업번호'))}
    (repo / 'baseline.json').write_text(json.dumps(baseline, ensure_ascii=False, default=str))
    mcp = FastMCP('indiebizos')

    @mcp.tool()
    def execute_ibl(code: str = '', describe: list[str] | None = None,
                    inputs: dict | None = None, check: bool = False) -> dict:
        """IBL 실행. describe로 액션 계약을 조회하고 code/inputs로 실행한다."""
        with redirect_stdout(sys.stderr), repair_workspace_scope(str(repo / 'candidate')):
            if describe:
                return {'actions': {k: registry[k].contract for k in describe if k in registry}}
            plan = compile_program(code, registry, inputs or {}, definitions=definitions())
            result = plan.report() if check or plan.issues else Runtime(plan, inputs or {}).run()
            with (repo / 'calls.jsonl').open('a') as f:
                f.write(json.dumps({'code': code, 'result': result, 'pid': os.getpid()},
                                   ensure_ascii=False, default=str) + '\n')
            # Inspect the actual published definition, not an executor's success claim.
            (repo / 'published.json').write_text(json.dumps(function_store.resolve('작업번호'),
                                                           ensure_ascii=False))
            return result

    mcp.run(transport='stdio')


@pytest.mark.system
@pytest.mark.skipif(os.environ.get('INDIEBIZ_RUN_FUNCTION_MODEL') != '1', reason='explicit real-model probe')
def test_model_revises_definition_and_verifies_both_inputs(tmp_path, monkeypatch):
    from providers.claude_code import ClaudeCodeProvider
    import function_store
    from ibl_v2_entry import handle_request
    repo = tmp_path / 'body'
    repo.mkdir()
    output = ROOT / 'outputs/function-model-acceptance-2026-10-31' / f'run-{int(time.time())}'
    output.mkdir(parents=True)
    config = output / 'mcp.json'
    config.write_text(json.dumps({'mcpServers': {'indiebizos': {
        'command': sys.executable, 'args': [str(Path(__file__).resolve()), '--serve', str(repo)]}}}))
    prompt = (ROOT / 'data/common_prompts/fragments/12_ibl_only.md').read_text()
    prompt += '\n' + (ROOT / 'data/common_prompts/fragments/13_repair.md').read_text()
    provider = ClaudeCodeProvider(api_key='', model='opus', system_prompt=prompt, project_path=str(repo),
                                  agent_name='function-probe', agent_id='function-probe')
    assert provider.init_client()
    command = [provider._binary_path, '--print', '--output-format', 'json', '--model', provider.model,
               '--permission-mode', 'bypassPermissions', '--setting-sources', '', '--tools', '',
               '--strict-mcp-config', '--mcp-config', str(config), '--allowed-tools',
               'mcp__indiebizos__execute_ibl', '--no-session-persistence', '--append-system-prompt', prompt]
    result = subprocess.run(command, input=REQUEST, text=True, cwd=repo, env=provider._build_env(),
                            capture_output=True, timeout=300)
    (output / 'model.json').write_text(result.stdout)
    (output / 'stderr.log').write_text(result.stderr)
    (output / 'request.txt').write_text(REQUEST)
    for name in ('calls.jsonl', 'published.json', 'baseline.json'):
        if (repo / name).exists():
            (output / name).write_bytes((repo / name).read_bytes())
    assert result.returncode == 0, result.stderr[-1500:]
    published = json.loads((repo / 'published.json').read_text())
    assert published['source'] != BROKEN and published['state'] == 'active'
    assert not (repo / 'candidate/data/workflows').exists()
    calls = [json.loads(line) for line in (repo / 'calls.jsonl').read_text().splitlines()]
    assert len({c['pid'] for c in calls}) == 1
    baseline = json.loads((repo / 'baseline.json').read_text())
    assert (baseline['valid'] is False or baseline['result'].get('success') is False), (
        '시험의 수정 전 결함이 재현되지 않았다')
    assert published['function_id'] == baseline['function_ref']['function_id']
    assert published['revision'] != baseline['function_ref']['revision']
    for expected in ('receipt-1', 'bare-2'):
        assert any(expected in json.dumps(c['result'].get('value')) and c['result'].get('success')
                   and '[fn:작업번호]' in c['code'] for c in calls), '개정 뒤 재호출 근거가 없다'
    monkeypatch.setattr('workflow_store._get_workflows_path', lambda: repo / 'data/workflows')
    assert function_store.resolve('작업번호')['revision'] == published['revision']
    for value in ({'task_ref': {'kind': 'guestpc', 'task_id': 'third'}},
                  {'kind': 'guestpc', 'task_id': 'fourth'}):
        answer = handle_request({'edition': 2, 'code': '[fn:작업번호]{작업:$task}', 'inputs': {'task': value}})
        assert answer['success'] and answer['value'] == value.get('task_ref', value)['task_id']


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--serve':
        serve(Path(sys.argv[2]).resolve())
    else:
        raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
