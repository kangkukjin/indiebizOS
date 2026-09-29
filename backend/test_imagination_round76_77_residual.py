"""상상훈련 76·77회차 잔여 수리 회귀 (2026-09-29). 라이브 서비스 없음.

1b9a4932(72~76)·747d5103(77~81)가 개별 자리를 닫은 뒤 재탐침에서 남은 것:
  · B75-4 재확인(76 T19): 손으로 쓴 callable_contract 가 ops 투영을 못 받아 미지 op 이 check 를 통과하고
    realty 핸들러 폴백이 실거래 성공으로 바꿈 → project_ops 한 벌 + 폴백 제거 + 디스패처 폴백 관문
  · B77-1: 원천별 선택 인자가 check 에 안 보임·arXiv 최신순/연도 미구현 → param_support 선언을 계약 변이로 투영
  · G77-1(언어 개정, 사용자 판정): contains(text, part, exact)
  · F72-2 재확인: count→len 제안, `$x.9월` 안내, INDEX 세부
  · F77-2: 429 → 공통 봉투 → 판본 2 RATE_LIMITED
  · F76-2 재확인: 관측 좌표 축 유도(스키마 enum·param_support·shape_variants), op 모르는 실사용 관측 비대여
  · F77-1 밭 이관: 표시 칸 접기 관문 · F77-3: structure 원문 보존 복원 · B76-4 잔여: 이력 total 상시
"""
import importlib.util
import json
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

from common.expression_ir import Fault
from ibl_v2_adapters import decode_envelope

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'
SCRIPTS = ROOT / 'scripts'
LEGACY = {"protocol": "legacy-envelope", "value_path": ""}


def module(package, name='handler'):
    path = TOOLS / package / (name + '.py')
    spec = importlib.util.spec_from_file_location(f'r7677_{package.replace("-", "_")}_{name}', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def script(name):
    import sys
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return __import__(name)


def check(source):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    return compile_program('#!ibl edition=2\n' + source, load_registry()).report()


def codes(report):
    return [i['code'] for i in report['issues']]


# ── B75-4 재확인: 선언 계약에도 op 허용값 ──

def test_declared_contract_receives_op_enum_and_default():
    from ibl_v2_contracts import declared_contract
    config = {"callable_contract": {"version": 1, "params": {"op": "Unknown", "source": "Unknown"},
                                    "result": "Record", "effects": ["unknown"],
                                    "adapter": {"protocol": "legacy-envelope", "value_path": ""}},
              "ops": {"default": "query", "values": {"query": "", "codes": ""}}, "side_effect": False}
    contract = declared_contract(config)
    assert contract["enums"]["op"] == ["query", "codes"]
    assert contract["defaults"]["op"] == "query"
    assert {v["when"]["op"]: v["effects"] for v in contract["variants"]} == {
        "query": ["read_external"], "codes": ["read_external"]}


def test_unknown_realty_op_is_refused_by_check():
    report = check('return [sense:realty]{op:"registry", region:"청주 흥덕구"}')
    assert 'ARGUMENT_CONTRACT' in codes(report)


def test_realty_handler_refuses_unknown_op():
    mod = module('real-estate')
    ctx = type('C', (), {'tool_name': 'realty_op'})()
    out = mod.execute({'op': 'registry'}, ctx)
    out = json.loads(out) if isinstance(out, str) else out
    assert out['success'] is False and 'registry' in out['error']


def test_dispatcher_fallback_gate_catches_default_function():
    validators = script('iblbuild_validators')
    src = '_OP_DISPATCHERS = {"t": {"a": f}}\ndef execute(i, c):\n    return _OP_DISPATCHERS["t"].get(i["op"], f)(i)\n'
    assert validators._dispatcher_fallbacks(src) == [3]
    assert validators._dispatcher_fallbacks(src.replace(', f)(i)', ')(i)')) == []


# ── B77-1: 원천별 선택 인자 = 조건부 계약 ──

@pytest.mark.parametrize('source,ok', [
    ('return [sense:paper]{query:"x", source:"arxiv", sort_by:"recent", year_from:2026}', True),
    ('return [sense:paper]{query:"x", source:"arxiv", sort_by:"cited"}', False),
    ('return [sense:paper]{query:"x", source:"nanet", open_access:true}', False),
    ('return [sense:paper]{query:"x", source:"s2", year_to:2024}', True),
    ('return [sense:paper]{query:"x", source:"scholar"}', False),
])
def test_paper_source_support_is_visible_to_check(source, ok):
    assert ('ARGUMENT_CONTRACT' not in codes(check(source))) is ok


def test_arxiv_builds_recent_and_date_range_query(monkeypatch):
    mod = module('study')
    seen = {}

    class R:
        status_code, text = 200, '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        def raise_for_status(self):
            pass
    def fake(url, **kw):
        seen['url'] = url
        return R()
    monkeypatch.setattr(mod, '_arxiv_get', fake)
    mod._search_arxiv({'query': 'llm', 'sort_by': 'recent', 'year_from': 2025})
    assert 'sortBy=submittedDate' in seen['url'] and '202501010000' in seen['url']


def test_nanet_year_range_and_structured_type(monkeypatch):
    mod = module('study')
    rows = [{'title': 'A', 'pubYear': '2021', 'divFlag': 'THESIS'}, {'title': 'B', 'pubYear': '2024', 'divFlag': 'ARTICLE'}]
    calls = []
    def fake(*args):
        calls.append(args)
        if len(calls) == 1:
            return {'result': [{'totalCount': 2, 'searchList': rows}]}
        return {'result': [{'error': [{'code': '201', 'message': 'end'}]}]}
    monkeypatch.setattr(mod, '_nanet_call', fake)
    out = mod._search_nanet({'query': 'x', 'limit': 5, 'year_from': 2022})
    assert [(r['title'], r['year'], r['type']) for r in out['items']] == [('B', 2024, 'ARTICLE')]


def test_param_support_declaration_check():
    v2 = script('iblbuild_v2')
    entry = {"params": {"year_from": "integer"}}
    bad = {"axis": "source", "params": ["year_from", "ghost"], "default": "x",
           "values": {"a": {"year_from": "any"}}, "aliases": {"b": "c"}}
    problems = v2._param_support_problems(bad, entry)
    assert any('ghost' in p for p in problems) and any('별칭' in p for p in problems) and any('기본값' in p for p in problems)


# ── G77-1: contains(text, part, exact) ──

def test_contains_exact_is_case_sensitive():
    from common.expression_functions import call
    tick = lambda: None
    assert call('contains', ['painting by John D. Graham', 'AI'], tick) is True
    assert call('contains', ['painting by John D. Graham', 'AI', True], tick) is False
    assert call('contains', ['claim by an AI', 'AI', True], tick) is True
    with pytest.raises(Fault):
        call('contains', ['x', 'x', 'yes'], tick)


# ── F72-2 재확인: 진단 안내 ──

def test_unknown_builtin_suggests_len():
    from common.expression_ops import unknown_builtin_message
    assert 'len' in unknown_builtin_message('count')


def test_digit_field_hint():
    with pytest.raises(Fault) as info:
        check('$x = {a:1}\nreturn $x.9월')
    assert info.value.code == 'SYNTAX' and 'get(' in str(info.value)


# ── F77-2: 429 = RATE_LIMITED ──

def test_rate_limited_envelope_becomes_distinct_code():
    from common.api_client import rate_limited_failure
    raw = rate_limited_failure('Semantic Scholar', retry_after=30, items=[])
    with pytest.raises(Fault) as info:
        decode_envelope(raw, LEGACY)
    assert info.value.code == 'RATE_LIMITED' and info.value.details['retry_after'] == 30
    with pytest.raises(Fault) as plain:
        decode_envelope({'success': False, 'error': 'x'}, LEGACY)
    assert plain.value.code == 'TOOL'


def test_rate_limit_gate_is_clean():
    assert script('iblbuild_rate_limits').validate_rate_limits(ROOT) == []


# ── F76-2 재확인: 관측 좌표 축 ──

def test_shape_axes_derive_from_declarations():
    from ibl_typecheck import shape_axes
    axes = shape_axes({"fixture": '[sense:x]{query: "a"}', "shape_axes": {"source": None},
                       "shape_variants": {"mode=b": "[sense:x]{mode: \"b\"}"},
                       "param_support": {"axis": "db", "default": "one"}})
    assert axes == {"source": None, "mode": None, "db": "one"}


def test_usage_observation_not_lent_across_ops(monkeypatch):
    import ibl_typecheck
    import ibl_access
    monkeypatch.setattr(ibl_access, '_return_shapes', lambda: {'self:thing': {'kind': 'scalar', 'keys': ['material'], 'source': 'usage'}})
    monkeypatch.setattr(ibl_typecheck, '_action_def', lambda n, a: {'ops': {'values': {'add': '', 'list': ''}}})
    assert ibl_typecheck.catalog_entry('self', 'thing', {'op': 'list'}, kinds=('scalar',)) is None


# ── F77-1 밭 이관: 표시 칸 접기 ──

def test_meta_fields_gate_is_clean_and_self_tests():
    gate = script('iblbuild_meta_fields')
    gate._self_test()
    issues, _ = gate.validate_meta_fields(ROOT)
    assert issues == []


# ── F77-3: structure 원문 보존 ──

def test_structure_restores_near_verbatim_titles():
    mod = module('data-ops', 'doc_build')
    content = 'DeepSeek-R1 incentivizes reasoning in LLMs through reinforcement learning. Attention Is All You Need.'
    ir = {'title': '노트', 'blocks': [{'type': 'table', 'columns': ['제목'], 'rows': [
        ['DeepSeek-R1 incentives reasoning in LLMs through reinforcement learning'], ['Attention is all you need']]},
        {'type': 'heading', 'text': '강화학습으로 추론을 유도한다'}]}
    restored = mod._restore_verbatim(ir, content)
    assert [r['to'] for r in restored] == ['DeepSeek-R1 incentivizes reasoning in LLMs through reinforcement learning',
                                          'Attention Is All You Need']
    assert ir['blocks'][1]['text'] == '강화학습으로 추론을 유도한다'


# ── B76-4 잔여·직방 매매가 ──

def test_price_history_total_is_always_present():
    mod = module('investment')
    raw = {'success': True, 'data': {'total_days': 5, 'truncated': False,
                                     'prices': [{'date': '2026-09-2%d' % i, 'close': i} for i in range(5)]}}
    out = mod._attach_price_table(raw)
    assert out['total'] == 5 and out['truncated'] is False


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
