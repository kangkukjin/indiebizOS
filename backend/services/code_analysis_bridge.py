"""A launcher-issued workspace channel; readonly IBL and existing sandbox commands."""
import json
import subprocess
import time
from pathlib import Path

from code_analysis_channel import Channel
from code_analysis_scope import bind
from coding_process import CodingProcesses
from coding_store import CodingStore
from workspace_sessions import Workspace


class Bridge:
    def __init__(self, workspace, runtime, cancelled, store=None):
        self.root, self.cancelled = str(Path(workspace).resolve()), cancelled
        from code_analysis_scope import check
        check(self.root)
        self.workspace = Workspace(coding_store=store or CodingStore())
        # This resource is issued by the trusted worker launcher, never by model-supplied mode.
        from coding_projects import CodingProjects
        CodingProjects(self.workspace.code().store)._refuse_self(Path(self.root))
        row = {'id': CodingProjects.resource_id(Path(self.root)), 'path': self.root, 'name': Path(self.root).name,
               'mode': 'worker', 'root_identity': __import__('code_analysis_changes').identity(self.root)}
        self.workspace.code().store.save('project', row)
        self.resource = row['id']
        from code_diagnostics import Feedback
        self.feedback = Feedback(store=self.workspace.code().store)
        self.processes = CodingProcesses(self.root, Path(runtime) / 'commands')
        self.channel = Channel(runtime, self.dispatch)
        self.processes.ipc_path = self.channel.address
        self.processes.environment = {'CODE_ANALYSIS_CONNECTION': str(self.channel.config)}

    def dispatch(self, body):
        if self.cancelled():
            raise ValueError('종료된 작업의 분석 채널입니다')
        op = body.get('op')
        with bind(self.root, writable=True, generation=self.resource):
            if op == 'ibl':
                from tool_batch import checked_read_program
                from system_tools import execute_tool
                args = body.get('args', {})
                with bind(self.root, writable=False, generation=self.resource), checked_read_program(args, self.root, None):
                    return execute_tool('execute_ibl', args, self.root)
            if op == 'command':
                return self.command(body.get('command'))
            if op not in ('read', 'capabilities', 'propose', 'apply', 'recover'):
                raise PermissionError('작업 채널은 read/capabilities/propose/apply/recover만 지원합니다')
            resource = body.get('resource', self.resource)
            row = self.workspace.code().project(resource)
            if Path(row['path']).resolve() != Path(self.root):
                raise PermissionError('현재 사본의 resource만 사용할 수 있습니다')
            args = {k: body[k] for k in ('selector', 'proposal') if k in body}
            if op == 'read' and (args.get('selector') or {}).get('analysis'):
                result = self.workspace.code().analysis.query(row, args['selector'], cancelled=self.cancelled)
                return self.workspace.head('code', row, **result)
            return getattr(self.workspace, op)(resource=resource, **args)

    def command(self, command):
        from code_diagnostics import command_changes
        with bind(self.root, writable=True, generation=self.resource), command_changes(self.root, self.feedback):
            result = self._command(command)
        diagnostics = self.feedback.flush()
        if diagnostics:
            result['code_diagnostics'] = diagnostics
        return result

    def _command(self, command):
        if not isinstance(command, str) or not command or len(command) > 100000:
            raise ValueError('실행할 command 문자열이 필요합니다')
        from command_preflight import check, blocked, rejection
        def inspect(argv, **kwargs):
            proc = self.processes.spawn(argv, env=kwargs['env'], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                out, err = proc.communicate(kwargs['input'].encode(), timeout=kwargs['timeout'])
                return subprocess.CompletedProcess(argv, proc.returncode, out.decode(errors='replace'), err.decode(errors='replace'))
            finally:
                if proc.poll() is None:
                    self.processes.terminate(proc)
        argv = ['/bin/sh', '-c', command]
        preflight = check(argv, cwd=self.root, runner=inspect, cancelled=self.cancelled)
        if blocked(preflight):
            return rejection(preflight)
        proc = self.processes.spawn(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        started = time.monotonic()
        while True:
            try:
                output, _ = proc.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                if self.cancelled() or time.monotonic() - started > 240:
                    self.processes.terminate(proc)
                    raise ValueError('작업 사본 명령 취소·시간 초과')
        return {'success': proc.returncode == 0, 'exit_code': proc.returncode, 'output': output.decode(errors='replace')[-50000:],
                'preflight': preflight, 'executed': True}

    def close(self):
        self.feedback.close()
        self.processes.close()
        self.channel.close()
        self.workspace.code().analysis.close_view(self.resource)
