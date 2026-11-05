"""연구 실행 신원과 자료 관측 콜백. snapshot/restore가 병렬 작업에도 운반한다."""
from contextlib import contextmanager
import uuid
import threading
from pathlib import Path
import thread_context

_capture = None
_review = None
_session = None
_executions = {}
_lock = threading.RLock()


def install_capture(callback):
    global _capture
    _capture = callback


def install_review(callback):
    global _review
    _review = callback


def citation_review(text, *, query='', question_ids=(), full_receipts=False, occurrences=None):
    """현재 연구의 인용 검사를 평가에 공급한다. 일반 실행은 추가 작업이 없다."""
    context = current()
    if not context:
        return None
    if _review is None:
        raise RuntimeError('연구 인용 검사기가 준비되지 않았습니다')
    result = _review(context, text, query=query, question_ids=question_ids,
                      full_receipts=full_receipts, occurrences=occurrences)
    if full_receipts:
        import copy
        from research_review import claims
        context['prepared_review'] = copy.deepcopy(result)
        context['prepared_review']['claims'] = claims(text) if occurrences is None else occurrences
    return result


def review_state(dependencies=None):
    context = current()
    return _review(context, '', state_only=True, dependencies=dependencies) if context and _review else None


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
    if not context.get('attached') and (config.get('group') == 'delegation' or config.get('func') == 'delegate'):
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


def capture_stream(events, *, attached_only=False):
    """IBL 밖에서 반환된 일반 도구·CLI 도구 결과도 대화 자료로 보존한다."""
    calls = {}
    observed = set()
    generations = {}
    for event in events:
        if attached_only and not (current() or {}).get('attached'):
            yield event
            continue
        kind = event.get('type')
        if kind == 'tool_start':
            calls[event.get('id')] = event
            generations[event.get('id')] = generations.get(event.get('id'), 0) + 1
        elif kind == 'tool_result' and not event.get('is_error'):
            start = calls.get(event.get('id'), {})
            name = event.get('name') or start.get('name') or ''
            # IBL은 서버에서 축약 전 원문을 이미 보존했다. MCP 관리 도구는 자료가 아니다.
            if name and name != 'execute_ibl' and not name.startswith('mcp__indiebizos__'):
                import hashlib
                import json
                identity = (event.get('id'), generations.get(event.get('id'), 0), name, hashlib.sha256(json.dumps(
                    event.get('result', ''), sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest())
                if event.get('id') and identity in observed:
                    yield event
                    continue
                if event.get('id'):
                    observed.add(identity)
                params = start.get('input') or {}
                if isinstance(params, dict) and params.get('file_path') and not params.get('path'):
                    params = {**params, 'path': params['file_path']}
                observe({'router': 'handler', 'tool': name, 'research_coverage': 'unknown'},
                        params if isinstance(params, dict) else {}, event.get('result', ''))
        yield event


def install_session(callback):
    global _session
    _session = callback


class TurnResearch:
    """일반 심층연구의 수명만 묶는다. 서비스는 기존 자료실을 연결하는 콜백을 제공한다."""
    def __init__(self):
        from contextlib import ExitStack
        self.stack = ExitStack()
        self.context = None

    def __enter__(self):
        return self

    def __exit__(self, *error):
        return self.stack.__exit__(*error)

    def activate(self, runner, framing, message):
        if self.context:
            return self.context.get('guidance', '')
        if current() or not (framing or {}).get('_research_plan'):
            return ''
        if runner.config.get('_is_system_ai') or runner.config.get('_member'):
            return self._unsupported(framing, 'member' if runner.config.get('_member') else 'system_ai')
        if _session is None:
            raise RuntimeError('심층연구 자료 보존 어댑터가 준비되지 않았습니다')
        self.context = self.stack.enter_context(_session(runner, framing, message))
        if self.context is None:
            return self._unsupported(framing, 'unregistered_or_dedicated_project')
        framing['_research_coverage'] = {'surface': 'general_project', 'library_attached': True,
                                        'native_capture': 'observed_returns_only'}
        self.stack.enter_context(scope(self.context))
        self.stack.enter_context(bind_execution(thread_context.get_current_agent_id(),
                                               thread_context.get_current_task_id()))
        return self.context.get('guidance', '')

    @staticmethod
    def _unsupported(framing, surface):
        import json
        status = {'surface': surface, 'library_attached': False,
                  'reason': '이 실행 신원의 자동 연구 자료실 연결은 지원하지 않습니다',
                  'evidence': '기존 파일·도구 실행 근거 사용; 자료실 읽기 검증으로 간주하지 않음'}
        framing['_research_coverage'] = status
        return '\n<research_workspace_status>\n' + json.dumps(status, ensure_ascii=False) + '\n</research_workspace_status>'

    def events(self, events):
        # 활성화는 생성기 안에서 계획 작성 뒤 발생한다. 첫 도구 이벤트 이전에 결정된다.
        def selected():
            for event in events:
                if self.context and event.get('type') == 'final':
                    self.context['response'] = event.get('content') or ''
                if self.context and event.get('type') == 'error':
                    self.context['failed'] = True
                yield event
        yield from capture_stream(selected(), attached_only=True)


def finish_review(response, outcome=None, uses=()):
    """Carry the already-decided result to both storage surfaces. No file discovery or re-review."""
    context = current()
    if not context:
        return None
    from research_review import saved_citations
    from hashlib import sha256
    result = dict(outcome or {'review_status': 'NOT_RUN', 'goal_status': 'UNKNOWN'})
    fingerprint = sha256(response.encode()).hexdigest()
    if result.get('response_hash') and result['response_hash'] != fingerprint:
        raise ValueError('검수한 응답과 최종 전달할 응답의 지문이 다릅니다')
    prepared = context.get('prepared_review') or {}
    result.update(response_hash=sha256(response.encode()).hexdigest(), citation_uses=list(uses),
                  citations=saved_citations(prepared, uses) if prepared and uses else [],
                  research_identity={k: context[k] for k in ('project_uid', 'thread_id', 'run_id')})
    result['unresolved_citations'] = prepared.get('invalid', [])
    result['submissions'] = context.get('submissions', [])
    result['research_dependencies'] = prepared.get('dependencies')
    result['research_state'] = prepared.get('state_revision')
    context['final_review'] = result
    return result
