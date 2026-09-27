"""Direct Python library calls (current IBL only), never a script registry."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def authorize():
    import json
    import principal
    from thread_context import get_allowed_nodes
    from ibl_v2_ir import Fault
    policy = json.loads((ROOT / 'policy.json').read_text())
    if (not principal.is_owner() or get_allowed_nodes() is not None
            or policy.get('local_python', {}).get('owner_unrestricted') is not True):
        raise Fault('LOCAL_PYTHON_PERMISSION', 'local_python은 제한 없는 주인의 로컬 코드 실행에만 허용됩니다.', kind='permission')


def dependency(_args):
    import hashlib
    from runtime_utils import get_python_cmd
    return {'environment': _load('python_bridge_environment').fingerprint(),
            'interpreter': get_python_cmd(),
            'policy': hashlib.sha256((ROOT / 'policy.json').read_bytes()).hexdigest()}


def open_session(project_path, agent_id):
    authorize()
    return _load('python_bridge_session').Session(project_path, agent_id)


def _current_only(_params):
    return {'success': False, 'error_type': 'protocol',
            'error': 'Python 직접 호출은 현재 IBL(edition:2) 프로그램에서 사용하세요.'}


# Literal dispatch entries are also the builder's contract source.
_OP_DISPATCHERS = {'python_op': {
    'modules': _current_only, 'describe': _current_only, 'call': _current_only,
    'getattr': _current_only, 'export': _current_only, 'release': _current_only}}
_OP_DEFAULTS = {'python_op': 'modules'}


def execute(tool_input, context):
    authorize()
    return _current_only(tool_input)
