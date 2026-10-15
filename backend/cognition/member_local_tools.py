"""공통 회원 러너의 기기 도구 어댑터. 판단 루프와 도구 실행은 기존 관문을 쓴다."""
import member_runtime

FILES = {
    'read_file': ('read', '회원 작업 폴더의 파일을 읽는다. 쓰기 전 sha256을 보관한다.'),
    'list_files': ('list', '회원 작업 폴더 안의 파일과 하위 폴더 목록.'),
    'find_files': ('file_find', '회원 폴더에서 파일 이름 패턴으로 검색.'),
    'search_files': ('grep', '회원 폴더의 파일 내용에서 문자열 검색.'),
    'write_file': ('write', '회원 폴더에 파일 저장. 기존 파일은 읽을 때의 sha256을 expected_hash에 반드시 넣는다. 새 파일은 missing. 로컬 승인과 변경 전 사본 보관.'),
    'edit_file': ('file_edit', '회원 파일의 고유한 문자열을 바꾼다. 로컬 승인 필요.'),
}
NAMES = set(FILES) | {'computer'}


def definitions(state):
    tools = []
    if state.get('files_available'):
        for name, (_, description) in FILES.items():
            properties = {'path': {'type': 'string'}}
            required = ['path']
            if name in ('find_files', 'search_files'):
                properties['pattern'] = {'type': 'string'}
                required.append('pattern')
            if name == 'write_file':
                properties.update(content={'type': 'string'}, expected_hash={'type': 'string'})
                required += ['content', 'expected_hash']
            if name == 'edit_file':
                properties.update(old_string={'type': 'string'}, new_string={'type': 'string'},
                                  replace_all={'type': 'boolean'})
                required += ['old_string', 'new_string']
            tools.append({'name': name, 'description': description,
                          'input_schema': {'type': 'object', 'properties': properties, 'required': required}})
    if state.get('screen_available'):
        tools.append({'name': 'computer', 'description': '회원 PC의 화면 캡처와 마우스/키보드. 각 작업은 로컬 승인과 OS 권한 필요. 좌표는 직전 캡처 기준. 중앙 PC 화면에 접근하지 않는다.',
                      'input_schema': {'type': 'object', 'properties': {
                          'action': {'type': 'string', 'enum': ['screen', 'click', 'move', 'type', 'key', 'scroll', 'drag']},
                          **{k: {'type': 'integer'} for k in ('x', 'y', 'x2', 'y2', 'amount')},
                          **{k: {'type': 'string'} for k in ('text', 'key', 'direction', 'button')}}, 'required': ['action']}})
    return tools


def execute(name, args):
    from member_bridge import request
    state = member_runtime.current() or {}
    capability = 'screen_available' if name == 'computer' else 'files_available'
    if not state.get('local_task_id') or not state.get(capability):
        return {'success': False, 'error_type': 'permission', 'error': '회원 기기의 기능 허용이 필요합니다'}
    if name == 'computer':
        op = args.get('action')
        if op not in {'screen', 'click', 'move', 'type', 'key', 'scroll', 'drag'}:
            return {'success': False, 'error': 'unsupported_action'}
        command = {k: v for k, v in args.items() if k in {'x', 'y', 'x2', 'y2', 'amount', 'text', 'key', 'direction', 'button'}}
    else:
        op = FILES[name][0]
        command = {k: v for k, v in args.items() if k in {'path', 'pattern', 'content', 'expected_hash', 'old_string', 'new_string', 'replace_all'}}
    return request({'op': op, **command}, timeout=250)
