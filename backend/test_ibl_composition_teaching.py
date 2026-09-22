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


@pytest.mark.parametrize('name', list(EXAMPLES))
def test_guide_programs_pass_static_check(name, run):
    out = validate_code(EXAMPLES[name])
    assert out['valid'] and out['typecheck']['ok'], out


def test_pipeline_and_new_idiom_composition(run):
    assert run(EXAMPLES['pipeline'])['items'] == [
        {'id': 'b', 'score': 7}, {'id': 'c', 'score': 5}]
    assert run(EXAMPLES['compose'])['items'] == [
        {'id': 'b', 'score': 7, 'weighted': 14},
        {'id': 'c', 'score': 5, 'weighted': 10}]
    assert run(EXAMPLES['compose'].replace('최소:5', '최소:99'))['items'] == []
    assert run.observed['used']  # 실제 저장 관용구 해소 경로도 사용
    assert not run.observed['brief']  # 규칙 계산에 숨은 AI 호출 없음


def test_empty_and_failure_are_distinct(run):
    assert run(EXAMPLES['empty'])['items'] == [{'status': '대상 없음'}]
    present = EXAMPLES['empty'].replace('items:[]', 'items:[{id:"a"}]')
    assert run(present)['items'] == [{'id': 'a'}]
    caught = run(EXAMPLES['catch'])
    assert caught['items'] == [{'status': '원문 확인 실패'}]
    assert caught['_caught']


@pytest.mark.parametrize('recover', [False, True])
def test_retry_only_failed_row_and_preserve_unresolved_failure(run, monkeypatch, recover):
    import ibl_engine
    original = ibl_engine._execute_ibl_impl
    attempts = []
    diagnostics = []

    def leaf(ti, project, agent=None):
        if ti.get('_node') == 'sense' and ti.get('action') == 'crawl':
            url = ti['params']['url']
            attempts.append(url)
            if recover and url.endswith('/bad') and attempts.count(url) == 2:
                return {'success': True, 'items': [{'text': '회복한 원문'}]}
        result = original(ti, project, agent)
        if ti.get('_node') == 'table' and ti.get('action') == 'each':
            diagnostics.append(json.loads(result) if isinstance(result, str) else result)
        return result

    monkeypatch.setattr(ibl_engine, '_execute_ibl_impl', leaf)
    out = run(EXAMPLES['retry'])
    assert attempts.count('https://example.org/one') == 1
    assert attempts.count('https://example.org/bad') == 2
    assert [r['id'] for r in out['items']] == ['a', 'b']
    assert ('_error' in out['items'][1]) is not recover
    assert diagnostics[0]['error_count'] == 1
    assert diagnostics[0]['errors'][0]['id'] == 'b'


@pytest.mark.parametrize('text', ['', '가나다라마바사아자차카타파하', '가' * 647],
                         ids=['empty', 'three_chunks', '130_chunks'])
def test_chunk_covers_empty_and_more_than_default_each_limit(run, text):
    code = EXAMPLES['chunk'].replace('가나다라마바사아자차카타파하', text)
    rows = run(code)['items']
    assert ''.join(r['text'] for r in rows) == text
    assert [r['index'] for r in rows] == list(range(len(rows)))
    assert all(r['chars'] <= 5 for r in rows)
    assert [r['start'] for r in rows] == list(range(0, len(text), 5))


def test_compact_example_is_executable_and_bounded(run):
    compact = (FRAGMENTS / '12_ibl_compact.md').read_text()
    examples = re.findall(r'```ibl\n(.*?)\n```', compact, re.S)
    assert len(examples) == 1
    check = validate_code(examples[0])
    assert check['valid'] and check['typecheck']['ok'], check
    assert run(examples[0])['items'] == [{'id': 'a', 'total': 6}]
    empty = examples[0].replace('items:[{id:"a",qty:2}]', 'items:[]')
    assert run(empty)['items'] == []
    assert len((FRAGMENTS / "12_ibl_only.md").read_bytes()) <= 36000
    assert len(GUIDE.read_bytes()) <= 36000
    assert len(compact) <= 4200  # 상세 교재를 상시 프롬프트에 통째 싣지 않는다


def test_guide_is_reachable_from_actual_prompt_and_exact_filename():
    from ibl_access import build_environment
    from ibl_routing import _search_guide
    guide = _search_guide('ibl_composition.md', {'read': True})
    assert guide['match'] == 'filename' and guide['content'] == GUIDE.read_text()
    for compact in (True, False):
        prompt = build_environment(allowed_set={'table', 'self'},
                                   expose_idioms=False, compact=compact)
        assert 'read_guide(query="ibl_composition.md")' in prompt
    assert set(EXAMPLES) == {'pipeline', 'compose', 'empty', 'catch', 'retry', 'chunk'}
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
def test_retry_with_zero_or_all_failures(run, all_failed):
    code = EXAMPLES['retry']
    if all_failed:
        code = code.replace('/one', '/bad')
    else:
        code = code.replace('/bad', '/two')
    out = run(code)
    assert len(out['items']) == 2
    assert sum('_error' in row for row in out['items']) == (2 if all_failed else 0)
    assert len(run.observed['crawl']) == (4 if all_failed else 2)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
