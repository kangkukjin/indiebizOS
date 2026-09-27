"""Native partial recovery, source honesty and search diagnostics from research episodes."""
import json
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling
from supervision_store import TurnStore

WEB = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/web/handler.py'
CHALLENGE = ('A required part of this site couldn’t load. This may be due to a browser '
             'extension, network issues, or browser settings. Please check your connection, '
             'disable any ad blockers, or try using a different browser.')


@pytest.mark.parametrize('suffix', ['', '.pdf'])
def test_http200_challenge_is_failure_and_never_cached(monkeypatch, tmp_path, suffix):
    crawler = load_sibling(WEB, 'tool_webcrawl')
    from common import spill
    monkeypatch.setattr(spill, '_root', lambda: str(tmp_path))
    calls = []
    def get(url):
        calls.append(url)
        html = f'<html><title>Client Challenge</title><body>{CHALLENGE}</body></html>'
        return SimpleNamespace(status_code=200, url=url, content=html.encode(),
                               headers={'content-type': 'text/html'}, encoding='utf-8')
    monkeypatch.setattr(crawler, '_http_get', get)
    monkeypatch.setattr(crawler, '_get_chrome_driver', lambda: None)
    monkeypatch.setattr(crawler, '_get_browser_session', lambda: None)
    for _ in range(2):
        out = crawler.crawl_website('https://source.test/article' + suffix)
        assert out['success'] is False and out['reason'] == 'bot_blocked'
        assert 'source_ref' not in out
        assert not any(s['ran'] for s in out['stages'][1:])
    assert len(calls) == 2


@pytest.mark.parametrize('title,text', [
    ('Client Challenge in web publishing', CHALLENGE + ' This article explains the mechanism.'),
    ('Client Challenge', 'An ordinary article about browsers. ' * 100),
    ('Small actual article', 'Research on building reuse. ' * 12),
])
def test_challenge_mentions_do_not_block_real_articles(title, text):
    crawler = load_sibling(WEB, 'tool_webcrawl')
    assert crawler._diagnose(200, 'https://x.test', 'https://x.test', text, title) is None


@pytest.fixture
def view(monkeypatch, tmp_path):
    import model_result_view
    monkeypatch.setattr(model_result_view, 'evidence_store', lambda: TurnStore(tmp_path / 'evidence'))
    return model_result_view


def read_all(view, request):
    chunks = []
    while request:
        page = view.read_result(request)
        chunks.append(page['text'])
        request = page['next_read']
    return json.loads(''.join(chunks))


def test_real_parallel_partial_keeps_branch_identity_and_full_value_after_transport(view):
    from ibl_v2_adapters import Adapter, Adapted
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_v2_ir import Fault
    from ibl_result_transport import provider_tool_result
    body = 'important evidence\n' * 6000
    values = {'a': {'text': body, 'items': [{'text': body}], 'count': 1},
              'c': {'text': 'small final source', 'items': []}}
    calls = []
    def call(runtime, args):
        calls.append(args['id'])
        if args['id'] == 'b':
            raise Fault('TOOL', 'source blocked')
        return Adapted(values[args['id']], {})
    contract = {'version': 1, 'params': {'id': 'Text'}, 'required': ['id'],
                'result': 'Record', 'effects': ['read_external'],
                'adapter': {'protocol': 'legacy-envelope', 'value_path': ''}}
    plan = compile_program('[sense:source]{id:"a"} & [sense:source]{id:"b"} & [sense:source]{id:"c"}',
                           {'sense:source': Adapter(contract, call)})
    raw = Runtime(plan).run()
    before = json.dumps(raw)
    shown = view.project_v2_result(raw)
    assert json.dumps(raw) == before
    assert not shown['success'] and shown['source_complete'] is False
    assert shown['diagnostic']['details'] == raw['diagnostic']['details']
    assert shown['continuation'] == raw['continuation'] if 'continuation' in raw else True
    assert shown['partial_preview']['scope'] == 'display'
    assert len(json.dumps(shown, ensure_ascii=False)) < 24000
    delivered = json.loads(provider_tool_result(json.dumps(shown, ensure_ascii=False)))
    assert delivered['success'] is False
    reads = delivered['result_ref']['partial_reads']
    assert [(r['branch_index'], r['partial_index']) for r in reads] == [(0, 0), (2, 1)]
    assert read_all(view, reads[0]['text_read_args']) == body
    assert read_all(view, reads[1]['read_args']) == values['c']
    inputs, _ = view.resolve_input_refs(reads[0]['input_args'])
    assert inputs['입력'] == values['a']
    assert len(calls) == 3  # recovery reads never execute the sources again


def test_many_branches_publish_bounded_mapping_with_explicit_omission(view):
    raw = {'edition': 2, 'success': False, 'diagnostic': {
        'has_partial': True, 'partial': [None, 0, [], {'results': 'user data'}] * 5,
        'details': {'successful_indices': list(range(0, 40, 2)), 'coverage': ['ok', 'failed'] * 20}}}
    shown = view.project_v2_result(raw)
    ref = shown['result_ref']
    assert len(ref['partial_reads']) == 6 and ref['partial_reads_omitted'] == 14
    assert read_all(view, ref['partial_mapping_read_args']) == raw['diagnostic']['details']
    for entry in ref['partial_reads']:
        assert read_all(view, entry['read_args']) == raw['diagnostic']['partial'][entry['partial_index']]


def test_unknown_partial_origin_is_not_given_invented_branch_indices(view):
    raw = {'edition': 2, 'success': False, 'diagnostic': {
        'has_partial': True, 'partial': ['large' * 10000], 'details': {}}}
    shown = view.project_v2_result(raw)
    assert 'partial_reads' not in shown['result_ref']
    assert read_all(view, shown['partial_preview']['read_args']) == raw['diagnostic']['partial']


def test_partial_input_uses_typed_wire_not_display_tags(view):
    from decimal import Decimal
    from ibl_v2_ir import UNIT, pack, projection
    values = [Decimal('0.10000000000000000001'), UNIT, 2**80]
    raw = {'edition': 2, 'success': False,
           'partial_wire': {'protocol': 'ibl-value/1', 'data': pack(values)},
           'diagnostic': {'has_partial': True, 'partial': projection(values),
                          'details': {'successful_indices': [0, 2, 3]}}}
    ref = view.project_v2_result(raw)['result_ref']
    resolved = [view.resolve_input_refs(r['input_args'])[0]['입력'] for r in ref['partial_reads']]
    assert resolved == values and resolved[1] is UNIT
    assert isinstance(resolved[0], Decimal)
    raw.pop('partial_wire')
    raw['partial_wire_error'] = {'code': 'VALUE_PROTOCOL_UNSUPPORTED'}
    blocked = view.project_v2_result(raw)['result_ref']
    assert all('input_args' not in r for r in blocked['partial_reads'])
    with pytest.raises(ValueError, match='전송'):
        view.resolve_input_refs({'입력': {'$ref': blocked['id'], 'path': ['diagnostic', 'partial', 0]}})


@pytest.mark.parametrize('queries', [
    ['site.admin.ch demolition', 'site2.gov.bc.ca repair'],
    'site.admin.ch demolition\nsite.oecd.org land',
])
def test_search_notes_reach_caller_without_changing_query_or_results(monkeypatch, queries):
    handler = load_sibling(WEB, 'handler')
    seen = []
    def execute(args, context):
        seen.append(dict(args))
        return json.dumps({'success': True, 'items': [{'title': 'actual result'}]})
    monkeypatch.setattr(handler, '_execute', execute)
    args = {'source': 'ddg', 'queries': queries}
    out = json.loads(handler.execute(args, SimpleNamespace(tool_name='search', project_path='.')))
    assert seen == [args] and out['success']
    assert out['items'] == [{'title': 'actual result'}]
    assert len(out['query_notes']) == 2
    assert all(n['code'] == 'POSSIBLE_SITE_OPERATOR_TYPO' for n in out['query_notes'])


@pytest.mark.parametrize('query', ['site:example.org housing', '"site.example.org" literal',
                                  'https://site.example.org', 'a site.example.org reference'])
def test_valid_operators_and_literal_mentions_are_untouched(query):
    assert load_sibling(WEB, 'web_search_io').query_notes({'query': query}) == []


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
