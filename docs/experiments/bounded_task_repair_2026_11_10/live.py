"""Real model + native fixture actions, isolated from production MCP and data.

This tests method choice and delivered files. Backend repair/return, authority,
budget and process cleanup are covered separately by test_task_repair.py.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import json
import os
import tempfile
import time

from providers.codex import CodexProvider
from providers.base import turn_token_scope
from task_continuation import message
from thread_context import actor_context


class FixtureProvider(CodexProvider):
    TOOL_POLICY = ''

    def _mcp_bridge_acquire(self):
        return None  # No production tools; only native fixture file operations.

    def _build_command(self, **kwargs):
        cmd = super()._build_command(**kwargs)
        cmd.remove('--dangerously-bypass-approvals-and-sandbox')
        cmd[-1:-1] = ['--sandbox', 'workspace-write', '-c', 'approval_policy="never"',
                     '-c', 'web_search="disabled"']
        return cmd


def main():
    policy = (ROOT / 'data/common_prompts/fragments/12_ibl_only.md').read_text()
    policy = policy.split('## 작성과 검사\n', 1)[1].split('\n\n지속 수리가', 1)[0]
    report = {'model': 'gpt-6-astra:high', 'scope': 'synthetic native file tasks; not production self-repair',
              'cases': []}
    with tempfile.TemporaryDirectory(prefix='bounded-repair-live-') as directory:
        base = Path(directory)
        cli_home = base / 'cli-home'
        cli_home.mkdir()
        auth = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'auth.json'
        (cli_home / 'auth.json').symlink_to(auth)
        for name in ('alternative', 'direct_code', 'repair_required', 'repair_exhausted'):
            work = base / name
            work.mkdir()
            (work / 'input.json').write_text(json.dumps([
                {'state': 'confirmed', 'net': 12}, {'state': 'cancelled', 'net': 90},
                {'state': 'confirmed', 'net': 18}, {'state': 'confirmed', 'net': 7}]))
            broken = 'def total(rows):\n    return sum(row["amount"] for row in rows if row["state"] == "confirmed")\n'
            (work / 'helper.py').write_text(broken)
            request = '확정 주문만 집계해 report.json에 count(건수), total(합계) 필드로 실제 저장하고 확인해 주세요. 취소 주문은 제외하세요.'
            context = 'input.json은 동일 원자료입니다. helper.py 호출은 KeyError: amount로 실패했습니다.'
            if name == 'alternative':
                (work / 'alternate.py').write_text('import json\nrows=json.load(open("input.json"))\nrows=[r for r in rows if r["state"]=="confirmed"]\nprint(json.dumps({"count":len(rows),"total":sum(r["net"] for r in rows)}))\n')
                context += ' alternate.py는 같은 원자료와 필수 조건을 지원하는 기존 별도 집계 도구입니다.'
            elif name == 'direct_code':
                context += ' 이 업무 전용 코드 작성은 가능합니다. helper.py는 다른 팀 공유 파일이므로 변경 권한이 없습니다.'
            elif name == 'repair_required':
                request += ' 후속 소비자는 helper.total을 계속 사용하므로 이 함수도 같은 자료에서 올바른 확정 주문 합계를 반환해야 합니다. 이 fixture 파일은 직접 수정 권한이 있습니다.'
            else:
                context += ' 한정 수리 자식이 검사 중 수리 몫을 소진해 안전하게 중단됐습니다. 원래 업무의 예산은 남아 있고 후보는 helper.py에 보존되어 있습니다. 이 후보의 추가 수리 예산은 없습니다.'
            provider = FixtureProvider(api_key='', model=report['model'], tools=[], project_path=str(work),
                agent_id='bounded-live-' + name, agent_name='bounded fixture',
                system_prompt=policy + '\n이 검증에서는 현재 임시 폴더의 가상 자료와 네이티브 파일·셸만 사용합니다. '
                              '네트워크·다른 경로·운영 서비스에 접근하지 마세요. 설치·Git·공용 등록은 필요 없습니다.')
            provider.disable_session_persistence = True
            original_env = provider._build_env
            provider._build_env = lambda: {**original_env(), 'CODEX_HOME': str(cli_home),
                                           'INDIEBIZ_RUNTIME_STATE_DIR': str(base / 'runtime')}
            assert provider.init_client()
            prompt = message(request, context, [{'name': 'aggregate', 'is_error': True,
                             'result': {'error': 'KeyError: amount'}}], reason='같은 실행 중 실패 관측')
            started = time.monotonic()
            events = []
            with actor_context(agent_id=provider.agent_id, task_id=name, origin='training'), \
                    turn_token_scope(provider.agent_id, name, hard_token_limit=300000, deadline_s=120):
                events.extend(provider.process_message_stream(message=prompt, history=[],
                    cancel_check=lambda: time.monotonic() - started >= 115))
            output = work / 'report.json'
            try:
                value = json.loads(output.read_text())
            except (OSError, ValueError):
                value = None
            edited = (work / 'helper.py').read_text() != broken
            repaired = False
            if name == 'repair_required':
                import subprocess
                check = subprocess.run([sys.executable, '-c',
                    'import helper,json; assert helper.total(json.load(open("input.json")))==37'],
                    cwd=work, capture_output=True, timeout=10)
                repaired = check.returncode == 0
            passed = value == {'count': 3, 'total': 37} and (repaired if name == 'repair_required' else not edited)
            row = {'name': name, 'passed': passed, 'result': value, 'helper_changed': edited,
                   'helper_verified': repaired, 'elapsed_s': round(time.monotonic() - started, 3),
                   'usage': provider.metrics.to_dict(), 'events': events}
            report['cases'].append(row)
            Path(__file__).with_name('live.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            print(json.dumps({k: row[k] for k in ('name', 'passed', 'elapsed_s')}, ensure_ascii=False), flush=True)
    assert all(c['passed'] for c in report['cases'])


if __name__ == '__main__':
    main()
