"""IBL value/evidence adapter for the IBL-independent file execution module."""
from pathlib import Path
import json
import sys

from ibl_v2_ir import Fault, UNIT


def is_file_call(args):
    return 'path' in args and args.get('op', 'run') == 'run'


def invocation_identity(args):
    if not is_file_call(args):
        return None
    from script_workspace import authorize, source_path, workspace
    from file_script import digest
    from python_environment_lock import fingerprint
    try:
        authorize()
        path = source_path(args['path'])
        root = workspace().resolve()
        hashes = {p.relative_to(root).as_posix(): digest(p.read_bytes())
                  for p in sorted(root.rglob('*.py')) if '__pycache__' not in p.parts}
        environment = fingerprint(root, details=True)
        return {'entry': path.relative_to(root).as_posix(), 'source_hashes': hashes,
                'workspace': str(root), 'interpreter': sys.executable,
                'python_version': sys.version, 'environment_fingerprint': environment['combined'],
                'environment_metadata_fingerprint': environment['environment']}
    except (PermissionError, OSError, ValueError) as exc:
        raise Fault('SCRIPT_PATH', str(exc), kind='permission') from exc


def invoke(runtime, args, config, node, action):
    from repair_context import active
    if active():
        raise Fault('LOCAL_CODE_PERMISSION', '자기수리 임시 Python은 격리 셸에서 실행하세요.', kind='permission')
    from member_profile import gate
    from device_registry import required_capability, local_capabilities
    from script_workspace import authorize, source_path, workspace
    from file_script import execute, ScriptError
    from ibl_v2_adapters import Adapted
    from ibl_v2_compat import plain_arguments
    from logging_utils import mask_secrets
    try:
        authorize()
        if gate(node, action, config):
            raise PermissionError('이 문맥에는 임시 Script 실행 권한이 없습니다.')
        required = required_capability(config.get('runs_on'))
        if required and required not in local_capabilities():
            raise PermissionError('임시 Script는 로컬 PC 실행만 지원합니다. 원격 전송하지 않습니다.')
        if 'id' in args or any(k in args for k in ('args_file', 'interpreter', 'target', 'callable_contract')) or args.get('background'):
            raise Fault('SCRIPT_ARGUMENT', 'path 실행은 id·args_file·interpreter·target·background 없이 args를 사용하세요.')
        params = plain_arguments({'args': args.get('args', {})})['args']
        stdin = json.dumps(params, ensure_ascii=False, allow_nan=False).encode('utf-8')
        from common.pkg_utils import load_singleton
        from tool_loader import load_tool_handler
        handler = load_tool_handler(config['tool'])
        ops = load_singleton(handler.__file__, 'script_ops')
        result = execute(source_path(args['path']), stdin, workspace(),
                         interpreter=sys.executable, timeout=float(args.get('timeout', 300)),
                         check=runtime.check, env=ops._child_env('foreground'),
                         expected_hashes=runtime.local.invocation_dependency['source_hashes'],
                         expected_environment=runtime.local.invocation_dependency['environment_fingerprint'])
    except PermissionError as exc:
        raise Fault('LOCAL_CODE_PERMISSION', str(exc), kind='permission') from exc
    except ScriptError as exc:
        raise Fault(exc.code, str(exc), details=exc.details) from exc
    record = Path(result['record'])
    meta = result['meta']
    evidence = {'execution_id': meta['execution_id'], 'record': str(record),
                'protocol': meta['protocol'], 'exit_code': meta['exit_code'],
                'expires_at': meta['expires_at'], 'source_hashes': meta['source_hashes'],
                'stdin_hash': meta['stdin_hash'], 'stdout': str(record / 'stdout.log'),
                'stderr': str(record / 'stderr.log'), 'result': str(record / 'result.json'),
                'reproduce': {'module': 'file_script_cli', 'record': str(record)}}
    if not result['ok']:
        with (record / 'stderr.log').open('rb') as stream:
            stream.seek(max(0, (record / 'stderr.log').stat().st_size - 4000))
            tail = stream.read().decode('utf-8', errors='replace')
        error = result['error']
        raise Fault(error['code'], error['message'],
                    kind='budget' if error['code'] == 'SCRIPT_TIMEOUT' else 'runtime',
                    partial=result['value'] if result['has_value'] else UNIT,
                    details={**evidence, 'stderr_tail': mask_secrets(tail),
                             'effect_status': 'unknown', 'invoked': True})
    return Adapted(result['value'], {'file_script': evidence})
