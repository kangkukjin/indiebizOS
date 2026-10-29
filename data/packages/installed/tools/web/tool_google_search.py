"""One-call Google browser search, isolated from interactive browser work and member sessions."""
import asyncio
import hashlib
import json
import re
import time
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlencode

from common.pkg_utils import load_singleton

MAX_RESULTS = 10
MAX_QUERIES = 10
QUERY_SECONDS = 25
BATCH_SECONDS = 90


def _parser():
    return load_singleton(__file__, 'web_google_dom')


def _session_module():
    anchor = Path(__file__).parent.parent / 'browser-action' / 'handler.py'
    return load_singleton(anchor, 'browser_session', module_key='google_search_browser_session')


def _run(coro):
    from system_tools import _get_async_loop
    future = asyncio.run_coroutine_threadsafe(coro, _get_async_loop())
    try:
        return future.result(timeout=BATCH_SECONDS + 5)
    except BaseException:
        future.cancel()
        raise


def search(args, project_path='.'):
    """Capture authority before the async hop; batch queries share an isolated locked session."""
    from principal import is_owner, cache_key
    parser = _parser()
    if not is_owner():
        return parser.failure('FORBIDDEN', 'Google 브라우저 검색은 소유자 작업에서만 사용할 수 있습니다.')
    raw = args.get('queries')
    batch = raw is not None
    if isinstance(raw, str):
        raw = re.split(r'[,\n]', raw)
    if not batch:
        raw = [args.get('query')]
    if (not isinstance(raw, list) or not raw or len(raw) > MAX_QUERIES or
            any(not isinstance(q, str) or not q.strip() or len(q) > 2000 for q in raw)):
        return parser.failure('INVALID_QUERY', '검색어는 1~2000자이며 배치는 1~10개입니다.')
    queries = [q.strip() for q in raw]
    try:
        requested = int(args.get('limit', args.get('count', 5)) or 5)
        if requested < 1:
            raise ValueError
    except (ValueError, TypeError):
        return parser.failure('INVALID_LIMIT', 'limit는 양의 정수입니다.')
    country = str(args.get('country') or '').lower()
    if country and not re.fullmatch(r'[a-z]{2}(?:-[a-z]{2})?', country):
        return parser.failure('INVALID_COUNTRY', 'country는 kr/us 또는 kr-kr/us-en 같은 지역 코드입니다.')
    language = args.get('language') or 'auto'
    if language not in ('auto', 'ko', 'en'):
        return parser.failure('INVALID_LANGUAGE', 'language는 auto/ko/en입니다.')
    # No user profile/cookie file: owner_scope prevents BrowserSession's default automatic state.
    identity = json.dumps(['google-search', cache_key(), str(Path(project_path).resolve())])
    owner = hashlib.sha256(identity.encode()).hexdigest()
    try:
        call = load_singleton(__file__, 'webcrawl_embedded').prepare()
        result = _run(_collect(queries, min(requested, MAX_RESULTS), country, language, owner, batch, call))
    except Exception as exc:
        code = 'SEARCH_TIMEOUT' if isinstance(exc, TimeoutError) else 'BROWSER_UNAVAILABLE'
        return parser.failure(code, 'Google 검색 브라우저를 실행하지 못했습니다: ' + type(exc).__name__)
    if requested > MAX_RESULTS:
        result.update(clamped=True, requested=requested, message=f'요청 {requested}건 → 첫 페이지 최대 {MAX_RESULTS}건으로 제한했습니다.')
    return result


async def _collect(queries, limit, country, language, owner, batch, call=None):
    parser = _parser()
    module = None if call else _session_module()
    driver = 'embedded' if call else 'playwright'
    started = time.monotonic()
    results = []
    tab = None
    blocked = False
    try:
        with module.owner_scope(owner) if module else nullcontext():
            session = module.BrowserSession.get_instance() if module else None
            for query in queries:
                remaining = BATCH_SECONDS - (time.monotonic() - started)
                if blocked:
                    result = parser.failure('SKIPPED_AFTER_BLOCK', '앞선 Google 확인 화면 때문에 나머지 검색을 중단했습니다.')
                elif remaining <= 0:
                    result = parser.failure('SEARCH_TIMEOUT', 'Google 검색 배치 시간 제한을 초과했습니다.')
                else:
                    try:
                        if call and tab is None:
                            opened = await call(op='tab', mode='new', url='about:blank', timeout=5000)
                            tab = opened.get('tab_id')
                            if not tab:
                                raise RuntimeError(opened.get('error_code', 'BROWSER_UNAVAILABLE'))
                        result = await asyncio.wait_for(
                            _one_embedded(call, tab, query, limit, country, language) if call else
                            _one(session, query, limit, country, language), min(QUERY_SECONDS, remaining))
                    except TimeoutError:
                        result = parser.failure('SEARCH_TIMEOUT', 'Google 검색 결과를 기다리다 시간 제한을 초과했습니다.')
                    except Exception as exc:
                        result = parser.failure('BROWSER_UNAVAILABLE', 'Google 브라우저 검색 실패: ' + type(exc).__name__)
                result.update(query=query, source='google', method='browser', browser_driver=driver)
                results.append(result)
                blocked = blocked or result.get('error_code') in ('CAPTCHA_REQUIRED', 'CONSENT_REQUIRED')
    finally:
        if call:
            for args in ([{'op': 'tab', 'mode': 'close', 'tab_id': tab}] if tab else []) + [{'op': 'close'}]:
                try:
                    closed = await call(**args, timeout=2000)
                    if closed.get('success') is False and results:
                        results[-1]['cleanup_error'] = closed.get('error_code', 'TAB_CLOSE_FAILED')
                except Exception as exc:
                    if results:
                        results[-1]['cleanup_error'] = type(exc).__name__
    if not batch:
        return results[0]
    items = [{**item, 'query': r['query']} for r in results for item in r['items']]
    errors = [{k: r[k] for k in ('query', 'error', 'error_code') if k in r} for r in results if not r['success']]
    out = {'success': not errors, 'source': 'google', 'method': 'browser', 'browser_driver': driver, 'queries': queries,
           'items': items, 'count': len(items), '_display': {'group_by': 'query'},
           'sections': [{k: r[k] for k in ('query', 'count', 'elapsed_ms', 'session_reused', 'error_code', 'message', 'cleanup_error') if k in r} for r in results]}
    if errors:
        out.update(errors=errors, error=f'검색 {len(errors)}개 실패; 성공한 결과는 items에 보존')
    return out


def _url(query, limit, country, language):
    params = {'q': query, 'num': limit,
              'hl': ('ko' if re.search('[가-힣]', query) else 'en') if language == 'auto' else language}
    if country:
        params['gl'] = country.split('-')[0]
    return 'https://www.google.com/search?' + urlencode(params)


async def _one_embedded(call, tab, query, limit, country, language):
    parser = _parser()
    started = time.monotonic()
    url = _url(query, limit, country, language)
    value = await call(op='navigate', tab_id=tab, url=url, timeout=15000)
    # Google can replace its initial navigation (ERR_ABORTED) while loading the final search page.
    # Observe that page; do not navigate/retry or accept another query's results.
    if value.get('success') is False and value.get('error_code') != 'ERR_ABORTED':
        return parser.failure(value.get('error_code', 'BROWSER_UNAVAILABLE'), value.get('error', '내장 브라우저 이동 실패'))
    for _ in range(25):
        value = await call(op='google_results', tab_id=tab, timeout=3000)
        if value.get('success') is False:
            return parser.failure(value.get('error_code', 'BROWSER_UNAVAILABLE'),
                                  value.get('error', '검색 추출 실패') + ' 최신 앱으로 재시작했는지 확인하세요.')
        result = await asyncio.to_thread(parser.parse_results, value.get('html', ''), value.get('url', ''), limit)
        if result.get('success') and value.get('query') != query:
            result = parser.failure('QUERY_MISMATCH', '요청한 검색어와 현재 Google 결과 페이지의 검색어가 다릅니다.')
        if result.get('error_code') not in ('RESULTS_UNRECOGNIZED', 'QUERY_MISMATCH'):
            break
        await asyncio.sleep(0.2)
    result.update(search_url=url, elapsed_ms=round((time.monotonic() - started) * 1000),
                  session_reused=True, scope='first_page_organic')
    return result


async def _one(session, query, limit, country, language):
    parser = _parser()
    started = time.monotonic()
    url = _url(query, limit, country, language)
    async with session._operation_lock:
        reused = session.is_active
        page = await session.ensure_browser(headless=True)
        response = await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        status = response.status if response else None
        # Readiness is result/empty/challenge evidence, not a fixed sleep or all-network-idle.
        for _ in range(25):
            html = await page.content()
            result = await asyncio.to_thread(parser.parse_results, html, page.url, limit)
            if result.get('error_code') != 'RESULTS_UNRECOGNIZED' or status and status >= 400:
                break
            await asyncio.sleep(0.2)
        if status and status >= 400 and result.get('error_code') not in ('CAPTCHA_REQUIRED', 'CONSENT_REQUIRED'):
            result = parser.failure('HTTP_ERROR', f'Google 검색 응답 HTTP {status}')
        result.update(search_url=url, elapsed_ms=round((time.monotonic() - started) * 1000),
                      session_reused=reused, scope='first_page_organic', http_status=status)
        return result
