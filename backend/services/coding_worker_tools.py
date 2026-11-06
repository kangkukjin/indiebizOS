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
    runtime = Path(workspace).parent / ('runtime-' + Path(workspace).name)
    processes = CodingProcesses(workspace, runtime, own_sandbox=native)
    from code_analysis_bridge import Bridge
    bridge = processes.analysis_bridge = Bridge(workspace, runtime, cancelled)
    runner.ai.system_prompt = (getattr(runner.ai, 'system_prompt', '') or '') + (
        '\n코드 분석은 [self:workspace]{op:"read",kind:"code",selector:{analysis:"definition",path:"파일",line:1,column:1}}. '
        '행·열은 1부터. 변경·빌드는 run_command의 OS 격리에서 실행한다. '
        '의미 기반 변경은 Python으로 backend/code_analysis_cli.py에 JSON stdin을 전달한다. '
        + 'CLI 경로: ' + str(Path(__file__).resolve().parents[1] / 'code_analysis_cli.py'))
    provider.system_prompt = runner.ai.system_prompt
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
                from code_analysis_scope import bind
                with bind(workspace, generation=bridge.resource), checked_read_program(args, str(workspace), agent_id):
                    return execute_tool(name, args, str(workspace), agent_id)
            if name != 'run_command' or not isinstance(args.get('command'), str):
                raise ValueError('이 작업 사본은 execute_ibl 읽기와 run_command만 지원합니다')
            return json.dumps(bridge.command(args['command']), ensure_ascii=False)
        runner.ai._custom_execute_tool = execute
    return processes
