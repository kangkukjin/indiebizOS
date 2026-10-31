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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--model', default='sonnet')
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
        for name, prompt, state in scenarios():
            # Alternate condition order to make it visible; one pair is not a statistical estimate.
            variants = [('control', prompt), ('situation', prompt + '\n\n' + render(state.prepare(name)))]
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
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
