"""Registered, execution-scoped scripts use the existing script action.

The registry selects a protocol, never a special script ID or library name.
Ordinary stdin/stdout scripts keep their existing execution path.
"""
from pathlib import Path
import yaml
from ibl_v2_ir import Fault

PROTOCOL = 'ibl-script-session/1'


def registration(args):
    from runtime_utils import get_base_path
    if args.get('op', 'run' if args.get('id') else 'list') != 'run':
        return None
    root = get_base_path() / 'data/scripts'
    registry_path = root / 'registry.yaml'
    registry = yaml.safe_load(registry_path.read_text()) if registry_path.exists() else {}
    registry = registry or {}
    sid = args.get('id')
    entry = registry.get(sid) if isinstance(sid, str) else None
    if not entry or (entry.get('callable_contract') or {}).get('adapter', {}).get('protocol') != PROTOCOL:
        return None
    from ibl_v2_adapters import validate_contract
    try:
        validate_contract(entry['callable_contract'])
    except (ValueError, KeyError) as exc:
        raise Fault('SCRIPT_CONTRACT', str(exc), kind='protocol') from exc
    path = (root / str(entry.get('file', ''))).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise Fault('SCRIPT_PATH', '등록된 세션 스크립트 파일을 찾을 수 없거나 허용 경로 밖입니다.', kind='permission')
    if entry.get('interpreter') != 'python':
        raise Fault('SCRIPT_CAPABILITY', '세션 스크립트의 첫 공급자는 Python 인터프리터입니다.', kind='protocol')
    return sid, entry, path


def is_stateful(args):
    return registration(args) is not None


def authorize():
    import principal
    from thread_context import get_allowed_nodes
    if not principal.is_owner() or get_allowed_nodes() is not None:
        raise Fault('LOCAL_CODE_PERMISSION', '세션 스크립트는 제한 없는 주인의 로컬 코드 실행에만 허용됩니다.', kind='permission')


def invoke(runtime, args, registration, project_path, agent_id, config, node, action):
    from common.pkg_utils import load_singleton
    from tool_loader import load_tool_handler
    from member_profile import gate
    from ibl_v2_adapters import Adapted, validate_contract
    from ibl_v2_types import guard
    from ibl_callable_contract import normalize, selected, problems
    if gate(node, action, config):
        raise Fault('MEMBER_ACCESS', '등록 스크립트 실행 권한이 없습니다.', kind='permission')
    authorize()
    from device_registry import required_capability, local_capabilities
    required = required_capability(config.get('runs_on'))
    if required and required not in local_capabilities():
        raise Fault('SCRIPT_CAPABILITY', '이 몸은 등록 세션 스크립트를 로컬에서 실행할 수 없습니다. 원격 전송하지 않았습니다.', kind='protocol')
    sid, entry, path = registration
    if args.get('background') or args.get('args_file') or args.get('target'):
        raise Fault('SCRIPT_CAPABILITY', '세션 스크립트는 현재 로컬 IBL의 동기 실행과 명시 args를 사용합니다.', kind='protocol')
    from common.value_semantics import compare_order, order_matches
    if 'timeout' in args and not order_matches(compare_order(args['timeout'], 0), '>'):
        raise Fault('ARGUMENT_CONTRACT', 'script timeout은 양수여야 합니다.')
    base = validate_contract(entry['callable_contract'])
    params = normalize(base, guard(args.get('args', {}), 'Record', 'script.args'))
    contract = selected(base, params)
    errors = problems(contract, params)
    errors += [f'필수 인자 누락: {k}' for k in contract.get('required', contract['params']) if k not in params]
    errors += [f'지원하지 않는 인자: {k}' for k in params if k not in contract['params']]
    if errors:
        raise Fault('ARGUMENT_CONTRACT', '; '.join(errors))
    for key, value in params.items():
        guard(value, contract['params'][key], key)
    handler = load_tool_handler(config['tool'])
    provider = load_singleton(handler.__file__, 'script_session')
    with runtime.lock:
        session = runtime.foreign_sessions.get(sid)
        if session is None:
            session = provider.Session(project_path, agent_id, sid, path, interpreter=entry.get('interpreter'))
            runtime.foreign_sessions[sid] = session
            runtime.resources.callback(session.close)
    try:
        value, evidence = session.invoke(params, runtime, timeout=args.get('timeout', entry.get('timeout', 60)))
        guard(value, contract['result'], 'script 반환')
    except Fault as exc:
        provider.record(handler.__file__, sid, False, str(exc))
        raise
    provider.record(handler.__file__, sid, True)
    return Adapted(value, evidence)
