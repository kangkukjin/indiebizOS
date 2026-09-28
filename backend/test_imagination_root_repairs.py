"""Round 67–71 root contracts: exact identity, source coverage and atomic values.

All storage, concurrent mutations and external page responses are isolated.
"""
import boot_paths  # noqa: F401
import importlib.util
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import pack, unpack
from ibl_v2_runtime import Runtime
from common.value_semantics import (values_equal, compare_order, equality_bucket,
                                    relation_identity, group_identity, sort_records)

ROOT = Path(__file__).resolve().parents[1]


def run_value(source, registry=None):
    result = Runtime(compile_program(source, registry)).run()
    assert result['success'], result
    return unpack(result['value_wire']['data'])


@pytest.mark.parametrize('a,b', [('0.10000000000000001', '0.1'),
                               ('9007199254740993.0', '9007199254740992.0')])
def test_numeric_identity_matches_exact_arithmetic(a, b):
    result = run_value(f'$a={a}; $b={b}; return {{eq:$a==$b,gt:$a>$b,'
                       'diff:$a-$b,n:len(unique([$a,$b])),rows:sorted([$a,$b])}')
    assert result['eq'] is False and result['gt'] is True
    assert result['diff'] == Decimal(a) - Decimal(b) and result['n'] == 2
    assert result['rows'] == [Decimal(b), Decimal(a)]
    assert sort_records([{'n': Decimal(a)}, {'n': Decimal(b)}], 'n')[0]['n'] == Decimal(b)
    assert relation_identity(Decimal(a)) != relation_identity(Decimal(b))


def test_numeric_identity_mixed_representations_share_buckets():
    representations = [Decimal('1.0'), 1, 1.0, '1.000', '01', '1e0']
    for a in representations:
        for b in representations:
            assert values_equal(a, b) and compare_order(a, b) == 0
            assert equality_bucket(a) == equality_bucket(b)
            assert relation_identity(a) == relation_identity(b)
    assert values_equal(Decimal('.1'), .1)
    assert group_identity(Decimal('1.0')) == group_identity(1)
    assert not values_equal(True, 1)


def test_exact_comparison_preserves_persisted_float_group_keys():
    from common.pkg_utils import load_sibling
    handler = ROOT / 'data/packages/installed/tools/data-ops/handler.py'
    module = load_sibling(str(handler), 'dataops_value_semantics')
    for number in [0.1, 1.0, 1e20, 1e-20]:
        # Existing since ledgers encode float group identities as JSON numbers.
        old = '\x1ejson:' + json.dumps(('list', (('number', number),)), separators=(',', ':'))
        assert module.persistent_keys([number])[0] == old


@pytest.fixture
def molit():
    path = ROOT / 'data/packages/installed/tools/real-estate/realty_molit_common.py'
    spec = importlib.util.spec_from_file_location('root_repair_molit', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('cap', [1, 999, 1000, 1500, 2500, 5001, None])
def test_pages_cover_one_contiguous_selection(molit, monkeypatch, cap):
    total, requests = 6000, []
    def response(url):
        q = parse_qs(urlparse(url).query)
        size, page = int(q['numOfRows'][0]), int(q['pageNo'][0])
        requests.append((page, size))
        start = (page - 1) * size
        body = ''.join(f'<item><id>{i}</id></item>' for i in range(start, min(start + size, total)))
        return f'<response><resultCode>000</resultCode><totalCount>{total}</totalCount><items>{body}</items></response>'
    monkeypatch.setattr(molit, '_get', response)
    result = molit.fetch_month_paged('https://example.invalid', '', 'x', '202601', cap,
                                     lambda row, month: int(row.findtext('id')))
    limit = min(cap or 5000, 5000)
    assert result['rows'] == list(range(limit))
    assert len({size for _, size in requests}) == 1
    assert result['truncations'][0]['scope'] == ('selection' if cap and cap <= 5000 else 'source')


def test_second_page_failure_preserves_source_error(molit, monkeypatch):
    replies = iter(['<response><resultCode>000</resultCode><totalCount>3</totalCount>'
                    '<items><item><id>1</id></item></items></response>',
                    '<response><resultCode>999</resultCode><resultMsg>unavailable</resultMsg></response>'])
    monkeypatch.setattr(molit, '_get', lambda _: next(replies))
    result = molit.fetch_month_paged('https://example.invalid', '', 'x', '202601', 3, lambda row, month: 1)
    assert result['error'] and result['truncations'][0]['scope'] == 'source'


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    import model_result_view as view
    from supervision_store import TurnStore
    store = TurnStore(tmp_path)
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    return store, view


def envelope(value):
    return {'edition': 2, 'success': True, 'value': value,
            'value_wire': {'protocol': 'ibl-value/1', 'data': pack(value)}}


@pytest.mark.parametrize('state', ['old', 'missing', 'corrupt', 'mismatched'])
def test_uncertified_evidence_is_readable_but_not_an_input(evidence, state):
    store, view = evidence
    value = json.dumps(envelope({'memo': 'already ****'}))
    if state == 'old':
        from supervision_store import digest
        key = digest(value)
        (store.directory / (key + '.txt')).write_text(value)
        (store.directory / (key + '.masked.json')).write_text('[]')
    else:
        key = store.evidence(value)['id']
        cert = store.directory / (key + '.evidence.json')
        if state == 'missing':
            cert.unlink()
        elif state == 'corrupt':
            cert.write_text('{')
        else:
            (store.directory / (key + '.txt')).write_text(json.dumps(envelope('modified')))
    assert store.read_evidence(key)['integrity'] == 'unknown'
    assert view.read_result({'id': key})['input_unavailable']
    with pytest.raises(ValueError, match='원형 보존'):
        view.resolve_input_refs({'x': {'$ref': key}})


def test_atomic_certificate_publication_fails_closed(evidence, monkeypatch):
    store, view = evidence
    ready, release = threading.Event(), threading.Event()
    publish = store._publish_evidence
    def paused(name, text):
        if name.endswith('.evidence.json'):
            ready.set()
            assert release.wait(10)
        publish(name, text)
    monkeypatch.setattr(store, '_publish_evidence', paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(store.evidence, json.dumps(envelope('original')))
        try:
            assert ready.wait(10)
            key = next(store.directory.glob('*.txt')).stem
            with pytest.raises(ValueError):
                view.resolve_input_refs({'x': {'$ref': key}})
        finally:
            release.set()
        ref = pending.result(timeout=10)
    assert view.resolve_input_refs({'x': {'$ref': ref['id']}})[0]['x'] == 'original'


def test_transformation_facts_participate_in_content_identity(evidence):
    store, view = evidence
    secret = '와이파이 비밀번호는 cafe2026guest 입니다'
    masked = store.evidence(json.dumps(envelope(secret), ensure_ascii=False))
    displayed = store.read_evidence(masked['id'], 0, None)['text']
    clean = store.evidence(displayed)
    assert clean['id'] != masked['id']
    with pytest.raises(ValueError):
        view.resolve_input_refs({'x': {'$ref': masked['id']}})
    assert view.resolve_input_refs({'x': {'$ref': clean['id']}})[0]['x'].endswith('**** 입니다')


def test_typed_json_looking_strings_have_same_read_and_input_shape(evidence):
    store, view = evidence
    ref = store.evidence(json.dumps(envelope({'memo': '[1, 2]'})))
    page = view.read_result({'id': ref['id'], 'path': ['value', 'memo']})
    assert page['text'] == '[1, 2]' and page['read_scope']['format'] == 'text'
    assert view.resolve_input_refs(page['input_args'])[0]['입력'] == page['text']
    with pytest.raises(ValueError):
        view.read_result({'id': ref['id'], 'path': ['value', 'memo', 0]})


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def test_parallel_file_aliases_use_runtime_identity(registry, tmp_path):
    a = tmp_path / 'a.txt'
    link = tmp_path / 'alias.txt'
    link.symlink_to(a)
    from runtime_utils import file_resource_identity
    for b in [str(tmp_path) + '/./a.txt', str(link)]:
        source = '[self:write]{path:%s,content:"A"} & [self:write]{path:%s,content:"B"}' % (json.dumps(str(a)), json.dumps(b))
        plan = compile_program(source, registry)
        assert any(i['code'] == 'PARALLEL_WRITE_CONFLICT' for i in plan.issues)
        assert file_resource_identity(a) == file_resource_identity(b)
    assert not a.exists()


@pytest.mark.parametrize('dead', [
    '[def:f](){ return "done"; [self:write]{path:"a.txt",content:"A"} }; [fn:f]{}',
    '([] >> [table:each]{parallel:2}{ [self:write]{path:"a.txt",content:"A"} })',
    '[def:f](){ [repeat:0]{ [self:write]{path:"a.txt",content:"A"} } }; [fn:f]{}',
])
def test_unreachable_writes_do_not_conflict(registry, dead):
    plan = compile_program(dead + ' & [self:write]{path:"a.txt",content:"B"}', registry)
    assert not plan.issues, plan.report()


def test_static_concatenation_keeps_resource_identity(registry):
    source = '$p="a"+".txt"; [self:write]{path:$p,content:"A"} & [self:write]{path:"a.txt",content:"B"}'
    assert any(i['code'] == 'PARALLEL_WRITE_CONFLICT' for i in compile_program(source, registry).issues)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
