"""소유자 내장 브라우저의 임시 작업 탭에서 본문을 읽는다. 인증정보는 옮기지 않는다."""
import hashlib
import uuid
from pathlib import Path

from common.pkg_utils import load_singleton


def prepare():
    """동기 호출 문맥에서 권한을 확인한다. 사용 불가면 기존 수집 경로를 유지한다."""
    from principal import is_owner
    if not is_owner():
        return None
    anchor = Path(__file__).parent.parent / 'browser-action' / 'handler.py'
    bridge = load_singleton(anchor, 'browser_embedded')
    if not bridge.connection():
        return None
    # 독립 임시 작업이므로 기존 AI/사용자 탭을 이동·해제하지 않는다.
    owner = hashlib.sha256(('crawl:' + uuid.uuid4().hex).encode()).hexdigest()

    async def call(**args):
        _, result = await bridge.route({**args, 'driver': 'embedded'}, 'browser_op',
                                      owner, True, False)
        return result

    return call


async def collect(call, url, diagnose):
    """고정 커서의 모든 조각과 관측된 프레임을 수집한다. 부분 수집은 캐시하지 않는다."""
    tab = None
    errors, texts, selections = [], [], []
    capture_cut = False
    title, resolved = '', url
    result = {'success': False, 'url': url, 'method': 'embedded'}

    async def checked(**args):
        value = await call(**args)
        if not isinstance(value, dict) or value.get('success') is False:
            message = (value or {}).get('error', '내장 브라우저 수집 실패')
            raise ValueError(message)
        return value

    async def read_frame():
        nonlocal capture_cut
        chunk = await checked(op='content', mode='text', tab_id=tab, limit=20000)
        first = chunk
        parts = []
        offset = 0
        while True:
            if (chunk.get('document_id') != first.get('document_id') or
                    chunk.get('cursor') != first.get('cursor') or
                    chunk.get('url') != first.get('url') or chunk.get('offset') != offset):
                raise ValueError('수집 중 문서·커서·위치가 변경되었습니다.')
            parts.append(chunk.get('content', ''))
            next_offset = chunk.get('next_offset')
            if next_offset is None:
                break
            if not isinstance(next_offset, int) or next_offset <= offset or not first.get('cursor'):
                raise ValueError('내장 브라우저의 다음 본문 위치가 올바르지 않습니다.')
            offset = next_offset
            chunk = await checked(op='content', mode='text', tab_id=tab,
                                  cursor=first['cursor'], offset=offset, limit=20000)
        if first.get('capture_truncated') or chunk.get('capture_truncated'):
            capture_cut = True
            errors.append({'source_url': first.get('url', url),
                           'error': '내장 브라우저 본문 캡처 상한 초과'})
        selections.append({'source_url': first.get('url', url), 'selector': 'body',
                           'method': 'rendered_dom', 'coverage_limits': [
                               'unloaded_or_collapsed_content', 'images_and_canvas', 'form_values']})
        return ''.join(parts), first

    try:
        probe = await call(op='tab', mode='list', timeout=2000)
        if probe.get('success') is False:
            result.update(error=probe.get('error', '내장 브라우저 연결 불가'),
                          reason='embedded_unavailable',
                          fallback_safe=probe.get('error_code') == 'BROWSER_UNAVAILABLE')
            return result
        opened = await checked(op='tab', mode='new', url=url, timeout=20000)
        tab = opened.get('tab_id')
        if not tab:
            raise ValueError('새 수집 탭의 식별자를 받지 못했습니다.')
        text, page = await read_frame()
        texts.append(text)
        title, resolved = page.get('title', ''), page.get('url', url)
        reason = diagnose(200, resolved, url, text, title)
        if reason in ('login_required', 'bot_blocked'):
            result.update(reason=reason, error='내장 브라우저에서도 인증 또는 접근 제한이 확인됐습니다. limbs:browser로 확인하세요.')
            return result
        try:
            listing = await checked(op='iframe', mode='list', tab_id=tab)
            frames = listing.get('frames')
            if not isinstance(frames, list):
                raise ValueError('프레임 목록을 확인하지 못했습니다.')
            for index, frame in enumerate(frames):
                try:
                    await checked(op='iframe', mode='switch', index=index, tab_id=tab)
                    frame_text, observed = await read_frame()
                    if frame.get('url') and observed.get('url') != frame['url']:
                        raise ValueError('수집 중 프레임 주소가 변경되었습니다.')
                    texts.append(frame_text)
                except ValueError as exc:
                    errors.append({'source_url': frame.get('url', resolved), 'error': str(exc)})
        except ValueError as exc:
            errors.append({'source_url': resolved, 'error': str(exc)})
        text = '\n\n'.join(t for t in texts if t.strip())
        reason = diagnose(200, resolved, url, text, title)
        if not text.strip() or reason in ('login_required', 'bot_blocked'):
            result.update(reason=reason or 'insufficient_content', error='내장 브라우저에서 본문을 확보하지 못했습니다.')
        else:
            result.update(success=True, title=title, text=text, length=len(text),
                          resolved_url=resolved, truncated=capture_cut,  # truncation-scope: source — 내장 캡처 상한으로 잘린 원천임을 신고
                          _content_selection=selections)
            if errors:
                result.update(source_complete=False, partial=True, errors=errors,
                              reason='incomplete_content')
            elif reason:
                result['reason'] = reason
        return result
    except ValueError as exc:
        result.update(error=str(exc), reason='embedded_failed')
        return result
    finally:
        # 호출 전부터 있던 탭은 건드리지 않는다. 연결 실패 때도 해제는 시도한다.
        try:
            try:
                if tab:
                    closed = await call(op='tab', mode='close', tab_id=tab, timeout=2000)
                    if closed.get('success') is False:
                        result['cleanup_error'] = closed.get('error', '수집 탭 닫기 실패')
            finally:
                released = await call(op='close', timeout=2000)
                if released.get('success') is False:
                    result.setdefault('cleanup_error', released.get('error', '수집 작업 해제 실패'))
        except Exception as exc:
            result['cleanup_error'] = f'수집 탭 정리 실패: {type(exc).__name__}'
