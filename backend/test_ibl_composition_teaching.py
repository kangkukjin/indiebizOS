"""교재 코드 자체를 실제 파서·함수·table 실행기로 검사. 웹만 고정 응답."""
import json
import re
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from api_ibl import validate_code
from test_idiom_composition_2026_09_07 import run  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / 'data/guides/ibl_composition.md'
FRAGMENTS = ROOT / 'data/common_prompts/fragments'
EXAMPLES = dict(re.findall(
    r'<!-- example:(\w+) -->\s*```ibl\n(.*?)\n```', GUIDE.read_text(), re.S))


@pytest.fixture
def current(monkeypatch, tmp_path):
    import ibl_engine
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    calls = []
    real_leaf = ibl_engine.execute_ibl
    def leaf(ti, *args, **kwargs):
        if (ti['_node'], ti['action']) in {('table', 'join'), ('table', 'groupby'), ('self', 'time')}:
            return real_leaf(ti, *args, **kwargs)
        assert (ti['_node'], ti['action']) == ('sense', 'crawl')
        url = ti['params']['url']
        calls.append(url)
        if url.endswith('/bad') and not (execute.recover and calls.count(url) == 2):
            return {'success': False, 'error': '원문 실패'}
        return {'success': True, 'text': '원문', 'title': '문서', 'url': url,
                'items': [{'text':'원문', 'url':url, 'paragraph_index':0}]}
    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    registry = load_registry(str(tmp_path))
    seeds = json.loads((ROOT / 'data/idioms/ibl_v2_seeds.json').read_text())
    definitions = {e['alias']: e['ibl_code'] for e in seeds if e.get('alias')}
    def execute(code):
        from ibl_edition import source_context
        plan = compile_program(code, registry, definitions=definitions)
        assert not plan.issues, plan.report()
        with source_context(2):
            return Runtime(plan).run()
    execute.calls, execute.recover = calls, False
    return execute


@pytest.mark.parametrize('name', list(EXAMPLES))
def test_guide_programs_execute(name, current):
    out = current(EXAMPLES[name])
    assert out['success'], out


def test_pipeline_and_new_idiom_composition(current):
    assert current(EXAMPLES['pipeline'])['value'] == [
        {'id': 'b', 'score': 7}, {'id': 'c', 'score': 5}]
    assert current(EXAMPLES['compose'])['value'] == [
        {'id': 'b', 'score': 7, 'weighted': 14},
        {'id': 'c', 'score': 5, 'weighted': 10}]
    assert current(EXAMPLES['compose'].replace('최소:5', '최소:99'))['value'] == []
    assert not current.calls  # 규칙 계산에 숨은 외부 호출 없음


def test_join_time_guide_preserves_unmatched_rows(current):
    out = current(EXAMPLES['join_time'])
    assert out['source_complete'], out
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', out['value']['date'])
    assert out['value']['items'] == [
        {'id': 'a', 'price': 300, 'memo': '역세권'},
        {'id': 'b', 'price': 200, 'memo': '미검토'}]


def test_unary_group_guide_preserves_aggregate(current):
    assert current(EXAMPLES['unary_group'])['value'] == [{'분류': '식비', '합계': 50}]


def test_loop_accumulation_guide_uses_the_current_iteration_index(current):
    assert current(EXAMPLES['loop_accumulate'])['value'] == ['기초', '실습', '심화']


def test_empty_and_failure_are_distinct(current):
    assert current(EXAMPLES['empty'])['value'] == [{'status': '대상 없음'}]
    present = EXAMPLES['empty'].replace('$후보 = []', '$후보 = [{id:"a"}]')
    assert current(present)['value'] == [{'id': 'a'}]
    caught = current(EXAMPLES['catch'])
    assert caught['value'] == {'status': '원문 확인 실패', 'reason': '원문 실패'}
    assert any(e['kind'] == 'recovered' for e in caught['evidence'])


def test_record_field_pipeline_is_rejected_and_hoisted_example_executes(current):
    from ibl_v2_compile import compile_program
    invalid = '$목록=[]; return {apps:($목록 >> [table:filter]{where:($행)=>true})}'
    assert 'PURE_EXPRESSION' in [issue['code'] for issue in compile_program(invalid).issues]
    invalid_contains = EXAMPLES['pure_record'].replace(
        '$행.url == "https://example.org/board"', 'contains($행.url,"board")')
    assert 'BUILTIN' in [issue['code'] for issue in compile_program(invalid_contains).issues]
    assert current(EXAMPLES['pure_record'])['value'] == {
        'apps': [{'url': 'https://example.org/board'}]}


@pytest.mark.parametrize('recover', [False, True])
def test_retry_only_failed_row_and_preserve_unresolved_failure(current, recover):
    current.recover = recover
    out = current(EXAMPLES['retry'])
    assert current.calls.count('https://example.org/one') == 1
    assert current.calls.count('https://example.org/bad') == 2
    assert [r['id'] for r in out['value']] == ['a', 'b']
    assert ('error' in out['value'][1]) is not recover
    assert not out['source_complete']  # 복구해도 앞선 실패 증거는 지우지 않는다.


@pytest.mark.parametrize('count', [0, 3, 130])
def test_chunk_covers_empty_and_more_than_old_default_each_limit(current, count):
    rows = [{'index': i, 'text': '가나'} for i in range(count)]
    code = re.sub(r'(?m)^\$덩이 = .*$', lambda _: '$덩이 = ' + json.dumps([rows]), EXAMPLES['chunk'])
    out = current(code)
    assert out['value'] == [{**r, 'chars': 2} for r in rows]


def test_compact_example_is_executable_and_bounded(current):
    compact = (FRAGMENTS / '12_ibl_compact.md').read_text()
    examples = re.findall(r'```ibl\n(.*?)\n```', compact, re.S)
    assert len(examples) == 1
    assert current(examples[0])['value'] == [{'id': 'a', 'total': 6}]
    empty = examples[0].replace('[{id:"a",qty:2}]', '[]')
    assert current(empty)['value'] == []
    assert len((FRAGMENTS / '12_ibl_only.md').read_bytes()) <= 36000
    assert len(GUIDE.read_bytes()) <= 36000
    assert len(compact) <= 4200


def test_guide_is_reachable_from_actual_prompt_and_old_links():
    from ibl_access import build_environment
    from ibl_routing import _search_guide
    for query in ('ibl_composition.md', 'ibl_v2.md', 'ibl_v2'):
        guide = _search_guide(query, {'read': True})
        assert guide['match'] == 'filename' and guide['content'] == GUIDE.read_text()
    assert 'ibl_v2' not in [g['id'] for g in _search_guide('', {})['guides']]
    for compact in (True, False):
        prompt = build_environment(allowed_set={'table', 'self'},
                                   expose_idioms=False, compact=compact)
        assert 'read_guide(query="ibl_composition.md")' in prompt
    assert set(EXAMPLES) == {'pipeline', 'pure_record', 'compose', 'empty', 'catch', 'retry', 'chunk', 'join_time', 'unary_group', 'loop_accumulate'}
    assert len(re.findall(r'```ibl\n', GUIDE.read_text())) == len(EXAMPLES)


@pytest.mark.parametrize('body,side_effect,ai_call', [
    ('[table:take]{items:[],n:1}', False, False),
    ('[self:write]{path:"never-written.txt",content:"x"}', True, False),
    ('[table:brief]{items:[{text:"x"}],instruction:"요약"}', False, True),
])
def test_validation_sees_function_effects_without_execution(body, side_effect, ai_call):
    out = validate_code('[def:f]{' + body + '}; [fn:f]{}')
    assert out['valid'], out
    assert out['has_side_effect'] is side_effect
    assert out['has_ai_call'] is ai_call


def test_validation_resolves_function_inside_each_and_catches_unknown_action():
    code = '[def:f]{[table:take]{items:[{id:1}],n:1}}; [table:each]{items:[{}]}{[fn:f]{}}'
    out = validate_code(code)
    assert out['valid'] and not out['has_side_effect'], out
    assert not validate_code(code.replace('table:take', 'table:no_such_action'))['valid']
    assert not validate_code('[def:f]{todo};[fn:f]{}')['valid']
    recursive = validate_code('[def:f]{[fn:f]{}};[fn:f]{}')
    assert recursive['has_side_effect']
    assert any('상한' in row['effect'] for row in recursive['steps'])


def test_validation_does_not_invent_effects_for_unused_definition():
    out = validate_code('[def:unused]{[self:write]{path:"never-written.txt",content:"x"}};'
                        '[table:take]{items:[],n:1}')
    assert out['valid'] and not out['has_side_effect'], out


@pytest.mark.parametrize('raw', [
    '[table:take]{items:[],n:1}',
    ['[table:take]{items:[],n:1}'],
    [{'_node': 'table', 'action': 'take', 'params': {'items': [], 'n': 1}}],
])
def test_validation_accepts_saved_workflow_body_shapes(monkeypatch, raw):
    import workflow_store
    monkeypatch.setattr(workflow_store, 'get_workflow', lambda name: {'steps': raw})
    out = validate_code('[fn:saved]{}')
    assert out['valid'] and not out['has_side_effect'], out


def test_validation_honors_workflow_before_idiom(run, monkeypatch):
    import workflow_store
    monkeypatch.setattr(workflow_store, 'get_workflow',
                        lambda name: {'problem': '몸통 손상'})
    out = validate_code('[fn:정렬해추리기]{}')
    assert not out['valid']
    assert '몸통 손상' in out['steps'][0]['error']
    monkeypatch.setattr(workflow_store, 'get_workflow', lambda name: None)
    assert not validate_code('[fn:no_such_function]{}')['valid']


@pytest.mark.parametrize('all_failed', [False, True])
def test_retry_with_zero_or_all_failures(current, all_failed):
    code = EXAMPLES['retry']
    if all_failed:
        code = code.replace('/one', '/bad')
    else:
        code = code.replace('/bad', '/two')
    out = current(code)
    assert len(out['value']) == 2
    assert sum('error' in row for row in out['value']) == (2 if all_failed else 0)
    assert len(current.calls) == (4 if all_failed else 2)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
