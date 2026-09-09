"""받은 원문을 버려 재조회하던 경로: 수집·보관·표시·후속 읽기를 분리한다."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from common.pkg_utils import load_sibling
from ibl_envelope import preview_envelope
from ibl_honesty import truncation_evidence
from test_envelope_preview_2026_09_06 import _run, _fr

ROOT = Path(__file__).resolve().parents[1]
CRAWLER = ROOT / 'data/packages/installed/tools/web/tool_webcrawl.py'
URL = 'https://fixture.test/article'
TEXT = ('앞 문단입니다. ' * 1300) + '\n\n' + ('중간 문단입니다. ' * 1500) + '\n\n끝문장: tail-proof'


@pytest.fixture
def crawl(monkeypatch, tmp_path):
    from common import spill
    monkeypatch.setattr(spill, '_root', lambda: str(tmp_path / 'spill'))
    crawler = load_sibling(CRAWLER, 'tool_webcrawl')
    calls = []

    class Response:
        status_code = 200
        url = URL
        headers = {'Content-Type': 'text/html; charset=utf-8'}
        content = ('<html><title>시험 문서</title><article>'
                   + ''.join('<p>' + p + '</p>' for p in TEXT.split('\n\n'))
                   + '</article></html>').encode()

    def http_get(url):
        calls.append(url)
        return Response()
    monkeypatch.setattr(crawler, '_http_get', http_get)
    monkeypatch.setattr(crawler, '_get_chrome_driver', lambda: None)
    monkeypatch.setattr(crawler, '_get_browser_session', lambda: None)
    monkeypatch.setattr(crawler, '_resolve_google_news', lambda url: None)
    return crawler, calls


def test_full_source_and_snapshot_survive_small_model_preview(crawl):
    crawler, calls = crawl
    raw = crawler.crawl_website(URL, max_length=500)
    assert raw['success'] and len(raw['text']) > 23000 and 'tail-proof' in raw['text']
    assert 'tail-proof' in raw['items'][-1]['text'] and not raw['truncated']
    shown = preview_envelope(raw)
    assert '_preview' in shown and 'text' not in shown
    assert len(json.dumps(shown, ensure_ascii=False)) < 3000
    assert 'tail-proof' not in json.dumps(shown['items'], ensure_ascii=False)
    assert truncation_evidence(shown) == {'preview': True}
    saved = json.loads(Path(raw['source_ref']['path']).read_text())
    assert saved['text'] == raw['text'] and saved['items'] == raw['items']
    assert calls == [URL] and not raw['cache']['hit']
    assert preview_envelope(raw, verbose=True) is raw


def test_more_text_uses_cache_even_after_module_reload(crawl):
    crawler, calls = crawl
    first = crawler.crawl_website(URL, max_length=100)
    # 크롤 모듈이 재로드돼도 디스크 원문을 재사용한다.
    second = load_sibling(CRAWLER, 'tool_webcrawl').crawl_website(URL, max_length=50000)
    assert calls == [URL] and second['cache']['hit']
    assert first['source_ref'] == second['source_ref']
    assert first['text'] == second['text']
    assert 'tail-proof' in json.dumps(preview_envelope(second), ensure_ascii=False)


def test_refresh_is_explicit_and_does_not_overwrite_prior_snapshot(crawl, monkeypatch):
    crawler, calls = crawl
    first = crawler.crawl_website(URL)
    original = crawler._crawl_website_impl
    def changed(*a):
        out = original(*a)
        out['text'] += '\n\n수정된 원문'
        out['length'] = len(out['text'])
        return out
    monkeypatch.setattr(crawler, '_crawl_website_impl', changed)
    second = crawler.crawl_website(URL, refresh=True)
    assert calls == [URL, URL] and not second['cache']['hit']
    assert first['source_ref']['path'] != second['source_ref']['path']
    assert '수정된 원문' not in Path(first['source_ref']['path']).read_text()
    assert '수정된 원문' in second['text']


@pytest.mark.parametrize('cause', ['expiry', 'missing_source', 'broken_index', 'broken_source'])
def test_unusable_cache_is_refetched(crawl, monkeypatch, cause):
    crawler, calls = crawl
    first = crawler.crawl_website(URL)
    source = Path(first['source_ref']['path'])
    index = next(source.parent.glob('crawl_cache_*.json'))
    if cause == 'expiry':
        obj = json.loads(index.read_text())
        obj['fetched_at'] -= 901
        index.write_text(json.dumps(obj))
    elif cause == 'missing_source':
        source.unlink()
    elif cause == 'broken_source':
        source.write_text('{}')
    else:
        index.write_text('broken')
    assert crawler.crawl_website(URL)['success'] and calls == [URL, URL]


def test_parallel_same_url_fetches_once(crawl):
    crawler, calls = crawl
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: crawler.crawl_website(URL), range(4)))
    assert calls == [URL] and all(r['success'] for r in results)
    assert sum(not r['cache']['hit'] for r in results) == 1


def test_project_scopes_do_not_share_cached_pages(crawl, tmp_path):
    crawler, calls = crawl
    crawler.crawl_website(URL, project_path=str(tmp_path / 'a'))
    crawler.crawl_website(URL, project_path=str(tmp_path / 'b'))
    assert calls == [URL, URL]


@pytest.mark.parametrize('partial', [False, True])
def test_failure_or_uncertain_extraction_is_not_reused(crawl, monkeypatch, partial):
    crawler, calls = crawl
    invoked = []
    def fetch(*a):
        invoked.append(a)
        return dict(success=partial, reason='insufficient_content', text='일부 원문', length=5)
    monkeypatch.setattr(crawler, '_crawl_website_impl', fetch)
    crawler.crawl_website(URL)
    crawler.crawl_website(URL)
    assert len(invoked) == 2


def test_storage_failure_is_explicit(crawl, monkeypatch):
    from common import spill
    crawler, calls = crawl
    def fail(*a, **kw):
        raise OSError('disk full')
    monkeypatch.setattr(spill, 'spill_write', fail)
    out = crawler.crawl_website(URL)
    assert not out['success'] and out['reason'] == 'source_storage_failed'
    assert calls == [URL] and 'disk full' in out['error']


@pytest.mark.parametrize('budget', [0, -1, True, '10000'])
def test_invalid_display_budget_does_not_fetch(crawl, budget):
    crawler, calls = crawl
    assert not crawler.crawl_website(URL, max_length=budget)['success'] and not calls


def test_saved_full_document_flows_through_ibl_and_next_turn_call(crawl, monkeypatch, tmp_path):
    import ibl_engine
    from tool_context import ToolContext
    crawler, calls = crawl
    handler = load_sibling(CRAWLER, 'handler')
    original_loader = handler.load_module
    monkeypatch.setattr(handler, 'load_module', lambda n: crawler if n == 'tool_webcrawl' else original_loader(n))
    original = ibl_engine._execute_ibl_impl
    def leaf(ti, project, agent_id=None):
        if ti.get('_node') == 'sense' and ti.get('action') == 'crawl':
            return handler.execute(ti.get('params') or {}, ToolContext(project, 'crawl_website', agent_id=agent_id))
        return original(ti, project, agent_id)
    monkeypatch.setattr(ibl_engine, '_execute_ibl_impl', leaf)
    task = 'crawl-retained-fixture'
    shown = _run('$원문=[sense:crawl]{url:"' + URL + '",max_length:500}', tmp_path, task)
    assert shown.get('_preview') or _fr(shown).get('_preview')
    # 같은 턴의 다음 호출: 모델에 안 보인 끝 문단을 저장 변수에서 골라 온다.
    tail = _run('$원문 >> [table:filter]{where:"text contains \'tail-proof\'"}', tmp_path, task)
    final = _fr(tail) or tail
    assert 'tail-proof' in json.dumps(final['items'], ensure_ascii=False)
    assert calls == [URL]
    app = _run('[sense:crawl]{url:"' + URL + '"}', tmp_path, task, channel='app')
    assert 'tail-proof' in json.dumps(app, ensure_ascii=False) and not app.get('_preview')
    assert calls == [URL]


def test_long_single_row_and_nested_body_are_bounded_without_mutating_source():
    row_error = {'_error': '수집 실패: ' + ('구체적인 오류 ' * 100),
                 'truncations': [{'scope': 'source', 'source': URL, 'retained': 10, 'total': 100}]}
    raw = {'items': [{'url': URL, 'body': {'text': TEXT}, **row_error}], 'truncated': True,
           'truncations': [{'scope': 'source', 'source': 'external'}]}
    shown = preview_envelope(raw, policy={'prose_chars': 300})
    assert len(shown['items'][0]['body']['text']) == 300
    assert shown['items'][0]['url'] == URL and raw['items'][0]['body']['text'] == TEXT
    assert all(shown['items'][0][k] == v for k, v in row_error.items())
    assert truncation_evidence(shown)['truncations'] == raw['truncations']


def test_idiom_reads_tail_in_same_program_without_refetch(crawl):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from idiom_experiment_worker import run_trial
    from idiom_experiment_cases import decoded
    crawler, calls = crawl
    code = ('$목록=[{url:"' + URL + '"},{url:"' + URL + '"}]; '
            '[fn:주소마다읽기]{목록:$목록,개수:2} '
            '>> [table:filter]{where:"text contains \'tail-proof\'"}')
    trial = run_trial(code, 'dedup', source_results={URL: lambda p: crawler.crawl_website(**p)})
    assert trial['result']['success'], trial
    final = decoded(trial['result']['final_result'])
    assert 'tail-proof' in json.dumps(final['items']) and calls == [URL]
    assert not truncation_evidence(trial['result'])


def test_pdf_extraction_preserves_long_text(crawl, monkeypatch):
    crawler, calls = crawl
    response = type('PDF', (), {'content': b'%PDF fixture'})()
    monkeypatch.setattr(crawler, '_pdf_reader', lambda *a: json.dumps(
        {'success': True, 'text': TEXT, 'metadata': {}, 'total_pages': 20}))
    monkeypatch.setattr(crawler, '_crawl_static', lambda url, cap:
        crawler._extract_pdf_response(response, url, url, cap, 'static'))
    raw = crawler.crawl_website(URL)
    assert raw['success'] and raw['text'] == TEXT and not raw['truncated']


def test_browser_extraction_preserves_long_text(crawl, monkeypatch):
    import asyncio
    crawler, calls = crawl
    class Driver:
        _tab_id = 'fixture'
        async def call_tool(self, name, params):
            return {'text': TEXT if name == 'get_page_text' else '시험 제목'}
    async def no_sleep(*a):
        pass
    monkeypatch.setattr(crawler.asyncio, 'sleep', no_sleep)
    monkeypatch.setattr(crawler, '_crawl_static', lambda *a: {'success': False})
    monkeypatch.setattr(crawler, '_get_chrome_driver', Driver)
    monkeypatch.setattr(crawler, '_run_async', asyncio.run)
    raw = crawler.crawl_website(URL)
    assert raw['success'] and 'tail-proof' in raw['text'] and not raw['truncated']


def test_refresh_failure_is_not_hidden_by_cached_success(crawl, monkeypatch):
    crawler, calls = crawl
    crawler.crawl_website(URL)
    monkeypatch.setattr(crawler, '_crawl_website_impl', lambda *a:
        {'success': False, 'error': 'network failed'})
    out = crawler.crawl_website(URL, refresh=True)
    assert not out['success'] and out['error'] == 'network failed'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
