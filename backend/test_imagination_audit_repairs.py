"""1~81회차 재검에서 확인한 경계 결함. 외부 호출·사용자 데이터 쓰기 없음."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'


def module(package, name='handler'):
    spec = importlib.util.spec_from_file_location('audit_' + package.replace('-', '_') + name.replace('/', '_'),
                                                TOOLS / package / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def obj(value):
    return json.loads(value) if isinstance(value, str) else value


@pytest.mark.parametrize('rows', [[], [{'path': '/one'}]])
def test_variable_payload_preserves_empty_currency(rows):
    from workflow_binding import _v4_var_payload
    raw = json.dumps({'success': True, 'annotations': rows, 'items': rows, 'count': len(rows)})
    if rows:  # different nonempty payloads remain a structured envelope by contract
        raw = json.dumps({'success': True, 'items': rows, 'count': len(rows)})
    assert json.loads(_v4_var_payload(raw)) == rows


@pytest.mark.parametrize('args,needle,count', [
    ({'table': {'columns': ['x'], 'rows': [[1], [2]]}}, '최소 2열', 2),
    ({'items': [], 'x': 'name', 'y': 'cpu'}, '입력 0행', 0),
    ({'_prev_result': {'items': []}}, '입력 0행', 0),
    ({'_prev_result': 'today'}, '스칼라', 0),
    ({'data': 3}, '스칼라', 0),
    ({'data': []}, '입력 0행', 0),
])
def test_chart_input_diagnostics(tmp_path, args, needle, count):
    mod = module('visualization')
    ctx = SimpleNamespace(tool_name='chart', output_dir=lambda: str(tmp_path))
    out = obj(mod.execute({'chart_type': 'bar', **args}, ctx))
    assert out['success'] is False and needle in out['error'], out
    assert out['rows_in'] == count
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('block,expected', [
    ({'type': 'table', 'items': [{'a': 1}, {'a': 2, 'b': 'keep'}]}, 'keep'),
    ({'type': 'table', 'items': '[{"a":"keep"}]'}, 'keep'),
    ({'type': 'cards', 'items': [{'a': 'keep'}]}, 'keep'),
])
def test_document_records_are_not_silently_lost(tmp_path, block, expected):
    mod = module('data-ops', 'doc_build')
    out = obj(mod.render_document({'blocks': [block], 'format': 'markdown'}, str(tmp_path)))
    assert out['success'], out
    assert expected in out['markdown']


@pytest.mark.parametrize('block', [{'type': 'table'}, {'type': 'table', 'items': '$missing.items'},
                                   {'type': 'cards', 'items': []}])
def test_unrenderable_document_fails_before_writing(tmp_path, block):
    out = obj(module('data-ops', 'doc_build').render_document({'blocks': [block], 'format': 'markdown'}, str(tmp_path)))
    assert out['success'] is False and 'blocks[0]' in out['error'], out
    assert not list(tmp_path.iterdir())


def test_trigger_rejects_missing_time_before_registration():
    from trigger_engine import resolve_trigger_config
    assert 'interval_hours' in resolve_trigger_config({'config': {'repeat': 'daily', 'interval_hours': 6}})['error']
    for params in ({}, {'config': {}}, {'config': {'repeat': 'daily'}}):
        assert 'time' in resolve_trigger_config(params)['error']
    assert not resolve_trigger_config({'config': {'repeat': 'daily', 'time': '09:00'}}).get('error')


def test_failure_signature_keeps_business_values_and_removes_epoch():
    from calendar_actions import CalendarActionsMixin as C
    one = 'failed {"prepare": {"time": 1790688273.01}, "amount": 123}'
    two = 'failed {"prepare": {"time": 1790691873.92}, "amount": 123}'
    assert C._failure_signature(one) == C._failure_signature(two)
    assert C._failure_signature(one) != C._failure_signature(two.replace('123', '456'))
    task = {}
    assert C._should_notify_result(task, {'error': one}, now=100)
    assert not C._should_notify_result(task, {'error': two}, now=3700)
    assert C._should_notify_result(task, {'error': two}, now=86500)


@pytest.mark.parametrize('endpoint', ['zones', '/zones'])
def test_cloudflare_endpoint_and_currency(monkeypatch, endpoint):
    mod = module('cloudflare', 'tools/api')
    seen = {}
    def request(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(ok=True, status_code=200, json=lambda: {'success': True, 'result': [{'id': 'fixture'}]})
    monkeypatch.setattr(mod.requests, 'request', request)
    out = mod.run({'endpoint': endpoint}, {'api_token': 'fixture'})
    assert seen['url'] == 'https://api.cloudflare.com/client/v4/zones'
    assert out['items'] == [{'id': 'fixture'}]


@pytest.mark.parametrize('sort', ['recent', 'relevance'])
def test_arxiv_plain_terms_are_conjoined(monkeypatch, sort):
    from urllib.parse import urlparse, parse_qs
    mod = module('study')
    seen = {}
    def get(url):
        seen.update(parse_qs(urlparse(url).query))
        return SimpleNamespace(text='<feed xmlns="http://www.w3.org/2005/Atom"></feed>', raise_for_status=lambda: None)
    monkeypatch.setattr(mod, '_arxiv_get', get)
    mod._search_arxiv({'query': 'LLM reasoning limitations', 'sort_by': sort})
    assert seen['search_query'] == ['all:LLM AND all:reasoning AND all:limitations']
    mod._search_arxiv({'query': 'ti:LLM OR ti:reasoning', 'year_from': 2025})
    assert seen['search_query'][0].startswith('(ti:LLM OR ti:reasoning) AND submittedDate:')


def test_history_omitted_limit_preserves_all_observations(monkeypatch):
    from common.response_formatter import compact_price_series
    mod = module('investment')
    seen = {}
    rows = [{'date': str(i), 'close': i} for i in range(100)]
    def price(**kwargs):
        seen.update(kwargs)
        compact, truncated = compact_price_series(rows, kwargs['max_points'])
        return {'success': True, 'data': {'prices': compact, 'total_days': 100, 'truncated': truncated}}
    monkeypatch.setattr(mod, 'load_module', lambda _: SimpleNamespace(get_stock_price=price))
    out = mod._stock_history({'ticker': 'AAPL'})
    assert seen['max_points'] is None
    assert out['items'] == rows and out['truncated'] is False
    selected = mod._stock_history({'ticker': 'AAPL', 'max_points': 10})
    assert len(selected['items']) == 10 and selected['truncations'][0]['scope'] == 'selection'


@pytest.mark.parametrize('code,warning', [
    ('$x = 1; [if: $x > 0]{$k = 10}[else]{$k = 20}; [table:take]{items:[{v:"$k"}],n:1}', False),
    ('$x = 1; [if: $x > 0]{$k = 10}; [table:take]{items:[{v:"$k"}],n:1}', True),
    ('[try]{$k = 10}[catch]{$k = 20}; [table:take]{items:[{v:"$k"}],n:1}', False),
])
def test_definite_branch_assignment(code, warning):
    from ibl_typecheck import typecheck_code
    report = typecheck_code(code)
    assert any('분기 몸' in i['message'] for i in report['issues']) is warning, report


def test_legacy_check_refuses_unknown_action():
    from ibl_typecheck import typecheck_code
    report = typecheck_code('[sense:nosuchaction]{}')
    assert report['ok'] is False, report


def test_else_retains_observed_value(monkeypatch):
    import ibl_executors as e
    monkeypatch.setattr(e, '_run_branch', lambda *args: {'success': True})
    out = e._execute_condition({'branches': [{'condition': '5 > 10', 'action': {}},
                                            {'condition': None, 'action': {'fixture': True}}]}, str(ROOT), '')
    assert out['matched'] == 'else' and out['matched_value'] == 5


def test_copy_list_pipeline_executes(tmp_path):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    source = tmp_path / 'source'; source.mkdir()
    (source / 'a.pdf').write_text('fixture')
    dest = tmp_path / 'dest'
    code = '[self:list]{path:' + json.dumps(str(source)) + ',pattern:"*.pdf"} >> [self:copy]{dest:' + json.dumps(str(dest)) + '}'
    out = Runtime(compile_program(code, load_registry(str(tmp_path)))).run()
    assert out['success'], out
    assert (dest / 'a.pdf').read_text() == 'fixture'


def test_nl_imprint_is_normalized_without_losing_source(monkeypatch):
    from urllib.parse import quote_plus
    mod = module('books', 'tool_nl')
    raw = {'T1': '책', 'PB': '서울 : 하다, 20120208', 'YR': '20120208'}
    html = "검색 결과 총 1건 data-refWorks='" + quote_plus(json.dumps(raw)) + "'"
    monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: SimpleNamespace(text=html, raise_for_status=lambda: None))
    row = mod.search_nl('책')['items'][0]
    assert row['publisher'] == '하다' and row['publication_year'] == '2012'
    assert row['publisher_raw'] == raw['PB'] and row['publication_year_raw'] == raw['YR']


def test_commercial_discloses_place_only_interpretation(monkeypatch):
    mod = module('real-estate')
    monkeypatch.setattr(mod, '_geocode_query_to_latlng', lambda _: {'lat': 1, 'lng': 2, 'matched': 'fixture'})
    monkeypatch.setattr(mod, 'load_module', lambda _: SimpleNamespace(search_commercial_district=lambda **k: {'success': True, 'data': []}))
    out = mod.execute({'query': '청주 카페'}, SimpleNamespace(tool_name='search_commercial_district'))
    assert out['query_interpretation']['query'] == '청주 카페'
    assert any('지명으로만' in note for note in out['notes'])


def test_old_notice_signature_is_migrated_on_comparison():
    from calendar_actions import CalendarActionsMixin as C
    task = {'failure_notice': {'error': 'failed {"time":1790688273.01}', 'repeated': 2, 'notified_at': 100}}
    assert not C._should_notify_result(task, {'error': 'failed {"time":1790691873.92}'}, now=3700)
    assert task['failure_notice']['repeated'] == 3


def test_short_summary_does_not_replace_empty_currency():
    from workflow_binding import _v4_var_payload
    assert json.loads(_v4_var_payload(json.dumps({'items': [], 'message': '0건 조회'}))) == []


def test_recurrence_fields_are_not_silently_ignored():
    from calendar_rules import normalize_schedule_config
    for key, value in [('interval_hours', 6), ('weekdays', [1]), ('month', 2), ('day', 5)]:
        result = normalize_schedule_config({'repeat': 'daily', 'time': '09:00', key: value}, executable=True)
        assert key in result['error']


def test_cloudflare_items_contract_keeps_write_effects():
    from ibl_typecheck import typecheck_code
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    code = '[limbs:cloudflare_api]{endpoint:"zones"} >> [table:take]{n:1}'
    assert typecheck_code(code)['ok']
    report = compile_program('$cf=[limbs:cloudflare_api]{endpoint:"zones"}\n'
                             'return $cf.items >> [table:take]{n:1}', load_registry()).report()
    assert report['status'] != 'invalid' and 'write_external' in report['effects']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
