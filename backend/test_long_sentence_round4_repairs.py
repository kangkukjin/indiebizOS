"""Input specialization must preserve guards, and diagnostics their cause."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'docs/experiments/long_sentence_imagination/round_4'


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


@pytest.mark.parametrize('body', [
    'return $it.a == null ? "-" : text($it.a)',
    '[if:$it.a == null]{return "-"};return text($it.a)',
    'return $it.a != null ? f"${$it.a}" : "-"',
    'return $it.a != null and number($it.a) > 0 ? text($it.a) : "-"',
    'return $it.a == null or number($it.a) > 0 ? "-" : "negative"',
])
@pytest.mark.parametrize('rows', [[{'a': None}], [{'a': None}, {'a': 3}], [{'a': 3}]])
def test_guarded_specialization(registry, body, rows):
    code = '$x >> [table:each]{' + body + '}'
    plan = compile_program(code, registry, {'x': rows})
    assert not plan.issues, plan.issues
    result = Runtime(plan, {'x': rows}).run()
    assert result['success'], result
    expected = ['-' if r['a'] is None or ' or ' in body else '3' for r in rows]
    assert result['value'] == expected


@pytest.mark.parametrize('code,inputs,diagnostic', [
    ('return text($x)', {'x': None}, 'TYPE'),
    ('return $x == null ? text($x) : "-"', {'x': None}, 'TYPE'),
    ('return $x == null ? "-" : text($missing)', {'x': None}, 'UNBOUND'),
    ('return $x == null ? "-" : text({bad:1})', {'x': None}, 'TYPE'),
    ('return $x == null ? "-" : unknown_builtin($x)', {'x': None}, 'BUILTIN'),
    ('$v=$x == null ? "-" : text($x);return text($x)', {'x': None}, 'TYPE'),
    ('return $x != null ? number($x) : 0', {'x': {}}, 'ARITHMETIC'),
])
def test_impossible_value_does_not_hide_source_errors(registry, code, inputs, diagnostic):
    assert diagnostic in {i['code'] for i in compile_program(code, registry, inputs).issues}


def test_bottom_join_and_nested_discrimination(registry):
    from ibl_v2_types import NEVER, TEXT, join, declared
    assert join(NEVER, TEXT) == join(TEXT, NEVER) == TEXT
    with pytest.raises(ValueError):
        declared('Never')  # internal analysis only
    code = ('return $x.ok ? text($x.value) : text($x.error)')
    plan = compile_program(code, registry, {'x': {'ok': True, 'value': 2}})
    assert not plan.issues, plan.issues
    assert Runtime(plan, {'x': {'ok': True, 'value': 2}}).run()['value'] == '2'


def test_one_diagnostic_per_impure_expression(registry):
    code = (FIXTURE / 'repro/pure_expr_triple.ibl').read_text()
    issues = compile_program(code, registry).issues
    assert len(issues) == 1 and issues[0]['code'] == 'PURE_EXPRESSION'
    assert 'reduce(' in issues[0]['hint'] and '$변환' in issues[0]['hint']
    two = 'return [unique([1] >> [table:each]{return $it}),len([2] >> [table:each]{return $it})]'
    assert len(compile_program(two, registry).issues) == 2


def test_function_diagnostic_and_executable_predicate_hint(registry):
    code = (FIXTURE / 'repro/pure_fn_in_lambda.ibl').read_text()
    issues = compile_program(code, registry).issues
    assert len(issues) == 1 and '순수 효과여도' in issues[0]['message']
    assert '람다를 반환' in issues[0]['hint']
    code = ('[def:큰가]($기준){return ($r)=>$r.n > $기준};'
            '$술어=[fn:큰가]{기준:2};'
            'return [{n:1},{n:5}] >> [table:filter]{where:$술어}')
    plan = compile_program(code, registry)
    assert not plan.issues, plan.issues
    assert Runtime(plan).run()['value'] == [{'n': 5}]
    code = 'return unique(reduce([{p:"a"},{p:"b"}],[],($acc,$r)=>$acc+[$r.p]))'
    plan = compile_program(code, registry)
    assert not plan.issues, plan.issues
    assert Runtime(plan).run()['value'] == ['a', 'b']


@pytest.mark.parametrize('query', ['["one","two"]', '"one,two"', '$queries'])
def test_batch_does_not_borrow_single_search_observation(registry, query):
    code = '$r=[sense:search]{queries:' + query + '};return $r.items >> [table:each]{return $it.query}'
    plan = compile_program(code, registry, {'queries': ['one', 'two']})
    assert not plan.issues, plan.issues
    assert not [w for w in plan.preflight['warnings'] if w['code'] == 'UNOBSERVED_FIELD']


def test_observation_coordinates_keep_valid_typo_warnings(registry, monkeypatch):
    import ibl_access
    monkeypatch.setattr(ibl_access, '_return_shapes', lambda: {
        'sense:search': {'kind': 'items', 'keys': ['title', 'url']}})
    code = '$r=[sense:search]{query:"one"};return $r.items >> [table:each]{return $it.typo}'
    plan = compile_program(code, registry)
    assert any(w['code'] == 'UNOBSERVED_FIELD' for w in plan.preflight['warnings'])
    # A dynamic source also changes shape; removing its marker would borrow ddg.
    code = code.replace('query:"one"', 'query:"one",source:$source')
    plan = compile_program(code, registry, {'source': 'naver'})
    assert not any(w['code'] == 'UNOBSERVED_FIELD' for w in plan.preflight['warnings'])


@pytest.mark.parametrize('variant', [False, True])
def test_original_full_render_and_new_partial_source(tmp_path, variant):
    # Same whole P3 program, synthetic extraction input; no model or network.
    payload = {'검색어': ['synthetic'], '원천': [], '추출': []}
    for version in ['3.13', '3.14']:
        missing = variant and version == '3.14'
        payload['원천'].append({'버전': version, 'ok': not missing,
            'url': 'https://example.org/' + version, '찾은경로': None if missing else 'synthetic',
            '적중': 1, '생략': 0, '이유': '404' if missing else None, '문단수': 0 if missing else 1})
        payload['추출'].append({'버전': version, '실패': [], '버림': [],
            '변경': [] if missing else [{'pep': 'PEP 703', '제목': 'sample',
                '분류': '인터프리터·성능', '상태': '실험적' if version == '3.13' else '정식', '문단': 1}]})
    inputs = {'추출': payload, '출력': str(tmp_path / 'notes.md')}
    code = (FIXTURE / 'drafts/p3_v1.ibl').read_text()
    plan = compile_program(code, load_registry(str(tmp_path)), inputs)
    assert not plan.issues, plan.issues
    result = Runtime(plan, inputs).run()
    assert result['success'] and result['value']['저장일치'], result
    text = (tmp_path / 'notes.md').read_text()
    assert ('404' in text) is variant
    assert ('실험적 → 3.14 정식' in text) is not variant


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
