"""긴문장 10회차: 도달 불가 연산, 다단계 정렬, 줄 머리 연산자, 블록 뒤 문장, 행 목록과 봉투, 앞 턴 프로그램 목록."""
import boot_paths  # noqa: F401
import json
from pathlib import Path

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_entry import handle_request
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime
from supervision_store import TurnStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'docs/experiments/long_sentence_imagination/round_10'


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def run(code, registry, inputs=None):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.issues
    return Runtime(plan, inputs).run()


# ── L10-3: 도달할 수 없는 가지의 연산 ──

@pytest.mark.parametrize('value,expected', [(None, ''), ('글', '주의: 글\n')])
def test_concat_in_unreachable_branch_is_not_numeric(registry, value, expected):
    code = (FIXTURE / 'repro/concat_null_branch.ibl').read_text()
    assert run(code, registry, {'x': value})['value'] == expected


def test_real_arithmetic_errors_still_reported(registry):
    issues = compile_program('return "글" + 1', registry).issues
    assert issues and issues[0]['code'] in ('NUMBER_REQUIRED', 'ARITHMETIC', 'TYPE')


# ── L10-1: 다단계 정렬 ──

def test_sort_by_several_keys(registry):
    rows = [{'학번': 'S2', '일자': '09-02'}, {'학번': 'S1', '일자': '09-03'},
            {'학번': 'S2', '일자': '09-01'}, {'학번': 'S1', '일자': '09-01'}]
    value = run('return $rows >> [table:sort]{by:["학번","일자"]}', registry, {'rows': rows})['value']
    assert [(r['학번'], r['일자']) for r in value] == [('S1', '09-01'), ('S1', '09-03'), ('S2', '09-01'), ('S2', '09-02')]
    single = run('return $rows >> [table:sort]{by:"일자",descending:true}', registry, {'rows': rows})['value']
    assert single[0]['일자'] == '09-03'
    out = run('return $rows >> [table:sort]{by:["학번","없는열"]}', registry, {'rows': rows})
    assert not out['success'] and out['diagnostic']['code'] == 'MISSING_FIELD'
    assert compile_program('return $rows >> [table:sort]{by:[]}', registry, {'rows': rows}).issues or \
        not Runtime(compile_program('return $rows >> [table:sort]{by:[]}', registry, {'rows': rows}), {'rows': rows}).run()['success']


# ── L10-2·L10-8: 줄 머리 연산자(불변), 블록 뒤 문장 ──

def test_leading_operator_rule_is_unchanged(registry):
    """줄 머리 산술 연산자는 09-26·5회차 결정대로 거절한다 — 10회차에서 개정을 검토했으나 근거가 훈련자 2회뿐이라 두었다."""
    with pytest.raises(Fault) as refused:
        compile_program('$글 = "가"\n  + "나"\nreturn $글', registry)
    assert refused.value.code == 'SYNTAX' and '앞줄 끝' in str(refused.value)
    assert run('$글 = "가" +\n  "나"\nreturn $글', registry)['value'] == '가나'


def test_statement_may_follow_a_control_block_on_the_same_line(registry):
    code = '[def:부호]($v){ [if:$v < 0]{return "음"} [if:$v == 0]{return "영"} return "양" }\nreturn [[fn:부호]{v:-1},[fn:부호]{v:0},[fn:부호]{v:3}]'
    assert run(code, registry)['value'] == ['음', '영', '양']
    with pytest.raises(Fault):
        compile_program('$a = 1 $b = 2', registry)          # 블록이 아닌 문장 사이는 여전히 구분자가 필요하다
    assert run('[if:true]{$x = 1}[else]{$x = 2} return 3', registry)['value'] == 3


def test_value_branch_and_list_spread_hints(registry):
    issue = next(i for i in compile_program('return {p:[if:true]{1}[else]{0}}', registry).issues if i['code'] == 'VALUE_EXPRESSION')
    assert '?' in issue['hint'] and '조건 값' in issue['hint']
    issue = next(i for i in compile_program('return reduce([1,2],0,($a,$r)=>[if:$r > $a]{$r}[else]{$a})', registry).issues)
    assert issue['code'] == 'PURE_EXPRESSION' and '? ' in issue['hint']
    with pytest.raises(Fault) as refused:
        compile_program('return [**$a, 1]', registry, {'a': [0]})
    assert '$a + [값]' in str(refused.value)


# ── L10-4: 행 목록과 봉투는 행이 필요한 자리에서 같다 ──

def test_envelope_flows_into_row_operations(registry):
    rows = [{'반': 'A', 'n': 2}, {'반': 'B', 'n': 1}, {'반': 'A', 'n': 5}]
    code = '''$묶음 = $rows >> [table:groupby]{by:"반",agg:{합:["sum","n"]}}
$정렬 = $묶음 >> [table:sort]{by:"합",descending:true}
$이름 = $묶음 >> [table:each]{ return $it.반 }
$고른 = $rows >> [table:select]{columns:["반"]}
$큰 = $묶음 >> [table:filter]{where:($r)=>$r.합 > 1} >> [table:take]{n:1}
return {정렬:$정렬,이름:$이름,고른수:len($고른),큰:$큰,옛:len($묶음.items)}'''
    value = run(code, registry, {'rows': rows})['value']
    assert value['정렬'][0] == {'반': 'A', '합': 7} and sorted(value['이름']) == ['A', 'B']
    assert value['고른수'] == 3 and value['큰'] == [{'반': 'A', '합': 7}] and value['옛'] == 2
    # items 목록이 없는 레코드는 여전히 행 목록이 아니다
    assert compile_program('return $r >> [table:sort]{by:"a"}', registry, {'r': {'a': 1}}).issues
    # 목록에 가상 .items 필드는 없다 — 봉투를 받아 줄 뿐, 목록을 봉투인 척하게 하지 않는다.
    issue = compile_program('return ($rows >> [table:select]{columns:["반"]}).items', registry, {'rows': rows}).issues[0]
    assert issue['code'] == 'FIELD_TYPE' and '그대로 넘기면' in issue['hint']


def test_join_pipes_into_left_when_right_is_given(registry):
    left, right = [{'k': 1, 'a': 'x'}, {'k': 2, 'a': 'y'}], [{'k': 1, 'b': 'z'}]
    value = run('return ($l >> [table:join]{right:$r,on:"k",how:"inner"}).items', registry, {'l': left, 'r': right})['value']
    assert value == [{'k': 1, 'a': 'x', 'b': 'z'}]
    pair = run('return ($l & $r >> [table:join]{on:"k",how:"anti"}).items', registry, {'l': left, 'r': right})['value']
    assert pair == [{'k': 2, 'a': 'y'}]


# ── L10-10: 순수 자리의 기준은 효과 ──

def test_pure_function_calls_are_allowed_in_pure_slots(registry):
    code = '''[def:숫자아님]($v) { [try]{ $n = number($v); return false } [catch]{ return true } }
[def:큰가]($n,$기준) { return $n > $기준 }
$rows = [{v:"1"},{v:"x"},{v:"7"}]
$bad = $rows >> [table:filter]{where:($r)=>[fn:숫자아님]{v:$r.v}}
$n = [fn:큰가]{n:len($bad),기준:0} ? "있음" : "없음"
[if:[fn:큰가]{n:3,기준:1} and len($bad) == 1]{ return {bad:$bad,n:$n} }
return null'''
    assert run(code, registry)['value'] == {'bad': [{'v': 'x'}], 'n': '있음'}


def test_effectful_function_is_still_refused_in_pure_slots(registry, tmp_path):
    code = ('[def:적기]($v){ $w = [self:write]{path:$p,content:$v}; return true }\n'
            'return [{v:"a"}] >> [table:filter]{where:($r)=>[fn:적기]{v:$r.v}}')
    plan = compile_program(code, registry, {'p': str(tmp_path / 'x.txt')})
    issue = next(i for i in plan.issues if i['code'] == 'PURE_EXPRESSION')
    assert '효과가 없어야' in issue['message'] and 'table:each' in issue['hint']
    assert not Runtime(plan, {'p': str(tmp_path / 'x.txt')}).run()['executed'] and not (tmp_path / 'x.txt').exists()
    tool = compile_program('return [{v:"a"}] >> [table:filter]{where:($r)=>[self:read]{path:$r.v}.text == ""}', registry)
    assert any(i['code'] == 'PURE_EXPRESSION' for i in tool.issues)


# ── 비용 안내 ──

def test_budget_message_states_the_maximum():
    result = handle_request({'code': '#!ibl edition=2\nreturn $rows >> [table:each]{return $it*2}',
                             'inputs': {'rows': list(range(50))}, 'budget': {'steps': 20}})
    assert result['diagnostic']['code'] == 'BUDGET' and '10000000' in result['error']


# ── L10-6: 앞 턴이 실행한 프로그램 목록 ──

def test_call_history_lists_earlier_turn_programs(tmp_path):
    import model_result_view
    from model_result_view import read_result

    def turn(number, actor=('system_ai', '.', 'owner')):
        store = TurnStore(tmp_path / 'supervision' / f'{number:032x}')
        store.join_lineage(*actor)
        return store

    first = turn(1)
    request = first.evidence({'code': 'return 1 + 1', 'edition': 2})
    answer = first.evidence({'success': True, 'value': 2, 'edition': 2})
    first.log('tool.started', id='c1', name='execute_ibl', input=request)
    first.log('tool.finished', id='c1', evidence=answer, is_error=False, elapsed_s=0.1)
    bad = first.evidence({'code': 'return ('})
    first.log('tool.started', id='c2', name='execute_ibl', input=bad)
    first.log('tool.finished', id='c2', evidence=first.evidence({'ok': False}), is_error=True, check_rejected=True, elapsed_s=0.1)
    other = turn(7, ('다른에이전트', '.', 'owner'))
    other.log('tool.started', id='x', name='execute_ibl', input=other.evidence({'code': 'secret'}))
    other.log('tool.finished', id='x', evidence=other.evidence({'success': True}), is_error=False, elapsed_s=0.1)
    second = turn(2)
    original = model_result_view.evidence_store
    model_result_view.evidence_store = lambda: second
    try:
        history = read_result({'calls': True})
        assert [t['current'] for t in history['turns']] == [True, False]
        calls = history['turns'][1]['calls']
        assert [c['is_error'] for c in calls] == [False, True] and calls[1]['check_rejected']
        assert 'secret' not in json.dumps(history, ensure_ascii=False)
        code = read_result({'id': calls[0]['input']['id'], 'path': ['code']})
        assert code['text'] == 'return 1 + 1' and code['from_turn'] == first.directory.name
        with pytest.raises(ValueError):
            read_result({})
    finally:
        model_result_view.evidence_store = original


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
