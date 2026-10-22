"""Bind task workers to the existing coding process boundary, including API tools."""
import json
from pathlib import Path
import subprocess
import time

from coding_process import CodingProcesses, available


def configure_worker(runner, workspace, task_id, cancelled):
    if not available():
        raise ValueError('이 몸에서는 협업 작업 사본의 OS 쓰기 격리를 지원하지 않습니다')
    provider = runner.ai._provider
    from providers.cli_provider import CliSubprocessProvider
    native = isinstance(provider, CliSubprocessProvider)
    if native and provider.__class__.__name__ != 'CodexProvider':
        raise ValueError('협업 사본의 네이티브 실행은 현재 Codex에서 지원합니다. API 실행자는 격리 명령 도구를 사용합니다')
    runtime = Path(workspace).parent / ('runtime-' + Path(workspace).name)
    processes = CodingProcesses(workspace, runtime, own_sandbox=native)
    if native:
        from providers.coding_profile import configure
        configure(provider, {'id': task_id, 'workspace': str(workspace)}, processes)
    else:
        from tool_loader import load_tool_schema
        runner.ai.tools = [load_tool_schema('execute_ibl'), {
            'name': 'run_command', 'description': '현재 작업 사본 안에서 명령을 실행합니다. 쓰기는 사본에 한정됩니다.',
            'input_schema': {'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command']}}]
        provider.tools = runner.ai.tools
        if hasattr(provider, '_cached_gemini_tools'):
            from google.genai import types
            provider._cached_gemini_tools = [types.Tool(function_declarations=provider._convert_tools())]

        def execute(name, args, project_path, agent_id=None):
            if name == 'execute_ibl':
                from tool_batch import checked_read_program
                from system_tools import execute_tool
                with checked_read_program(args, str(workspace), agent_id):
                    return execute_tool(name, args, str(workspace), agent_id)
            if name != 'run_command' or not isinstance(args.get('command'), str):
                raise ValueError('이 작업 사본은 execute_ibl 읽기와 run_command만 지원합니다')
            proc = processes.spawn(['/bin/sh', '-c', args['command']], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            started = time.monotonic()
            while True:
                try:
                    output, _ = proc.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    if cancelled() or time.monotonic() - started > 240:
                        processes.terminate(proc)
                        raise ValueError('작업 사본 명령이 취소되었거나 시간 한도를 넘었습니다')
            return json.dumps({'success': proc.returncode == 0, 'exit_code': proc.returncode,
                               'output': output.decode(errors='replace')[-50000:]}, ensure_ascii=False)
        runner.ai._custom_execute_tool = execute
    return processes
