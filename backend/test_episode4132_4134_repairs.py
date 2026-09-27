"""Authoring recovery and guide failure transport; no live web/model requests."""
import json
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'data/packages/installed/tools/web/handler.py'


def test_parallel_pipe_diagnostic_and_explicit_grouping():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    prefix = '[def:id]($x){return $x}\n'
    bad = compile_program(prefix + '1 >> [fn:id]{} & 2 >> [fn:id]{}', {})
    issue = next(i for i in bad.report()['issues'] if i['code'] == 'PIPE_TARGET')
    assert issue['actual'] == 'parallel'
    assert '(A >> B) & (C >> D)' in issue['hint']
    assert Runtime(bad).run()['executed'] is False
    good = compile_program(prefix + '(1 >> [fn:id]{}) & (2 >> [fn:id]{})', {})
    assert not good.issues
    assert Runtime(good).run()['value'] == [1, 2]
    combined = compile_program(prefix + '(1 & 2) >> [fn:id]{}', {})
    assert Runtime(combined).run()['value'] == [1, 2]


def test_non_parallel_pipe_does_not_suggest_unrelated_parentheses():
    from ibl_v2_compile import compile_program
    issue = next(i for i in compile_program('1 >> 2', {}).report()['issues']
                 if i['code'] == 'PIPE_TARGET')
    assert 'actual' not in issue and '(A >> B)' not in issue['hint']


@pytest.mark.parametrize('section,code', [
    ('검색', 'GUIDE_SECTION_NOT_FOUND'), ('중복', 'GUIDE_SECTION_AMBIGUOUS'),
])
def test_guide_recovery_arguments_select_real_sections_without_stale_hash(section, code):
    from guide_registry import guide_read_view
    source = {'file': 'test.md', 'content':
              '# Root\nIntro\n## 1. 검색\nActual\n## 중복\nA\n## 중복\nB\n'}
    first = guide_read_view(source, {})
    out = guide_read_view(source, {'section': section, 'if_hash': first['content_hash']})
    assert out['success'] is False and out['code'] == code
    assert 'content' not in out
    assert out['read_args'] == {'query': 'test.md', 'read': True}
    assert guide_read_view(source, out['read_args'])['content'] == source['content']
    assert out['section_reads']
    for args in out['section_reads']:
        assert 'if_hash' not in args and args['section'] != '중복'
        selected = guide_read_view(source, args)
        assert 'content' in selected and not selected.get('error')
    assert source['content'] == first['content']


def test_guide_recovery_is_bounded_and_missing_section_stays_error():
    from guide_registry import guide_read_view
    source = {'file': 'test.md', 'content': '\n'.join(f'## Part {i}\nText' for i in range(20))}
    out = guide_read_view(source, {'section': 'Part'})
    assert out['success'] is False and 'content' not in out
    assert len(out['section_reads']) == 8 and out['section_reads_omitted'] == 12


@pytest.mark.parametrize('payload,error', [
    ({'success': False, 'error': 'missing section', 'read_args': {'query': 'test.md'}}, True),
    ({'error': 'guide file missing'}, True),
    ({'content': 'error: this is documentation'}, False),
    ({'unchanged': True, 'content_hash': 'same'}, False),
    ({'guides': [], 'count': 0}, False),
])
def test_guide_mcp_protocol_and_codex_failure_accounting(monkeypatch, tmp_path, payload, error):
    import anyio
    import mcp_server
    from mcp.types import CallToolResult
    from providers.codex import CodexProvider
    from supervision_store import TurnStore
    from ibl_result_transport import tool_result_is_error
    raw = json.dumps(payload, ensure_ascii=False)
    monkeypatch.setattr(mcp_server, '_post_backend', lambda *a, **kw: raw)

    async def call():
        return await mcp_server.mcp.call_tool('read_guide', {'query': 'test.md'})

    response = anyio.run(call)
    if isinstance(response, CallToolResult):
        wire = response.model_dump()
    else:
        content = response[0] if isinstance(response, tuple) else response
        wire = {'content': [block.model_dump() for block in content], 'isError': False}
    text, failed = CodexProvider._tool_result(
        {'type': 'mcp_tool_call', 'status': 'completed', 'result': wire})
    assert failed is error and json.loads(text) == payload
    assert tool_result_is_error(raw) is error  # direct provider has the same verdict
    store = TurnStore(tmp_path)
    store.log('tool.finished', is_error=failed)
    assert store.cost['execution_calls'] == 1
    assert store.cost['execution_failures'] == int(error)


def test_search_warning_and_correction_survive_model_transport(monkeypatch, tmp_path):
    from common.pkg_utils import load_sibling
    import model_result_view as view
    from ibl_result_transport import provider_tool_result, tool_result_is_error
    from supervision_store import TurnStore
    monkeypatch.setattr(view, 'evidence_store', lambda: TurnStore(tmp_path))
    handler = load_sibling(WEB, 'handler')
    seen = []
    rows = [{'title': f'row {i}', 'summary': 'evidence ' * 1000} for i in range(30)]

    def execute(args, context):
        seen.append(dict(args))
        return json.dumps({'success': True, 'items': rows, 'warning': 'existing warning'})

    monkeypatch.setattr(handler, '_execute', execute)
    args = {'queries': ['site.nccih.nih.gov depression', 'site:cochrane.org depression']}
    out = json.loads(handler.execute(args, SimpleNamespace(tool_name='search')))
    assert seen == [args] and out['items'] == rows and out['success'] is True
    assert 'existing warning' in out['warning']
    assert out['query_notes'][0]['suggested_query'] == 'site:nccih.nih.gov depression'
    assert len(out['query_notes']) == 1
    shown = view.project_v2_result({'edition': 2, 'success': True, 'value': out})
    delivered = provider_tool_result(json.dumps(shown, ensure_ascii=False))
    assert not tool_result_is_error(delivered)
    assert 'site:가 아닌 표기' in delivered
    assert 'site:nccih.nih.gov depression' in delivered


@pytest.mark.parametrize('query', [
    'site:example.org text', '"site.example.org" text',
    'https://site.example.org', 'text site.example.org',
])
def test_literal_or_valid_site_queries_remain_untouched(query):
    from common.pkg_utils import load_sibling
    assert load_sibling(WEB, 'web_search_io').query_notes({'query': query}) == []


def test_uncertain_site_prefix_is_not_given_a_guessed_correction():
    from common.pkg_utils import load_sibling
    note = load_sibling(WEB, 'web_search_io').query_notes({'query': 'site2.gov.bc.ca text'})[0]
    assert 'suggested_query' not in note


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
