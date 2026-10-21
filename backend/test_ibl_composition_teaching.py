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
# 2026-10-07 분할: 본편(값·함수·병렬) + 도구·문서·재개. 예제는 두 파일에서 모은다.
TOOLS_GUIDE = ROOT / 'data/guides/ibl_composition_tools.md'
GUIDES = (GUIDE, TOOLS_GUIDE)
FRAGMENTS = ROOT / 'data/common_prompts/fragments'
EXAMPLES = dict(pair for guide in GUIDES for pair in re.findall(
    r'<!-- example:(\w+) -->\s*```ibl\n(.*?)\n```', guide.read_text(), re.S))


@pytest.fixture
def current(monkeypatch, tmp_path):
    import ibl_engine
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    calls = []
    (tmp_path / 'outputs').mkdir()
    real_leaf = ibl_engine.execute_ibl
    def leaf(ti, *args, **kwargs):
        if (ti['_node'], ti['action']) in {('table', 'join'), ('table', 'groupby'), ('table', 'dedup'),
                                         ('self', 'time'), ('self', 'list'), ('self', 'read')}:
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


def test_catch_report_preserves_typed_original_without_repeating_work(current):
    out = current(EXAMPLES['catch_json_report'])
    assert out['success'], out
    report = json.loads(out['value']['report_json'])
    original = out['value']['original_error']
    assert report['code'] == original['code'] == 'ASSERTION_FAILED'
    assert report['has_partial'] and not report['partial_preserved']
    assert report['evidence'] == original['evidence']
    assert original['partial'] == [{'$ibl': 'unit'}]
    wire_fields = dict(out['value_wire']['data'][1])
    assert dict(wire_fields['original_error'][1])['partial'] == ['list', [['unit']]]
    assert not current.calls


def test_pipeline_and_new_idiom_composition(current):
    assert current(EXAMPLES['pipeline'])['value'] == [
        {'id': 'b', 'score': 7}, {'id': 'c', 'score': 5}]
    assert current(EXAMPLES['compose'])['value'] == [
        {'id': 'b', 'score': 7, 'weighted': 14},
        {'id': 'c', 'score': 5, 'weighted': 10}]
    assert current(EXAMPLES['compose'].replace('최소:5', '최소:99'))['value'] == []
    assert current(EXAMPLES['builtin_callable'])['value'] == [7, 3]
    assert not current.calls  # 규칙 계산에 숨은 외부 호출 없음


@pytest.mark.parametrize('rows,expected', [
    ('[{id:"a",수량:2,단가:30},{id:"b",수량:1,단가:50}]',
     {'내역': [{'id': 'a', '금액': 60}, {'id': 'b', '금액': 50}], '합계': 110, '예산이내': False}),
    ('[]', {'내역': [], '합계': 0, '예산이내': True}),
    ('[{id:"다른입력",수량:4,단가:25}]',
     {'내역': [{'id': '다른입력', '금액': 100}], '합계': 100, '예산이내': True}),
])
def test_local_decomposition_needs_no_saved_functions_or_adapters(rows, expected):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    code = EXAMPLES['local_decomposition'].replace(
        '[{id:"a",수량:2,단가:30},{id:"b",수량:1,단가:50}]', rows)
    plan = compile_program(code, registry={}, definitions={})
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert out['success'] and out['source_complete'], out
    assert out['value'] == {
        '첫안': expected,
        '둘째안': {'내역': [{'id': 'c', '금액': 80}], '합계': 80, '예산이내': True},
    }


def test_join_time_guide_preserves_unmatched_rows(current):
    out = current(EXAMPLES['join_time'])
    assert out['source_complete'], out
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', out['value']['date'])
    assert out['value']['items'] == [
        {'id': 'a', 'price': 300, 'memo': '역세권'},
        {'id': 'b', 'price': 200, 'memo': '미검토'}]


def test_unary_group_guide_preserves_aggregate(current):
    assert current(EXAMPLES['unary_group'])['value'] == [{'분류': '식비', '합계': 50}]


@pytest.mark.parametrize('empty', [False, True])
def test_group_best_preserves_missing_targets(current, empty):
    code = EXAMPLES['group_best']
    if empty:
        code = re.sub(r'(?m)^\$후보=.*$', '$후보=[]', code)
    out = current(code)
    assert out['success'] and out['source_complete'], out
    assert [row['group'] for row in out['value']] == ['a', 'b', 'c']
    assert [row['choice']['id'] if row['choice'] else None for row in out['value']] == (
        [None, None, None] if empty else ['y', 'z', None])


@pytest.mark.parametrize('names,expected', [
    ([], []),
    (['부산', '부산', '부산'], [0, 0, 0]),
    (['e\u0301', 'é', 'E', 'e'], [0, 0, 1, 2]),
    (['A', 'a', ' A', '01', '1', ''], [0, 1, 2, 3, 4, 5]),
])
def test_record_key_aliases_keep_source_spelling_and_business_identity(current, names, expected):
    code = EXAMPLES['record_key_aliases']
    code = code.replace('["부산","부산","A","a"]', json.dumps(names, ensure_ascii=False))
    out = current(code)
    assert out['success'] and out['source_complete'], out
    value = out['value']
    assert list(value['aliases']) == list(dict.fromkeys(names))
    assert [value['aliases'][name] for name in names] == expected
    assert len(value['names']) == len(set(expected))
    assert not current.calls


def test_loop_accumulation_guide_uses_the_current_iteration_index(current):
    assert current(EXAMPLES['loop_accumulate'])['value'] == ['기초', '실습', '심화']


@pytest.mark.parametrize('left,right,expected', [
    ({'id': 'A', 'tokens': 3}, {'tokens': 3, 'id': 'A'}, True),
    ({'id': 'A'}, {'id': 'a'}, False),
    ({'id': '01'}, {'id': '1'}, False),
    ({'id': ' A'}, {'id': 'A'}, False),
    ({'id': 'é'}, {'id': 'e\u0301'}, False),
    ({'tokens': 3}, {'tokens': '3'}, False),
    ({'tokens': 1}, {'tokens': True}, False),
    ({'value': None}, {}, False),
    ({'A': 1}, {'a': 1}, False),
    ({}, {}, True),
])
def test_flat_record_identity_ignores_order_but_preserves_source_values(
        current, left, right, expected):
    code = EXAMPLES['flat_record_identity'].replace(
        'a:{id:"A",tokens:3},b:{tokens:3,id:"A"}',
        'a:' + json.dumps(left, ensure_ascii=False)
        + ',b:' + json.dumps(right, ensure_ascii=False))
    result = current(code)
    assert result['success'] and result['source_complete'], result
    assert result['value'] is expected


@pytest.mark.parametrize('rows', [
    [],
    [{'id': 'A', 'n': 1}, {'id': 'a', 'n': 2}, {'id': 'A', 'n': 3}],
    [{'id': key, 'n': i} for i, key in enumerate(['01', '1', '', 'é', 'e\u0301', '01'])],
])
def test_exact_key_groups_keep_all_rows_and_raw_ids(current, rows):
    code = EXAMPLES['exact_key_groups'].replace(
        '[{id:"A",n:1},{id:"a",n:2},{id:"A",n:3}]',
        json.dumps(rows, ensure_ascii=False))
    result = current(code)
    assert result['success'] and result['source_complete'], result
    expected = {}
    for row in rows:
        expected.setdefault(row['id'], []).append(row)
    assert result['value'] == expected
    assert list(result['value']) == list(expected)


def test_empty_and_failure_are_distinct(current):
    assert current(EXAMPLES['empty'])['value'] == [{'status': '대상 없음'}]
    present = EXAMPLES['empty'].replace('$후보 = []', '$후보 = [{id:"a"}]')
    assert current(present)['value'] == [{'id': 'a'}]
    caught = current(EXAMPLES['catch'])
    assert caught['value'] == {'status': '원문 확인 실패', 'reason': '원문 실패'}
    assert any(e['kind'] == 'recovered' for e in caught['evidence'])


def test_record_field_pipeline_executes_without_hoisting(current):
    from ibl_v2_compile import compile_program
    empty = '$목록=[]; return {apps:($목록 >> [table:filter]{where:($행)=>true})}'
    assert current(empty)['value'] == {'apps': []}
    contains_example = EXAMPLES['container_record'].replace(
        '$행.url == "https://example.org/board"', 'contains($행.url,"board")')
    assert 'BUILTIN' not in [i['code'] for i in compile_program(contains_example).issues]
    assert current(contains_example)['value'] == {'apps':[{'url':'https://example.org/board'}]}
    assert current(EXAMPLES['container_record'])['value'] == {
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
    assert all(len(guide.read_bytes()) <= 36000 for guide in GUIDES)
    assert len(compact) <= 4200


def test_full_prompt_local_functions_execute_without_saved_definitions():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    examples = re.findall(r'```ibl\n(.*?)\n```', (FRAGMENTS / '12_ibl_only.md').read_text(), re.S)
    assert len(examples) == 1
    plan = compile_program(examples[0], registry={}, definitions={})
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert out['success'], out
    assert out['value'] == [{'id': '007', 'weighted': 21}, {'id': 'b', 'weighted': 15}]


def test_guide_is_reachable_from_actual_prompt_and_old_links():
    from ibl_access import build_environment
    from ibl_routing import _search_guide
    for query in ('ibl_composition.md', 'ibl_v2.md', 'ibl_v2'):
        guide = _search_guide(query, {'read': True})
        assert guide['match'] == 'filename' and guide['content'] == GUIDE.read_text()
    tools = _search_guide('ibl_composition_tools.md', {'read': True})
    assert tools['match'] == 'filename' and tools['content'] == TOOLS_GUIDE.read_text()
    # 상시 프롬프트는 본편만 가리킨다 — 둘째 파일은 본편 머리말이 잇는다(상시 조각을 늘리지 않는다).
    assert 'read_guide(query="ibl_composition_tools.md")' in GUIDE.read_text().split('## ')[0]
    assert '(ibl_composition.md)' in TOOLS_GUIDE.read_text().split('## ')[0]
    assert 'ibl_v2' not in [g['id'] for g in _search_guide('', {})['guides']]
    for compact in (True, False):
        prompt = build_environment(allowed_set={'table', 'self'},
                                   expose_idioms=False, compact=compact)
        assert 'read_guide(query="ibl_composition.md")' in prompt
    assert set(EXAMPLES) == {'pipeline', 'container_record', 'compose', 'empty', 'catch', 'catch_json_report', 'retry', 'chunk', 'join_time', 'unary_group', 'loop_accumulate', 'builtin_callable', 'optional_file', 'local_decomposition', 'document_completion', 'value_revision', 'pure_list_transform', 'group_best', 'record_key_aliases', 'flat_record_identity', 'exact_key_groups'}
    assert sum(len(re.findall(r'```ibl\n', guide.read_text())) for guide in GUIDES) == len(EXAMPLES)
    assert {'join_time', 'unary_group', 'document_completion'} == set(
        re.findall(r'<!-- example:(\w+) -->', TOOLS_GUIDE.read_text()))


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


# 업무 교재도 표시된 실행 예제를 같은 컴파일러에 통과시킨다. 설명용 조각은 포함하지 않는다.
DOMAIN_GUIDES = ('goal', 'trigger', 'sheet', 'ai_words', 'judgment', 'body',
                 'document_edit', 'member_start', 'web_search')
DOMAIN_EXAMPLES = dict(pair for name in DOMAIN_GUIDES for pair in re.findall(
    r'<!-- example:(\w+) -->\s*```ibl\n(.*?)\n```',
    (ROOT / 'data/guides' / (name + '.md')).read_text(), re.S))


@pytest.fixture
def domain_runtime(monkeypatch, tmp_path):
    import ibl_engine
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_edition import source_context
    calls = []
    def leaf(ti, *args, **kwargs):
        node, action, params = ti['_node'], ti['action'], ti['params']
        calls.append((node, action, params))
        if (node, action) == ('self', 'trigger'):
            if params['op'] == 'create':
                return {'success': True, 'trigger': {'id': 'trg_actual'}}
            if params['op'] == 'list':
                return {'success': True, 'items': [
                    {'name': 'one', 'enabled': True, 'last_run': None, 'run_count': 0},
                    {'name': 'off', 'enabled': False, 'last_run': None, 'run_count': 0}]}
            if params['op'] == 'history':
                return {'success': True, 'items': [{'success': False}, {'success': True}]}
            return {'success': True, 'items': []}
        if (node, action) == ('self', 'read'):
            return {'success': True, 'text': '원문 $변수 \"인용\"', 'blocks': [],
                    'table': {'columns': ['품목', '단가'], 'rows': [['A', 30], ['B', 10]]}}
        if (node, action) in {('self', 'write'), ('self', 'sheet')}:
            return {'success': True, 'path': params['path']}
        raise AssertionError(f'예기치 않은 외부 호출: {node}:{action}')
    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    registry = load_registry(str(tmp_path))
    def execute(name):
        plan = compile_program(DOMAIN_EXAMPLES[name], registry)
        assert not plan.issues, plan.report()
        with source_context(2):
            out = Runtime(plan).run()
        assert out['success'], out
        return out
    execute.registry, execute.calls = registry, calls
    return execute


@pytest.mark.parametrize('name', list(DOMAIN_EXAMPLES))
def test_domain_teaching_compiles_without_external_effects(name, domain_runtime):
    from ibl_v2_compile import compile_program
    plan = compile_program(DOMAIN_EXAMPLES[name], domain_runtime.registry)
    assert not plan.issues, plan.report()
    assert domain_runtime.calls == []


def test_trigger_teaching_passes_real_id_and_preserves_explicit_inputs(domain_runtime):
    domain_runtime('trigger_lifecycle')
    calls = domain_runtime.calls
    created = next(p for _, a, p in calls if a == 'trigger' and p['op'] == 'create')
    assert created['inputs'] == {'알림': '아침 확인'}
    assert '$알림' in created['pipeline']
    assert all(p['trigger_id'] == 'trg_actual' for _, a, p in calls
               if a == 'trigger' and p['op'] in ('detail', 'history', 'update', 'disable'))


def test_file_copy_teaching_passes_text_instead_of_document_envelope(domain_runtime):
    domain_runtime('member_copy')
    writes = [p for _, a, p in domain_runtime.calls if a == 'write']
    assert len(writes) == 1
    assert writes[0]['content'] == '원문 $변수 \"인용\"'


def test_pdf_teaching_converts_columns_and_rows_to_sheet_records(domain_runtime):
    domain_runtime('sheet_pdf_rows')
    append = next(p for _, a, p in domain_runtime.calls if a == 'sheet')
    assert append['items'] == [{'품목': 'A', '단가': 30}, {'품목': 'B', '단가': 10}]


@pytest.mark.parametrize('name,expected', [
    ('goal_condition', {'판단': '방어 전략 검토', '관측': 2350}),
    ('goal_case', '추가 비교'), ('goal_repeat', 3),
])
def test_goal_teaching_runs_current_control_grammar(domain_runtime, name, expected):
    assert domain_runtime(name)['value'] == expected
    assert not domain_runtime.calls


def test_teaching_budget_matches_runtime_contract():
    from ibl_v2_runtime import Budget
    full = (FRAGMENTS / '12_ibl_only.md').read_text()
    compact = (FRAGMENTS / '12_ibl_compact.md').read_text()
    defaults = re.search(r'기본 (\d+)만 계산 단계·(\d+)만 반복 행·함수 깊이 (\d+)', full)
    maxima = re.search(r'최대 ([\d,]+)만/(\d+)만', compact)
    budget = Budget()
    assert (int(defaults[1]) * 10000, int(defaults[2]) * 10000, int(defaults[3])) == (
        budget.steps, budget.rows, budget.depth)
    assert (int(maxima[1].replace(',', '')) * 10000, int(maxima[2]) * 10000) == (
        Budget.REQUEST_LIMITS['steps'], Budget.REQUEST_LIMITS['rows'])
    assert budget.seconds is None and '프로그램 전체의 기본 시간 제한은 없음' in full


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
