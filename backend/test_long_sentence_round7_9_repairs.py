"""긴문장 7~9회차: 앞 턴 결과 이어 쓰기, 리허설 표식, 작성 진단과 줄 단위 비용."""
import boot_paths  # noqa: F401
import json
from pathlib import Path

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_entry import handle_request
from ibl_v2_runtime import Runtime
from supervision_store import EvidenceNotFound, LINEAGE_DEPTH, TurnStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def turn(root, number, actor=('system_ai', '.', 'owner')):
    store = TurnStore(root / 'supervision' / f'{number:032x}')
    store.join_lineage(*actor)
    return store


# ── L9-1: 같은 행위자의 앞 턴 결과 ──

def test_next_turn_reads_earlier_turn_of_same_actor(tmp_path):
    first = turn(tmp_path, 1)
    ref = first.evidence({'edition': 2, 'success': True, 'value': [1, 2, 3]})
    second = turn(tmp_path, 2)
    with pytest.raises(EvidenceNotFound):
        second.read_evidence(ref['id'])          # 턴 저장소 자체의 격리는 그대로
    page = second.read_evidence_across_turns(ref['id'], 0, None)
    assert page['from_turn'] == first.directory.name and page['integrity'] == 'verified'
    assert json.loads(page['text'])['value'] == [1, 2, 3]
    assert 'from_turn' not in first.read_evidence_across_turns(ref['id'], 0, None)


@pytest.mark.parametrize('other', [('다른에이전트', '.', 'owner'), ('system_ai', '/다른/프로젝트', 'owner'),
                                   ('system_ai', '.', 'member:7')])
def test_other_actor_cannot_read(tmp_path, other):
    ref = turn(tmp_path, 1).evidence('주인의 결과')
    with pytest.raises(EvidenceNotFound):
        turn(tmp_path, 2, other).read_evidence_across_turns(ref['id'])


def test_turn_without_lineage_and_later_turns_are_not_searched(tmp_path):
    plain = TurnStore(tmp_path / 'supervision' / f'{9:032x}')
    ref = turn(tmp_path, 1).evidence('앞 턴')
    with pytest.raises(EvidenceNotFound):
        plain.read_evidence_across_turns(ref['id'])
    early = turn(tmp_path, 2)
    late_ref = turn(tmp_path, 3).evidence('나중 턴')
    with pytest.raises(EvidenceNotFound):
        early.read_evidence_across_turns(late_ref['id'])   # 뒤 턴의 결과는 앞 턴이 읽지 않는다


def test_depth_limit_and_forged_ledger(tmp_path):
    ref = turn(tmp_path, 1).evidence('오래된 결과')
    for number in range(2, 2 + LINEAGE_DEPTH):
        last = turn(tmp_path, number)
    assert last.read_evidence_across_turns(ref['id'])['from_turn']
    with pytest.raises(EvidenceNotFound):
        turn(tmp_path, 99).read_evidence_across_turns(ref['id'])   # 최근 LINEAGE_DEPTH 턴 밖
    # 원장에 남의 턴 이름을 끼워 넣어도, 그 턴이 같은 키를 스스로 적지 않았으면 보지 않는다.
    foreign = turn(tmp_path, 200, ('다른에이전트', '.', 'owner'))
    secret = foreign.evidence('남의 결과')
    mine = turn(tmp_path, 201)
    key = json.loads((mine.directory / 'lineage.json').read_text())['key']
    ledger = tmp_path / 'supervision_lineage' / (key + '.jsonl')
    rows = ledger.read_text().splitlines()
    ledger.write_text('\n'.join(rows[:-1] + [json.dumps({'turn': foreign.directory.name}), rows[-1]]) + '\n')
    with pytest.raises(EvidenceNotFound):
        mine.read_evidence_across_turns(secret['id'])


def test_earlier_turn_evidence_must_be_certified(tmp_path):
    first = turn(tmp_path, 1)
    ref = first.evidence('원문')
    (first.directory / (ref['id'] + '.txt')).write_text('바뀐 원문', encoding='utf-8')
    with pytest.raises(EvidenceNotFound, match='인증'):
        turn(tmp_path, 2).read_evidence_across_turns(ref['id'])


def test_input_reference_and_read_result_cross_turn(tmp_path, registry):
    from model_result_view import read_result, resolve_input_refs
    import model_result_view
    first = turn(tmp_path, 1)
    executed = handle_request({'code': '#!ibl edition=2\nreturn {행:[{a:1},{a:2}],합:3}'})
    stored = {k: executed[k] for k in executed if k in ('success', 'value', 'value_wire', 'edition')}
    ref = first.evidence(stored)
    second = turn(tmp_path, 2)
    inputs, notes = resolve_input_refs({'앞': {'$ref': ref['id']}, '합': {'$ref': ref['id'], 'path': ['value', '합']}}, store=second)
    assert inputs == {'앞': {'행': [{'a': 1}, {'a': 2}], '합': 3}, '합': 3}
    assert all(note['from_turn'] == first.directory.name for note in notes)
    original = model_result_view.evidence_store
    model_result_view.evidence_store = lambda: second
    try:
        page = read_result({'id': ref['id'], 'path': ['value', '합']})
    finally:
        model_result_view.evidence_store = original
    assert page['from_turn'] == first.directory.name and json.loads(page['text']) == 3


# ── L9-2·L9-3·L8-4: 작성 진단 ──

def test_arity_reported_once_with_received_count(registry):
    code = ('#!ibl edition=2\n[def:f]($r) { return get($r) }\n'
            '$x = [fn:f]{r:{a:1}}\nreturn $x')
    report = handle_request({'code': code, 'check': True})
    arity = [i for i in report['issues'] if i['code'] == 'ARITY']
    assert len(arity) == 1
    assert '인자 2~3개' in arity[0]['message'] and '받은 인자 1개' in arity[0]['message']


# ── 언어 개정(2026-09-30): get 기본값 생략, 값 자리의 호출 ──

def test_get_default_is_null_when_omitted(registry):
    plan = compile_program('return [get($r,"a"), get($r,"없음"), get($r,"없음",0), get($r,"n")]', registry, {'r': {'a': 1, 'n': None}})
    assert not plan.issues, plan.issues
    assert Runtime(plan, {'r': {'a': 1, 'n': None}}).run()['value'] == [1, None, 0, None]


def test_episode_shapes_now_run_in_place(registry):
    """에피소드 4182·4183 과 훈련자 9회차가 거절당한 모양 — 연산·내장 함수 인자 안의 파이프와 함수 호출."""
    code = '''#!ibl edition=2
[def:천단위]($n) { return text($n) + "원" }
$행 = [{가게:"가", 금액:1200}, {가게:"나", 금액:300}, {가게:"가", 금액:500}]
$가게 = unique($행 >> [table:each]{ return $it.가게 })
$합 = sum($행 >> [table:each]{ return $it.금액 })
$줄 = $행 >> [table:each]{ return "| " + $it.가게 + " | " + [fn:천단위]{n:$it.금액} + " |" }
$둘 = ($행 >> [table:select]{columns:["가게"]}) + ($행 >> [table:select]{columns:["금액"]})
return {가게:$가게, 합:$합, 표:join("\\n", $줄), 줄수:len($둘), 글:f"합계 ${[fn:천단위]{n:$합}}"}'''
    plan = compile_program(code, registry)
    assert not plan.issues, plan.issues
    value = Runtime(plan).run()['value']
    assert value['가게'] == ['가', '나'] and value['합'] == 2000 and value['줄수'] == 6
    assert value['표'].splitlines()[0] == '| 가 | 1200원 |' and value['글'] == '합계 2000원'


def test_null_interpolation_names_the_value():
    from ibl_v2_ir import Fault
    from common.expression_ops import scalar_text
    with pytest.raises(Fault) as null_fault:
        scalar_text(None)
    assert 'null' in str(null_fault.value) and null_fault.value.details['actual'] == 'Null'
    with pytest.raises(Fault) as list_fault:
        scalar_text([1])
    assert 'json()' in str(list_fault.value) and list_fault.value.details['actual'] == 'list'
    assert scalar_text(3) == '3' and scalar_text(True) == 'true'


def test_result_list_hint_and_runtime_items_hint(registry):
    code = ('#!ibl edition=2\n$r = [1,2] >> [table:each]{on_error:"collect"}{ return {a:$it} }\n'
            'return $r >> [table:select]{columns:["a"]}')
    report = handle_request({'code': code, 'check': True})
    issue = next(i for i in report['issues'] if i['code'] == 'TYPE')
    assert 'unwrap' in issue['hint'] and 'zip' not in issue['hint']
    from ibl_v2_ir import Fault
    from ibl_v2_types import guard
    with pytest.raises(Fault) as fault:
        guard({'items': [{'a': 1}], 'count': 1}, 'List<Record>', 'table:compute.items')
    assert '.items' in str(fault.value)


# ── L9-4: 줄 단위 비용 ──

def test_steps_by_line_points_to_the_expensive_line(registry):
    code = '$a = 1\n$b = $rows >> [table:filter]{where:($r)=>$r.a > 1 and $r.a < 90}\nreturn len($b)'
    plan = compile_program(code, registry, {'rows': [{'a': i} for i in range(100)]})
    assert not plan.issues, plan.issues
    usage = Runtime(plan, {'rows': [{'a': i} for i in range(100)]}).run()['usage']
    lines = usage['steps_by_line']
    assert lines[0]['line'] == 2 and lines[0]['steps'] > 500
    assert len(lines) <= 10 and sum(row['steps'] for row in lines) <= usage['steps']
    assert lines[0]['steps'] > max(row['steps'] for row in usage['steps_by_span'])


# ── L7-1: 리허설 표식 ──

def test_conversation_threads_are_separate():
    from system_ai_memory import _thread_clause
    assert _thread_clause('rehearsal', 'WHERE') == "WHERE source = 'rehearsal'"
    assert _thread_clause('appmaker', 'AND') == "AND source = 'appmaker'"
    default = _thread_clause('system_ai', 'WHERE')
    assert "'appmaker'" in default and "'rehearsal'" in default and 'NOT IN' in default
    assert _thread_clause("x' OR 1=1 --", 'WHERE') == default   # 모르는 이름은 본 대화 절로만


def test_rehearsal_gets_its_own_cli_session_and_keeps_origin():
    from providers.cli_provider import CliSubprocessProvider
    from thread_context import actor_context, clear_task_origin, get_task_origin, in_rehearsal
    probe = CliSubprocessProvider.__new__(CliSubprocessProvider)
    probe.agent_id, probe.agent_name = 'system_ai', '시스템 AI'
    clear_task_origin()
    normal = CliSubprocessProvider._get_session_key(probe)
    with actor_context(origin='training'):
        assert in_rehearsal()
        assert CliSubprocessProvider._get_session_key(probe) == normal + '@rehearsal'
    assert get_task_origin() is None and CliSubprocessProvider._get_session_key(probe) == normal


def test_chat_origin_accepts_only_training():
    from fastapi import HTTPException
    from surface import api_system_ai
    with pytest.raises(HTTPException) as refused:
        api_system_ai.chat_with_system_ai(api_system_ai.ChatMessage(message='x', origin='user'))
    assert refused.value.status_code == 400 and 'training' in refused.value.detail


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
