"""Execution-scoped package adapter; foreign language details belong to providers."""
from ibl_v2_ir import Fault
from ibl_v2_adapters import Adapted


def invoke_foreign(runtime, args, config, project_path, agent_id, node, action):
    from tool_loader import load_tool_handler
    from member_profile import gate
    if gate(node, action, config):
        raise Fault('MEMBER_ACCESS', '로컬 외부 코드 실행 권한이 없습니다.', kind='permission')
    handler = load_tool_handler(config['tool'])
    if handler is None:
        raise Fault('PY_RUNTIME_UNAVAILABLE', '외부 실행 공급자를 불러올 수 없습니다.', kind='protocol')
    handler.authorize()
    key = config['tool']
    with runtime.lock:
        session = runtime.foreign_sessions.get(key)
        if session is None:
            session = handler.open_session(project_path, agent_id)
            runtime.foreign_sessions[key] = session
            runtime.resources.callback(session.close)
    value, evidence = session.invoke(args, runtime)
    return Adapted(value, evidence)


def provider_snapshot(tool, args):
    from tool_loader import load_tool_handler
    handler = load_tool_handler(tool)
    if handler is None:
        raise Fault('PY_RUNTIME_UNAVAILABLE', '외부 실행 공급자가 없습니다.', kind='protocol')
    return handler.dependency(args)
