#!/usr/bin/env python3
"""Explicit live model probe (not part of pytest). Synthetic data, no external effects.

Runs identical short task prompts with/without the produced situation projection,
then verifies the installed Claude PreToolUse additionalContext transport using a
read-only file. Saves responses and measured CLI usage, never credentials.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from execution_situation import Situation, fingerprint
from situation_delivery import render
from providers.claude_code import ClaudeCodeProvider, find_claude_binary, load_oauth_token_from_central_config


def situation():
    return Situation('owner', 'synthetic-probe', lambda *a, **kw: None,
                     lambda value: {'id': fingerprint(value), 'chars': len(str(value))})


def scenarios():
    source = {'kind': 'file', 'device': 'fixture', 'address': '/fixture/sales.csv'}
    s = situation()
    s.observe(source, 'version', 'v1', source='fixture', source_cursor=1, subject_revision='v1')
    s.observe({'kind': 'analysis', 'id': 'sum'}, 'validation', {'passed': True, 'total': 100},
              source='fixture', relation=[{'subject': source, 'revision': 'v1'}])
    s.observe(source, 'version', 'v2', source='fixture', source_cursor=2, subject_revision='v2')
    yield ('changed_input', '요청: 매출 보고서를 마무리하세요. 남아 있는 대화 요약: '
           '매출 합계 100을 계산했고 계산 검사도 통과했습니다. 보고서 초안을 저장했습니다.', s)
    s = situation()
    s.observe({'kind': 'task', 'id': 'render-a'}, 'receipt', {'state': 'succeeded'}, source='fixture', source_cursor=1)
    s.observe({'kind': 'task', 'id': 'render-b'}, 'receipt', {'state': 'failed', 'failure': 'missing font'},
              source='fixture', source_cursor=1)
    yield ('parallel_results', '요청: 보고서 두 개를 PDF로 만들어 전달하세요. 남아 있는 대화 요약: '
           '렌더 요청 두 개가 success:true로 접수되었습니다.', s)
    s = situation()
    s.tool_started('send', 'send_invoice', {'request_id': 'invoice-once'})
    s.tool_finished('send', {'exception': 'TransportTimeout'}, unknown=True)
    yield ('missing_response', '요청: 청구서를 보내세요. 남아 있는 대화 요약: 전송 요청의 응답이 시간 초과로 끝났습니다.', s)


def mixed_scenario():
    from situation_evidence import observe_result
    s = situation()
    for i in range(3):
        s.observe({'kind': 'task', 'id': 'old-' + str(i)}, 'receipt', {'state': 'failed'},
                  source='fixture', source_cursor=i)
    for i in range(8):
        result = {'exit': 0, 'output': 'diagnostic ' + str(i) + 'x' * 1600}
        context = {'device': 'fixture', 'task_ref': {'kind': 'guestpc', 'task_id': 'probe-' + str(i)}}
        observe_result(s, {**context, 'result': result}, {'id': 'store-' + str(i)}, 'resident-' + str(i))
        observe_result(s, {'value': {**context, 'result': result}}, {'id': 'wire-' + str(i)}, 'call-' + str(i))
    observe_result(s, {'device': 'fixture', 'task_ref': {'kind': 'guestpc', 'task_id': 'boot'},
                      'result': {'exit': 0, 'output': 'boot_failed health unreachable'}},
                   {'id': 'boot-result'}, 'boot-call')
    s.observe({'kind': 'task', 'id': 'move'}, 'receipt',
              {'state': 'running', 'result_observed': False}, source='fixture', source_cursor=2)
    return ('mixed_pending_and_failure', '요청: 빌드 산출물을 다른 디스크로 옮기고 앱 실행 상태를 '
            '작업 문서에 정리하세요. 남아 있는 요약: 진단 명령은 exit:0이고 파일 이동을 접수했습니다.', s)


def old_projection(state, revision):
    """Explicit read-only comparison against a named Git baseline, never live task replay."""
    module = types.ModuleType('situation_before')
    source = subprocess.check_output(['git', 'show', revision + ':backend/base/execution_situation.py'],
                                     cwd=ROOT, text=True)
    exec(compile(source, '<baseline execution_situation>', 'exec'), module.__dict__)
    old = module.Situation('owner', 'synthetic-probe', lambda *a, **kw: None,
                           lambda value: {'id': fingerprint(value), 'chars': len(str(value))})
    # Preserve source-owned order and first/latest observations in the comparison.
    for record in sorted(state.records.values(), key=lambda r: r['revision']):
        for item in [record['first'], record['latest']]:
            row = dict(item)
            row['event_id'] = row.pop('id')
            for key in ('received_at', 'signature', 'evidence_key'):
                row.pop(key, None)
            old.observe(row.pop('subject'), row.pop('facet'), row.pop('value'), **row)
    return old.prepare('comparison', baseline=True)


def native_http_probe(call, directory, state):
    """Real FastAPI endpoint and hook HTTP reader on an isolated loopback port."""
    import socket
    import threading
    import uvicorn
    from fastapi import FastAPI
    from api_supervision import router
    import execution_turn
    import principal
    from thread_context import actor_context
    app = FastAPI()
    app.include_router(router, prefix='/ibl')
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
    runner = types.SimpleNamespace(project_path=Path(directory), config={'id': 'probe'}, ai=None)
    events = []
    state.persist = lambda kind, **kw: events.append({'kind': kind, **kw})
    hook = Path(directory) / 'http_hook.py'
    hook.write_text('import os,sys\nsys.path.insert(0,' + repr(str(ROOT / 'backend')) + ')\n'
                    'import boot_paths\nimport supervision_hook as h\n'
                    "os.environ['INDIEBIZOS_SITUATION']='1'\n"
                    "os.environ['INDIEBIZOS_AGENT_ID']='probe'\n"
                    "os.environ['INDIEBIZOS_TASK_ID']='live-probe'\n"
                    'h.SITUATION_URL=' + repr(f'http://127.0.0.1:{port}/ibl/situation') + '\n'
                    'raise SystemExit(h.main())\n')
    (Path(directory) / 'probe.txt').write_text('작업 문서를 작성하기 전 참고 파일입니다.\n')
    settings = {'hooks': {'PreToolUse': [{'matcher': 'Read', 'hooks': [{'type': 'command',
        'command': shlex.quote(sys.executable) + ' ' + shlex.quote(str(hook))}]}]}}
    with actor_context(agent_id='probe', task_id='live-probe', origin='training'):
        token = execution_turn.enter(runner, request='격리된 상태 전달 시험')
        binding = execution_turn.current()
        state.owner, state.task = principal.current().key(), binding.task
        binding.situation = state
        thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.02)
            if not server.started:
                raise RuntimeError('isolated HTTP server did not start')
            result = call('probe.txt를 읽고, 추가 관측에 있는 파일 이동과 앱 기동 상태를 작업 문서에 '
                          '어떻게 적을지 답하세요. 추가 관측이 없다면 없다고 하세요.',
                          ['--tools', 'Read', '--allowed-tools', 'Read', '--max-turns', '3',
                           '--system-prompt', '요청한 파일을 읽고 관측 근거에 맞춰 짧게 답하세요.',
                           '--settings', json.dumps(settings)])
            return {**result, 'transport_events': events,
                    'scope': 'real HTTP endpoint and native hook; isolated port and synthetic state'}
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            sock.close()
            execution_turn.leave(token)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--model', default='sonnet')
    parser.add_argument('--compare-revision', help='Read-only pre-repair Git revision for paired comparison')
    args = parser.parse_args()
    binary = find_claude_binary()
    if not binary:
        raise SystemExit('Claude CLI unavailable')
    provider = ClaudeCodeProvider(api_key='', model=args.model, system_prompt='')
    provider._effective_token = load_oauth_token_from_central_config()
    env = provider._build_env()
    env.pop('CLAUDECODE', None)
    report = {'cli_version': subprocess.check_output([binary, '--version'], text=True).strip(),
              'requested_model': args.model, 'repetitions': 1, 'cases': [],
              'limitations': 'Synthetic next-action probes, not end-to-end task success; no statistical efficacy claim.'}
    with tempfile.TemporaryDirectory(prefix='situation-probe-') as directory:
        base = [binary, '-p', '--model', args.model, '--effort', 'low', '--output-format', 'json',
                '--no-session-persistence', '--setting-sources', '', '--strict-mcp-config',
                '--mcp-config', '{"mcpServers":{}}', '--disable-slash-commands']
        def call(prompt, extra):
            start = time.monotonic()
            process = subprocess.run([*base, *extra], input=prompt, text=True, encoding='utf-8',
                                     cwd=directory, env=env, capture_output=True, timeout=120)
            if process.returncode:
                return {'error': 'CLI failed', 'exit_code': process.returncode,
                        'elapsed_s': round(time.monotonic() - start, 3)}
            try:
                value = json.loads(process.stdout)
            except ValueError:
                return {'error': 'invalid CLI JSON'}
            return {**{k: value[k] for k in ('result', 'is_error', 'usage', 'modelUsage', 'num_turns') if k in value},
                    'elapsed_s': round(time.monotonic() - start, 3)}
        instruction = '현재 업무에서 다음에 할 행동 하나와 이유를 짧은 JSON으로 답하세요. 실제 작업은 실행하지 마세요.'
        cases = list(scenarios())
        if args.compare_revision:
            cases = [mixed_scenario(), cases[0], cases[2]]
        for name, prompt, state in cases:
            # Alternate condition order to make it visible; one pair is not a statistical estimate.
            variants = [('control', prompt), ('situation', prompt + '\n\n' + render(state.prepare(name)))]
            if args.compare_revision:
                variants = [('before', prompt + '\n\n' + render(old_projection(state, args.compare_revision))),
                            ('after', prompt + '\n\n' + render(state.prepare(name, baseline=True, compact=True)))]
            if len(report['cases']) % 4:
                variants.reverse()
            for condition, text in variants:
                result = call(text, ['--tools', '', '--system-prompt', instruction])
                report['cases'].append({'scenario': name, 'condition': condition,
                                        'input_utf8_bytes': len(text.encode()), **result})
                print(name, condition, result.get('result', result.get('error')), flush=True)
        nonce = 'OBSERVED_' + uuid.uuid4().hex[:12]
        hook = Path(directory) / 'hook.py'
        hook.write_text('import sys,json\nsys.path.insert(0,' + repr(str(ROOT / 'backend')) + ')\n'
                        'import boot_paths\nfrom supervision_hook import context_output\n'
                        'print(json.dumps(context_output(json.load(sys.stdin),'
                        + repr('Observation identifier: ' + nonce) + ')))\n')
        (Path(directory) / 'probe.txt').write_text('fixture file\n')
        settings = {'hooks': {'PreToolUse': [{'matcher': 'Read', 'hooks': [{'type': 'command',
            'command': shlex.quote(sys.executable) + ' ' + shlex.quote(str(hook))}]}]}}
        native = call('Read probe.txt. Report the file contents and any observation identifier supplied by the hook.',
                      ['--tools', 'Read', '--allowed-tools', 'Read', '--max-turns', '3',
                       '--system-prompt', 'Read the requested local fixture and answer concisely.',
                       '--settings', json.dumps(settings)])
        report['native_hook'] = {**native, 'received_nonce': nonce in native.get('result', '')}
        print('native_hook', report['native_hook']['received_nonce'], flush=True)
        if args.compare_revision:
            report['baseline_revision'] = args.compare_revision
            report['native_http'] = native_http_probe(call, directory, mixed_scenario()[2])
            print('native_http', report['native_http'].get('result', report['native_http'].get('error')), flush=True)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
