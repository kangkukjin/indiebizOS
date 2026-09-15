"""41~50위 어휘의 입력·실패·원장 보존 회귀. 외부 호출은 대역, 파일은 임시 경로."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'data/packages/installed/tools'


def load(package, name='handler'):
    path = PKG / package / (name + '.py')
    spec = importlib.util.spec_from_file_location('rank41_' + package.replace('-', '_') + name, path)
    mod = importlib.util.module_from_spec(spec)
    old_path = sys.path[:]
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = old_path
    return mod


@pytest.mark.parametrize('op', ['nearby', 'webcam'])
def test_cctv_limit_reaches_provider(monkeypatch, op):
    mod = load('cctv')
    calls = []

    def provider(lat, lng, count=5):
        calls.append((lat, lng, count))
        return {'items': []}

    monkeypatch.setitem(mod._OP_DISPATCHERS['cctv_query'], op, provider)
    mod._cctv_query(op=op, lat=0, lng=0, limit=2)
    assert calls == [(0, 0, 2)]


@pytest.mark.parametrize('op', ['profile', 'financials', 'disclosures'])
def test_company_corp_code_selects_dart(monkeypatch, op):
    mod = load('investment')
    calls = []
    api = SimpleNamespace(**{name: lambda **kw: calls.append(kw) or {'success': True, 'data': {}}
                             for name in ['get_company_info', 'get_financial_statements', 'get_disclosures']})

    def provider(name):
        assert name == 'tool_dart'
        return api

    monkeypatch.setattr(mod, 'load_module', provider)
    mod._OP_DISPATCHERS['company_op'][op]({'corp_code': '00126380'})
    assert calls[0]['corp_code'] == '00126380'


@pytest.mark.parametrize('query', ['005930', '005930.KS', '005930.ks'])
def test_company_stock_code_resolves_exactly(monkeypatch, query):
    mod = load('investment', 'tool_dart')
    monkeypatch.setattr(mod, '_load_corp_codes', lambda: {
        '삼성전자서비스': {'corp_code': 'other', 'stock_code': ''},
        '삼성전자': {'corp_code': '00126380', 'stock_code': '005930'}})
    assert mod._find_corp_code(query) == ('00126380', '삼성전자', None)


@pytest.mark.parametrize('content', ['{broken', '[]', '{"folders": "oops"}'])
def test_showcase_corrupt_state_is_preserved(tmp_path, monkeypatch, content):
    mod = load('public-files')
    path = tmp_path / 'state.json'
    path.write_text(content)
    monkeypatch.setattr(mod, '_STATE_PATH', path)
    monkeypatch.setattr(mod, '_DATA_DIR', tmp_path)
    out = json.loads(mod.execute({'op': 'basket_save', 'title': 'test'}, SimpleNamespace(tool_name='showcase_op')))
    assert out['success'] is False
    assert path.read_text() == content


@pytest.mark.parametrize('body, success', [
    ('<html><head><title>Maintenance</title></head><body>offline</body></html>', False),
    ('<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>', True),
])
def test_feed_html_is_not_empty_feed(monkeypatch, body, success):
    mod = load('web')
    monkeypatch.setattr(mod, '_read_feed', lambda url: mod.feedparser.parse(body))
    assert mod._fetch_feed({'url': 'https://fixture.test/feed'})['success'] is success


@pytest.mark.parametrize('limit', [0, -1, 'invalid'])
def test_feed_limit(monkeypatch, limit):
    mod = load('web')
    feed = mod.feedparser.parse('<rss version="2.0"><channel><title>T</title><item><title>A</title></item></channel></rss>')
    monkeypatch.setattr(mod, '_read_feed', lambda url: feed)
    result = mod._fetch_feed({'url': 'https://fixture.test/feed', 'limit': limit})
    assert result['success'] is (limit == 0)
    assert result['items'] == []


@pytest.mark.parametrize('verdict', [[], {}, {'passed': 'false', 'score': 8, 'issues': []},
                                    {'passed': True, 'score': 99, 'issues': []},
                                    {'passed': True, 'score': 8, 'issues': 'bad'}])
def test_image_critic_rejects_malformed_verdict(monkeypatch, verdict):
    mod = load('media_producer', 'vision_read')
    monkeypatch.setattr(mod, '_load_image_b64', lambda p: ({'base64': 'AA==', 'media_type': 'image/png'}, None))
    monkeypatch.setattr(mod, '_ai_call', lambda *a, **kw: json.dumps(verdict))
    out = json.loads(mod.critique_image({'image_path': '/fixture.png', 'intent': 'test'}, '.'))
    assert out['success'] is False


def test_image_critic_provenance_is_runtime_owned(monkeypatch):
    mod = load('media_producer', 'vision_read')
    monkeypatch.setattr(mod, '_load_image_b64', lambda p: ({}, None))
    monkeypatch.setattr(mod, '_ai_call', lambda *a, **kw: json.dumps(
        {'passed': False, 'score': 2, 'issues': ['cut off'], 'tier': 'prescreen', 'rubric': 'fake'}))
    out = mod.critique_image({'image_path': '/fixture.png', 'intent': 'test'}, '.')
    verdict = json.loads(out.split('verdict_json:', 1)[1])
    assert verdict['tier'] == 'vision' and verdict['rubric'].startswith('preset:general')


@pytest.mark.parametrize('content', ['[]', 'hello', ''])
def test_workflow_invalid_row_does_not_break_list(tmp_path, monkeypatch, content):
    import workflow_store as mod
    monkeypatch.setattr(mod, '_get_workflows_path', lambda: tmp_path)
    (tmp_path / 'bad.yaml').write_text(content)
    rows = mod.list_workflows()
    assert rows[0]['runnable'] is False and rows[0]['problem']


def test_workflow_rejects_path_escape_and_symlink(tmp_path, monkeypatch):
    import workflow_store as mod
    folder = tmp_path / 'workflows'
    folder.mkdir()
    monkeypatch.setattr(mod, '_get_workflows_path', lambda: folder)
    outside = tmp_path / 'outside.yaml'
    outside.write_text('name: outside\nsteps: []\n')
    (folder / 'link.yaml').symlink_to(outside)
    for key in ('../outside', str(outside.with_suffix('')), 'link'):
        assert mod.get_workflow(key).get('problem')
        assert mod.delete_workflow(key) is False
        with pytest.raises(ValueError):
            mod.save_workflow({'id': key, 'steps': ['[self:time]{}']})
    assert outside.read_text() == 'name: outside\nsteps: []\n'


def test_workflow_failed_replace_preserves_old_file(tmp_path, monkeypatch):
    import workflow_store as mod
    monkeypatch.setattr(mod, '_get_workflows_path', lambda: tmp_path)
    mod.save_workflow({'id': 'test', 'steps': ['[self:time]{}']})
    before = (tmp_path / 'test.yaml').read_bytes()
    monkeypatch.setattr(mod.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError):
        mod.save_workflow({'id': 'test', 'steps': ['new']})
    assert (tmp_path / 'test.yaml').read_bytes() == before
    assert list(tmp_path.glob('.workflow-*')) == []


def test_paper_unknown_source_does_not_search(monkeypatch):
    mod = load('study')
    monkeypatch.setattr(mod, '_search_openalex', lambda *a: pytest.fail('wrong source searched'))
    assert mod._paper_search({'source': 'arxvi', 'query': 'test'}, None)['success'] is False


@pytest.mark.parametrize('body', ['<html>maintenance</html>', '''<feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/api/errors#incorrect_id_format_for_1</id><title>Error</title><summary>Bad id</summary></entry></feed>'''])
def test_paper_arxiv_error_is_not_paper(monkeypatch, body):
    mod = load('study')
    monkeypatch.setattr(mod, '_arxiv_get', lambda *a: SimpleNamespace(text=body, raise_for_status=lambda: None))
    assert mod._search_arxiv({'query': 'test'})['success'] is False


def test_paper_openalex_error_is_not_empty(monkeypatch):
    mod = load('study')
    monkeypatch.setattr(mod.requests, 'get', lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {'error': 'bad request'}))
    assert mod._search_openalex({'query': 'test'})['success'] is False


@pytest.mark.parametrize('routes, success', [
    ([{'result_code': 104, 'result_msg': 'No route'}], False),
    ([{'result_code': 0, 'summary': {'distance': 1000, 'duration': 60}}], True),
])
def test_navigation_checks_route_result(monkeypatch, routes, success):
    mod = load('location-services')
    monkeypatch.setattr(mod, 'check_api_key', lambda *a: (True, None))
    monkeypatch.setattr(mod, '_geocode_place', lambda *a: (127, 37, 'test'))
    monkeypatch.setattr(mod, 'api_call', lambda *a, **kw: {'routes': routes})
    out = mod.kakao_navigation('a', 'b', generate_map=False)
    assert out['success'] is success


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'test.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE "my "" table" ("update" TEXT)')
        conn.execute('INSERT INTO "my "" table" VALUES (?)', ('delete',))
    return str(path)


def test_sqlite_special_path_names_and_literal(database):
    special = Path(database).with_name('a?#%.db')
    Path(database).rename(special)
    database = str(special)
    mod = load('system_essentials', 'sqlite_ops')
    out = mod.op_query({'path': database, 'query': 'SELECT "update", \'drop\' AS text FROM "my "" table"'})
    assert out['success'] and out['items'] == [{'update': 'delete', 'text': 'drop'}]
    assert mod.op_tables({'path': database})['items'] == [{'name': 'my " table', 'rows': 1}]
    assert mod.op_schema({'path': database, 'table': 'my " table'})['items'][0]['name'] == 'update'


@pytest.mark.parametrize('query', ['PRAGMA query_only=OFF', 'PRAGMA writable_schema=ON',
                                  'WITH x AS (SELECT 1) DELETE FROM "my "" table"',
                                  'SELECT 1 AS x, 2 AS x'])
def test_sqlite_denies_mutations_and_column_loss(database, query):
    mod = load('system_essentials', 'sqlite_ops')
    assert mod.op_query({'path': database, 'query': query})['success'] is False


def test_radio_unknown_op_does_not_search(monkeypatch):
    mod = load('radio')
    monkeypatch.setattr(mod, 'load_tool_radio', lambda: SimpleNamespace(search_radio=lambda **kw: pytest.fail('unexpected search')))
    result = mod.execute({'op': 'typo'}, SimpleNamespace(tool_name='radio_search_op'))
    assert result['success'] is False


@pytest.mark.parametrize('data', ['<html>error</html>', {}, {'success': False}, [1]])
def test_radio_invalid_response_is_failure(monkeypatch, data):
    mod = load('radio', 'tool_radio')
    monkeypatch.setattr(mod, 'api_call_raw', lambda *a, **kw: data)
    assert json.loads(mod.search_radio(name='test'))['success'] is False


def test_sqlite_fts_read_and_pragma_table_function(tmp_path):
    mod = load('system_essentials', 'sqlite_ops')
    path = tmp_path / 'fts.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE VIRTUAL TABLE docs USING fts5(body)')
        conn.execute("INSERT INTO docs VALUES ('hello world')")
    result = mod.op_query({'path': str(path), 'query': "SELECT * FROM docs WHERE docs MATCH 'hello'"})
    assert result['success'] and result['items'] == [{'body': 'hello world'}]
    result = mod.op_query({'path': str(path), 'query': "SELECT name FROM pragma_table_info('docs')"})
    assert result['success'] and result['items'] == [{'name': 'body'}]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
