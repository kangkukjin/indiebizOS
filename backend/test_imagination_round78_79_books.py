"""상상훈련 78·79회차 잔여: 정보나루 날 요청 에코(B78-6)·고전DB 검색어 무시(형제)·별칭 표 한 벌(B79-8)·
정수 값 인덱스와 INDEX 진단(F79-3). 네트워크·실제 저장소에 닿지 않는다(원천 응답은 실측 모양의 fixture)."""
import boot_paths  # noqa: F401
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.expression_ir import unpack
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ROOT / 'data/packages/installed/tools/books'


def module(name):
    spec = importlib.util.spec_from_file_location('r7879_books_' + name, BOOKS / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 2026-09-29 실측 모양(정보나루 srchBooks): 요청 에코는 날 문자, 본문 칸은 CDATA.
def naru_xml(echo_title):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="no"?><response><request>'
            f'<title>{echo_title}</title><sort>loan_count</sort><pageNo>1</pageNo><pageSize>3</pageSize>'
            '</request><numFound>22</numFound><docs><doc><bookname><![CDATA[<자리표> R&D 전략 ]]></bookname>'
            '<isbn13><![CDATA[9790000000000]]></isbn13></doc></docs></response>')


@pytest.mark.parametrize('title', ['R&D 전략', '<하네스>', 'A & <B> > C'])
def test_naru_raw_request_echo_is_not_a_parse_failure(monkeypatch, title):
    lib = module('tool_library')
    sent = {}

    def fake_call(service, path, params=None, **_):
        sent.update(params)
        return naru_xml(params['title'])

    monkeypatch.setattr(lib, 'check_api_key', lambda _: (True, None))
    monkeypatch.setattr(lib, 'api_call', fake_call)
    out = lib.search_books(title=title, page_size=3)
    assert 'error' not in out, out
    assert out['count'] == 22 and out['data'][0]['isbn13'] == '9790000000000'
    assert out['data'][0]['title'].startswith('<자리표> R&D')   # 본문 CDATA 는 건드리지 않는다
    assert sent['title'] == title


def test_naru_echo_escape_touches_only_the_echo():
    lib = module('tool_library')
    raw = naru_xml('R&D')
    fixed = lib._escape_request_echo(raw, {'title': 'R&D', 'pageNo': 1})
    assert '<title>R&amp;D</title>' in fixed and '<![CDATA[<자리표> R&D 전략 ]]>' in fixed


def test_naru_transformed_echo_falls_back_to_dropping_the_echo():
    lib = module('tool_library')
    # 원천이 값을 바꿔 되실어도(정확 이스케이프 빗나감) 에코 구간만 빼고 본문은 읽는다.
    root = lib.parse_xml_response(naru_xml('R&D  전략'), {'title': 'R&D 전략'})
    assert root.find('.//numFound').text == '22'


def test_naru_broken_body_is_source_parse_not_input():
    lib = module('tool_library')
    out = lib.parse_xml_response('<response><numFound>1</numFound><docs><doc>', {'title': 'x'})
    assert out['success'] is False and out['error_type'] == 'source_parse'
    assert '원천' in out['error']


def classics_xml(echo, docs=''):
    return (f"<?xml version='1.0' encoding='utf-8' ?><response><header><field name='secId'></field>"
            f"<field name='keyword'>{echo}</field><field name='totalCount'>2</field></header>"
            f"<result>{docs}</result></response>").encode('utf-8')


def test_korean_classics_sends_keyword_and_reads_rows(monkeypatch):
    mod = module('tool_korean_classics')
    seen = {}
    doc = ("<doc><field name='서명'>문집</field><field name='기사명'>기(記)</field><field name='권차명'>제3권</field>"
           "<field name='검색필드'>앞 &lt;em class=&quot;hl1&quot;&gt;말&lt;/em&gt; 뒤</field>"
           "<field name='자료ID'>ITKC_X_1</field></doc>")

    def fake_get(url, params=None, timeout=None):
        seen.update(params)
        return SimpleNamespace(status_code=200, content=classics_xml('R&amp;D', doc))

    monkeypatch.setattr(mod.requests, 'get', fake_get)
    out = mod.search_korean_classics('R&D', rows=2)
    assert seen == {'keyword': 'R&D', 'rows': 2}           # 옛 query= 는 원천이 무시했다
    row = out['results'][0]
    assert row['title'] == '문집' and row['article'] == '기(記)' and row['volume'] == '제3권'
    assert row['content_snippet'] == '앞 말 뒤'


def test_korean_classics_ignored_query_is_not_success(monkeypatch):
    mod = module('tool_korean_classics')
    monkeypatch.setattr(mod.requests, 'get',
                        lambda *a, **k: SimpleNamespace(status_code=200, content=classics_xml('')))
    out = mod.search_korean_classics('이황')
    assert out['success'] is False and out['error_type'] == 'source_changed'


# ---- B79-8 별칭 표 한 벌 ----

@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def run(code, registry):
    plan = compile_program(code, registry)
    return plan, (None if plan.issues else Runtime(plan).run())


def action(node, name):
    from ibl_registry import load_nodes_installed
    return load_nodes_installed()['nodes'][node]['actions'][name]


@pytest.mark.parametrize('flag', ['desc', 'descending'])
def test_sort_descending_alias_is_one_table_in_edition_2(registry, flag):
    plan, result = run('[table:sort]{items:[{a:1},{a:3},{a:2}], by:"a", ' + flag + ':true}', registry)
    assert not plan.issues, plan.report()
    assert unpack(result['value_wire']['data']) == [{'a': 3}, {'a': 2}, {'a': 1}]


def test_sort_alias_and_canonical_together_is_refused(registry):
    plan, _ = run('[table:sort]{items:[{a:1}], by:"a", desc:true, descending:false}', registry)
    assert plan.issues


def test_projection_matches_retired_hand_written_tables():
    from ibl_v2_contracts import declared_contract
    assert declared_contract(action('table', 'sort'))['aliases'] == {'desc': 'descending'}
    # 판본 2 가 이름을 바꾼 자리(root_path→path)도 같은 규칙으로 나온다 — 손으로 쓴 두 번째 표는 은퇴.
    assert declared_contract(action('self', 'grep'))['aliases'] == {
        'root_path': 'path', 'query': 'pattern', 'max_results': 'limit'}
    assert declared_contract(action('sense', 'search'))['aliases'] == {
        'count': 'limit', 'display': 'limit', 'page_size': 'limit', 'max_results': 'limit',
        'front_page': 'headlines'}


def test_gate_flags_second_alias_table_and_contradiction():
    from ibl_v2_contracts import alias_projection
    config = copy.deepcopy(action('table', 'sort'))
    config['callable_contract']['aliases'] = {'desc': 'by'}
    _, problems = alias_projection(config['callable_contract'], config)
    assert problems and '두 벌' in problems[0] and 'desc→descending' in problems[0]


def test_build_gate_reports_second_table_and_contract_only_keys(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    from iblbuild_v2 import validate_v2_contracts
    sort = copy.deepcopy(action('table', 'sort'))
    sort['callable_contract']['aliases'] = {'desc': 'descending'}          # 두 번째 표
    sort['callable_contract']['params']['reverse_order'] = 'Bool'          # 판본 1 이 모르는 계약 인자
    issues = validate_v2_contracts({'nodes': {'table': {'actions': {'sort': sort}}}})
    assert any('두 벌' in i for i in issues), issues
    assert any('reverse_order' in i and '판본 1' in i for i in issues), issues


def test_every_contract_vocab_is_accepted_by_edition_1():
    from ibl_param_vocab import vocab_outside_allowed
    from ibl_registry import load_nodes_installed
    leaks = {f'{n}:{a}': sorted(vocab_outside_allowed(n, a, cfg))
             for n, nd in load_nodes_installed()['nodes'].items()
             for a, cfg in (nd.get('actions') or {}).items()
             if cfg.get('callable_contract') and vocab_outside_allowed(n, a, cfg)}
    assert not leaks


def test_warning_never_suggests_the_unknown_key_itself():
    from ibl_param_vocab import check_params
    config = copy.deepcopy(action('table', 'sort'))
    assert check_params('table', 'sort', {'by': 'a', 'descending': True}, config) is None
    assert check_params('table', 'sort', {'by': 'a', 'desc': True}, config) is None
    # 옛 모양 재현: 계약만 아는 키(스키마·aliases 밖) — 모른다면서 그 키를 권하지 않는다.
    config['callable_contract']['params']['reverse_order'] = 'Bool'
    warn = check_params('table', 'sort', {'by': 'a', 'reverse_order': True}, config)
    assert warn['unknown'] == ['reverse_order']
    assert warn['suggest'].get('reverse_order') != 'reverse_order'
    assert "'reverse_order'" not in warn['message'].split('주요 키')[-1]


# ---- F79-3 정수 값 인덱스·INDEX 진단 ----

@pytest.mark.parametrize('code,expected', [
    ('return [10,20,30][3/3]', 20),
    ('return [10,20,30][round(1.6, 0)]', 30),
    ('return [10,20,30][7 // 3]', 30),
    ('return [10,20,30][0:4/2]', [10, 20]),
    ('return "abc"[round(0.4)]', 'a'),
])
def test_integer_valued_numbers_index(registry, code, expected):
    plan, result = run(code, registry)
    assert not plan.issues, plan.report()
    assert result['success'], result
    assert unpack(result['value_wire']['data']) == expected


def test_round_digits_accept_integer_valued_number(registry):
    _, result = run('return round(3.14159, 4/2)', registry)
    assert str(unpack(result['value_wire']['data'])) == '3.14'


def diagnostic(code, registry):
    plan, result = run(code, registry)
    assert not plan.issues, plan.report()
    assert not result['success']
    return result['diagnostic']


def test_index_diagnostic_splits_fraction_from_range(registry):
    frac = diagnostic('$xs=[10,20,30]\nreturn $xs[1.5]', registry)
    assert frac['code'] == 'INDEX' and '정수' in frac['message']
    assert frac['details'] == {'index': '1.5', 'index_type': 'Number', 'length': 3, 'variable': 'xs'}
    out = diagnostic('$xs=[10,20,30]\nreturn $xs[round(2.7, 0)]', registry)
    assert '범위' in out['message'] and out['details']['index'] == 3 and out['details']['length'] == 3
    bad = diagnostic('$pos = get({k:true}, "k", null)\nreturn [1,2,3][$pos]', registry)   # 정적 검사는 리터럴 Bool 을 먼저 막는다
    assert bad['details']['index_type'] == 'Bool'


def test_arithmetic_table_in_teaching_matches_runtime(registry):
    text = (ROOT / 'data/common_prompts/fragments/12_ibl_only.md').read_text(encoding='utf-8')
    for code, expected in [('2 * 3', '6'), ('7 / 2', '3.5'), ('7 // 2', '3'), ('7 % 3', '1')]:
        assert f'`{code}` → {expected}' in text
        _, result = run(f'return {code}', registry)
        assert str(unpack(result['value_wire']['data'])) == expected
    assert '`2 ** 0.5` → 1.414' in text
    _, result = run('return 2 ** 0.5', registry)
    assert str(unpack(result['value_wire']['data'])).startswith('1.414')


def test_edition_1_routing_carries_desc_to_the_canonical_key():
    from ibl_routing import _normalize_param_aliases
    params = _normalize_param_aliases('table', 'sort', {'by': 'a', 'desc': True}, action('table', 'sort'))
    assert params['descending'] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
