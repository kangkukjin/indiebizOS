"""연구 실행 신원과 자료 관측 콜백. snapshot/restore가 병렬 작업에도 운반한다."""
from contextlib import contextmanager
import uuid
import thread_context

_capture = None


def install_capture(callback):
    global _capture
    _capture = callback


def current():
    return getattr(thread_context._thread_local, 'research', None)


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
    if context.get('mode') == 'library':
        if not config.get('research_local') or params.get('op') not in {'search', 'sources', 'read', 'versions', 'thread_messages', 'thread_search'}:
            raise PermissionError('저장 자료만 사용 모드입니다. 추가 조사를 허용하려면 대화 설정에서 변경하세요')


def model_config(config):
    """승격/역할 전환도 보존 가능한 API 경로를 유지한다. CLI 네이티브 획득은 관측 불가."""
    context = current()
    cli = {'codex', 'codex_cli', 'claude_code', 'claudecode'}
    if not context or str(config.get('provider', '')).replace('-', '_') not in cli:
        return config
    from model_resolver import resolve
    alternate = resolve('evaluate')
    if str(alternate.get('provider', '')).replace('-', '_') in cli:
        raise ValueError('연구 대화에는 API 모델 설정이 필요합니다. 조종실에서 평가 모델을 설정하세요.')
    context['model_notice'] = '원문 보존을 지원하는 API 보조 모델로 실행했습니다.'
    return alternate
