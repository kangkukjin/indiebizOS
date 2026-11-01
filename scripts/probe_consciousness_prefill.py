#!/usr/bin/env python3
"""Paired fresh model sessions over pure IBL fixtures; no device or file tools.

The Git baseline supplies historical prompt assembly, never production execution.
This measures executor replay, not the whole consciousness/postprocessing pipeline.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import copy
import json
import subprocess
import tempfile
import time
import types
from unittest.mock import patch


def registry():
    from ibl_v2_adapters import load_registry
    return {k: v for k, v in load_registry().items()
            if k.startswith('table:') and v.contract['effects'] == ['pure']}


def selected_memory():
    """Use the shared recall lifecycle with an isolated fixture channel policy."""
    import associative_recall
    runner = types.SimpleNamespace(config={'allowed_nodes': ['table']})
    with patch.dict(associative_recall.CHANNELS, {'sample': {'only': {'hippocampus'}}}), \
            patch('episode_logger.record_trajectory_event'):
        recall = associative_recall.begin(runner, '선택한 액션으로 처리', channel='sample',
                                         action_hint='table:select', deep=False)
        recall.route('EXECUTE')
        result = recall.text()
    if 'user_selected_action' not in result:
        raise RuntimeError('Explicit user choice did not reach the fixture')
    return result


def run_code(code, adapters):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime, Budget
    plan = compile_program(code, adapters)
    if plan.issues:
        return {'success': False, 'errors': plan.report()}
    return Runtime(plan, budget=Budget(steps=100000, rows=1000, seconds=10)).run()


def serve(directory):
    from mcp.server.fastmcp import FastMCP
    from model_result_view import describe_actions
    adapters = registry()
    server = FastMCP('prefill_probe')

    def log(kind, args, result):
        with (Path(directory) / 'calls.jsonl').open('a') as out:
            out.write(json.dumps({'kind': kind, 'args': args, 'result': result}, ensure_ascii=False) + '\n')
        return json.dumps(result, ensure_ascii=False)

    @server.tool()
    def describe(actions: list[str]) -> str:
        """Read current callable contracts for selected allowed table actions."""
        result = describe_actions([a for a in actions if a in adapters], {'table'}, edition=2)
        return log('describe', actions, result)

    @server.tool()
    def execute_ibl(code: str) -> str:
        """Execute edition 2 IBL over inline data. Only pure table adapters are installed."""
        try:
            result = run_code(code, adapters)
        except Exception as exc:
            result = {'success': False, 'error': str(exc)}
        return log('execute', code, result)

    server.run()


def historical_module(revision, filename):
    module = types.ModuleType('historical_' + Path(filename).stem)
    module.__file__ = str(ROOT / filename)
    source = subprocess.check_output(['git', 'show', f'{revision}:{filename}'], cwd=ROOT, text=True)
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', default='607e8a9c')
    parser.add_argument('--model', default='opus')
    parser.add_argument('--assemble-only', action='store_true')
    parser.add_argument('--cases', nargs='*', help='Optional case names for targeted reruns')
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
        return
    if not args.output:
        parser.error('--output is required')
    import ibl_access
    import prompt_builder
    import reframe
    from providers.claude_code import ClaudeCodeProvider, find_claude_binary, load_oauth_token_from_central_config
    from providers.base import normalize_usage
    old = historical_module(args.baseline, 'backend/cognition/prompt_builder.py')
    old_reframe = historical_module(args.baseline, 'backend/cognition/reframe.py')
    old_guides = historical_module(args.baseline, 'backend/datastore/guide_registry.py')
    adapters = registry()
    catalog = copy.deepcopy(ibl_access.load_nodes_raw())
    catalog['nodes']['table']['actions'] = {
        k: v for k, v in catalog['nodes']['table']['actions'].items() if 'table:' + k in adapters}
    with patch.object(ibl_access, 'load_nodes_raw', return_value=catalog):
        environment = ibl_access.build_environment(allowed_set={'table'}, expose_idioms=False)
    cases = [
        ('simple', '입력 [{id:"a",n:2},{id:"b",n:5}]에서 id 열만 원래 순서대로 반환해줘.',
         ['table:select'], [{'id': 'a'}, {'id': 'b'}]),
        ('complex', '입력 [{id:"a",n:2},{id:"b",n:5},{id:"c",n:3}]에서 n이 3 이상인 행만 골라 '
         'n 내림차순으로 정렬하고 id와 double(n의 두 배) 열만 반환해줘.',
         ['table:filter', 'table:sort', 'table:select'], [{'id': 'b', 'double': 10}, {'id': 'c', 'double': 6}]),
        ('unfamiliar', '본문 abcdefg를 글자 수 기준 최대 3자, 겹침 1자로 나눠 각 조각의 text 열만 반환해줘. '
         '시스템의 본문 분할 액션을 사용해서 결과를 확인해줘.',
         ['table:chunk'], [{'text': 'abc'}, {'text': 'cde'}, {'text': 'efg'}]),
        ('reframe', '관측된 입력은 [{id:"a",n:2},{id:"b",n:5}]이다. n이 3 이상인 행의 id만 반환해줘. '
         '직전 호출은 where에 문자열을 넣어 Callable 자료형 오류가 났으며 성공 결과는 없다.',
         ['table:filter', 'table:select'], [{'id': 'b'}]),
        ('followup', '직전 성공 관측 [{id:"a",n:2},{id:"b",n:5}]을 그대로 재사용해서 n이 4 이상인 행만 반환해줘. '
         '새 데이터 조회는 필요 없다.', ['table:filter'], [{'id': 'b', 'n': 5}]),
        ('user_selected', '입력 [{id:"a",n:2},{id:"b",n:5}]에서 사용자가 고른 액션으로 id 열만 반환해줘.',
         ['table:select'], [{'id': 'a'}, {'id': 'b'}]),
    ]
    report = {'baseline_commit': subprocess.check_output(['git', 'rev-parse', args.baseline], cwd=ROOT, text=True).strip(),
              'model': args.model, 'pairs': [], 'scope': 'Fresh executor sessions, fixed framing and synthetic observations. '
              'Pure IBL execution; no original remote tasks repeated. One pair per case; not a statistical or '
              'end-to-end pipeline cost claim. Consciousness generation and postprocessing model costs unmeasured.',
              'postprocessing_model_cost': None, 'consciousness_model_cost': None}
    binary = find_claude_binary() if not args.assemble_only else None
    if not args.assemble_only and not binary:
        raise SystemExit('Claude CLI unavailable')
    provider = ClaudeCodeProvider(api_key='', model=args.model, system_prompt='')
    provider._effective_token = load_oauth_token_from_central_config()
    env = provider._build_env()
    env.pop('CLAUDECODE', None)
    for index, (name, request, actions, expected) in enumerate(cases):
        if args.cases and name not in args.cases:
            continue
        framing = {'task_framing': request, 'achievement_criteria': '관측한 성공 값을 JSON으로 보고한다.',
                   'capability_focus': {'highlight_actions': actions, 'hint': ''}}
        if name == 'followup':
            framing['_inherited_from'] = {'kind': 'fixture', 'previous_observation': 'above'}
        with patch.dict(sys.modules, {'guide_registry': old_guides}):
            before = old.compile_user_command(request, framing)
        after = prompt_builder.compile_user_command(request, framing)
        if name == 'reframe':
            envelope = {'revised': True, 'output': framing, 'scope_revision': 'approach'}
            before = old_reframe.render_for_executor(envelope)
            after = reframe.render_for_executor(envelope)
        selected = selected_memory() if name == 'user_selected' else ''
        variants = {'before': before + selected, 'after': after + selected}
        pair = {'case': name, 'expected': expected, 'runs': []}
        report['pairs'].append(pair)
        for variant in (['before', 'after'] if index % 2 == 0 else ['after', 'before']):
            prompt = variants[variant]
            row = {'variant': variant, 'initial_chars': len(environment) + len(prompt)}
            pair['runs'].append(row)
            if not args.assemble_only:
                with tempfile.TemporaryDirectory(prefix='prefill-probe-') as directory:
                    config = json.dumps({'mcpServers': {'prefill_probe': {'command': sys.executable,
                        'args': [str(Path(__file__).resolve()), '--serve', directory]}}})
                    command = [binary, '-p', '--model', args.model, '--effort', 'medium', '--output-format', 'json',
                        '--no-session-persistence', '--setting-sources', '', '--strict-mcp-config',
                        '--disable-slash-commands', '--tools', '', '--max-turns', '8', '--mcp-config', config,
                        '--allowed-tools', 'mcp__prefill_probe__describe', 'mcp__prefill_probe__execute_ibl',
                        '--system-prompt', '격리된 순수 데이터 과제다. 제공된 execute_ibl로 실제 계산하고 성공 값을 '
                        'JSON으로 보고하라. 필요하면 describe로 계약을 확인하라. 외부 작업을 하지 마라.\n' + environment]
                    start = time.monotonic()
                    process = subprocess.run(command, input=prompt, text=True, cwd=directory, env=env,
                                             capture_output=True, timeout=240)
                    elapsed = round(time.monotonic() - start, 3)
                    if process.returncode:
                        raise RuntimeError(f'{name}/{variant}: CLI exit {process.returncode}')
                    data = json.loads(process.stdout)
                    log = Path(directory) / 'calls.jsonl'
                    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
                    executions = [c for c in calls if c['kind'] == 'execute']
                    row.update(elapsed_s=elapsed, usage=normalize_usage(data.get('usage')), raw_usage=data.get('usage'),
                               model_usage=data.get('modelUsage'), num_turns=data.get('num_turns'),
                               model_error=data.get('is_error', False), answer=data.get('result'), calls=calls,
                               describe_calls=sum(c['kind'] == 'describe' for c in calls),
                               wrong_calls=sum(not c['result'].get('success') for c in executions),
                               execution_passed=bool(executions and executions[-1]['result'].get('success')
                                                     and executions[-1]['result'].get('value') == expected))
            print(json.dumps({k: v for k, v in row.items() if k not in ('calls', 'answer', 'model_usage', 'raw_usage')}, ensure_ascii=False), flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
