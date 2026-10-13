"""연구 실행 신원과 자료 관측 콜백. snapshot/restore가 병렬 작업에도 운반한다."""
from contextlib import contextmanager
import uuid
import threading
from pathlib import Path
import thread_context

_capture = None
_executions = {}
_lock = threading.RLock()


def install_capture(callback):
    global _capture
    _capture = callback


def current():
    return getattr(thread_context._thread_local, 'research', None)


def library_only():
    return (current() or {}).get('mode') == 'library'


@contextmanager
def scope(context):
    old = current()
    thread_context._thread_local.research = context
    try:
        yield
    finally:
        thread_context._thread_local.research = old


def observe(config, params, result):
    context = current()
    if not context or not _capture:
        return result
    if config.get('research_capture') is False:
        return result
    if config.get('router') not in {'handler', 'driver', 'api_engine', 'system'}:
        return result
    try:
        return _capture(context, config, params, result, uuid.uuid4().hex)
    except Exception:
        context['capture_failed'] = True
        raise


def before(config, params):
    context = current()
    if not context:
        return
    if context.get('capture_failed'):
        raise RuntimeError('자료 보존 실패로 조사를 멈췄습니다. 저장 공간과 권한을 확인하세요')
    if config.get('research_local') and params.get('project_ref') != context.get('project_uid'):
        raise PermissionError('현재 연구의 project_ref를 지정하세요. 다른 자료실은 자동으로 섞지 않습니다')
    if config.get('research_local') and params.get('thread_ref') and params['thread_ref'] != context.get('thread_id'):
        raise PermissionError('현재 대화 밖의 자료에는 접근할 수 없습니다')
    if config.get('group') == 'delegation' or config.get('func') == 'delegate':
        raise PermissionError('연구 대화는 독립 실행합니다. 다른 에이전트에게 위임하지 않습니다')
    if context.get('mode') == 'library':
        # 사용자 관점·연구 질문 정리는 외부 획득이 아니다. 같은 대화의 기록만 갱신한다.
        notes_only = (params.get('op') == 'thread_update' and 'notes' in params
                      and params.get('thread_ref') == context.get('thread_id')
                      and set(params) <= {'op', 'project_ref', 'thread_ref', 'expected_revision', 'notes'})
        questions_only = (params.get('op') == 'thread_update' and 'questions' in params
                          and params.get('thread_ref') == context.get('thread_id')
                          and set(params) <= {'op', 'project_ref', 'thread_ref', 'questions'})
        if config.get('research_local') and (notes_only or questions_only):
            return
        if not config.get('research_local') or params.get('op') not in {'search', 'sources', 'read', 'versions', 'thread_messages', 'thread_search'}:
            raise PermissionError('저장 자료만 사용 모드입니다. 추가 조사를 허용하려면 대화 설정에서 변경하세요')


@contextmanager
def bind_execution(agent_id, task_id):
    """실행 중인 대화만 MCP 재진입에 연결한다. 클라이언트가 자료실 신원을 고르지 않는다."""
    key = (agent_id, task_id)
    context = current()
    with _lock:
        _executions[key] = context
    try:
        yield
    finally:
        with _lock:
            _executions.pop(key, None)


@contextmanager
def adopt_execution(agent_id, task_id, project_path):
    with _lock:
        context = _executions.get((agent_id, task_id))
    if str(agent_id).startswith('research:') and context is None:
        raise PermissionError('종료되었거나 확인되지 않은 연구 실행입니다')
    if context and Path(project_path).resolve() != Path(context['path']).resolve():
        raise PermissionError('현재 연구 프로젝트 밖의 자료에는 접근할 수 없습니다')
    # 일반 호출도 풀 스레드의 이전 연구 맥락을 상속하지 않는다.
    with scope(context):
        yield


def capture_stream(events):
    """IBL 밖에서 반환된 일반 도구·CLI 도구 결과도 대화 자료로 보존한다."""
    calls = {}
    for event in events:
        kind = event.get('type')
        if kind == 'tool_start':
            calls[event.get('id')] = event
        elif kind == 'tool_result' and not event.get('is_error'):
            start = calls.pop(event.get('id'), {})
            name = event.get('name') or start.get('name') or ''
            # IBL은 서버에서 축약 전 원문을 이미 보존했다. MCP 관리 도구는 자료가 아니다.
            if name and name != 'execute_ibl' and not name.startswith('mcp__indiebizos__'):
                params = start.get('input') or {}
                if isinstance(params, dict) and params.get('file_path') and not params.get('path'):
                    params = {**params, 'path': params['file_path']}
                observe({'router': 'handler', 'tool': name, 'research_coverage': 'unknown'},
                        params if isinstance(params, dict) else {}, event.get('result', ''))
        yield event
