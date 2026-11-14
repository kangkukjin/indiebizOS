"""도구 결과 기록의 이음매 (2026-11-14, docs/MEMORY_REPAIR_PLAN_2026_11_14.md R0).

재현한 결함: 10-31 부터 MCP 가 도구 응답 뒤에 '실행 상황' 블록을 덧붙였고(`mcp_server.py`), CLI 공급자가
그 문자열을 그대로 기록했다. 결과를 JSON 으로 읽는 소비자(경험 증류 `closed_call`·지도 봉투)가 조용히
전부 놓쳐, 실행기억 증류가 두 주 동안 0건이었다. API 공급자는 화면 미리보기(3000자 절단)를 기록해 같은 꼴.
여기서는 **기록되는 결과가 결과만 담는가**를 잠근다.

실행: .venv/bin/python -m pytest backend/test_result_record_seam_2026_11_14.py -q
"""
import boot_paths  # noqa: F401
import json

import pytest

from situation_delivery import PREFIX, render, split_result

DELIVERY = {'delivery_id': 'd' * 32, 'mode': 'baseline', 'observations': [
    {'latest': {'value': {'success': False, 'error': 'earlier failure'}}}]}
RESULT = {'success': True, 'executed': True, 'source_complete': True, 'value': {'items': [{'n': 1}]}}


@pytest.mark.parametrize('joint', [' ', '\n'])
def test_appended_delivery_is_split_from_result(joint):
    """붙이는 쪽(render)과 떼는 쪽(split_result)의 왕복 — 형식이 바뀌면 여기서 깨진다."""
    text = json.dumps(RESULT, ensure_ascii=False) + joint + render(DELIVERY)
    result, delivery = split_result(text)
    assert json.loads(result) == RESULT
    assert delivery['delivery_id'] == DELIVERY['delivery_id']


def test_result_without_delivery_is_untouched():
    for text in (json.dumps(RESULT), '', 'plain output', None, {'already': 'object'}):
        assert split_result(text) == (text, None)


def test_prefix_inside_the_result_is_result_data():
    quoted = {'success': True, 'value': {'text': 'log line ' + PREFIX + '{"mode": "baseline"}'}}
    text = json.dumps(quoted, ensure_ascii=False)
    assert split_result(text) == (text, None)
    plain = 'cat of a log\n' + PREFIX + 'not a delivery object\nmore output'
    assert split_result(plain) == (plain, None)
    both, delivery = split_result(text + '\n' + render(DELIVERY))
    assert json.loads(both) == quoted and delivery['mode'] == 'baseline'


def test_cut_delivery_after_a_whole_result_is_still_not_result():
    text = json.dumps(RESULT) + '\n' + render(DELIVERY)[:-20]
    result, delivery = split_result(text)
    assert json.loads(result) == RESULT and delivery == {}


def _tool_result_events(translated):
    return [event for event, _ in translated if event.get('type') == 'tool_result']


def test_claude_code_event_carries_the_result_only():
    """Claude CLI 는 text 조각을 공백으로 이어 준다 — 옛 '\\n' 분리는 이 꼴을 못 뗐다."""
    from providers import get_provider
    provider = get_provider('claude_code', api_key='', model='opus', system_prompt='')
    block = {'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': [
        {'type': 'text', 'text': json.dumps(RESULT, ensure_ascii=False)},
        {'type': 'text', 'text': render(DELIVERY)}]}
    events = _tool_result_events(provider._translate_stream_event(
        {'type': 'user', 'message': {'content': [block]}}, '', 0.0))
    assert len(events) == 1
    assert json.loads(events[0]['result']) == RESULT
    assert events[0]['situation_delivery_id'] == DELIVERY['delivery_id']


def test_codex_event_carries_the_result_only(monkeypatch, tmp_path):
    import episode_logger as el
    from providers import get_provider
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    monkeypatch.setattr(el, 'record_trajectory_event', lambda *a, **kw: None)
    provider = get_provider('codex', api_key='', model='m', system_prompt='')
    item = {'id': 'item_1', 'type': 'mcp_tool_call', 'server': 'indiebizos', 'tool': 'execute_ibl',
            'arguments': {'code': '#!ibl edition=2\nreturn 1'}, 'status': 'completed',
            'result': {'content': [{'type': 'text', 'text': json.dumps(RESULT, ensure_ascii=False)},
                                   {'type': 'text', 'text': render(DELIVERY)}], 'isError': False}}
    events = _tool_result_events(provider._translate_stream_event(
        {'type': 'item.completed', 'item': item}, '', 0.0))
    assert len(events) == 1
    assert json.loads(events[0]['result']) == RESULT
    assert events[0]['situation_delivery_id'] == DELIVERY['delivery_id']


def test_split_result_reaches_learning_as_a_closed_call():
    """기록된 꼴 그대로(결과 + 공백 + 실행 상황)는 닫힌 실행이 아니고, 가른 결과는 닫힌 실행이다."""
    from ibl_v2_experience import closed_call
    call = {'tool_name': 'execute_ibl', 'success': True,
            'input': {'code': '#!ibl edition=2\nreturn [sense:restaurant]{query: "청주 맛집"}'}}
    recorded = json.dumps(RESULT, ensure_ascii=False) + ' ' + render(DELIVERY)
    assert closed_call({**call, 'result': recorded}) is None
    assert closed_call({**call, 'result': split_result(recorded)[0]}) is not None


CALL = {'tool_name': 'execute_ibl', 'success': True,
        'input': {'code': '#!ibl edition=2\nreturn [sense:restaurant]{query: "청주 맛집"}'}}


def test_unreadable_results_are_not_reported_as_nothing_to_learn():
    """R1: 못 읽은 것과 배울 것이 없는 것은 다른 사유다 — 죽은 고리가 '신중한 고리'로 보이지 않게."""
    from unified_distill import prepare
    job = {'user_message': '청주 맛집', 'write_forage': False, 'write_deep': False,
           'tool_calls': [{**CALL, 'result': json.dumps(RESULT, ensure_ascii=False) + ' ' + render(DELIVERY)}]}
    assert prepare(job)['skip_reasons']['execution'] == 'unreadable_evidence'
    readable = {**CALL, 'result': json.dumps({'success': True, 'executed': False})}
    assert prepare({**job, 'tool_calls': [readable]})['skip_reasons']['execution'] == 'no_new_eligible_evidence'


def _job(result, prepared=None, provider='codex'):
    payload = {'model': {'provider': provider}, 'tool_calls': [{**CALL, 'result': result}]}
    return json.dumps(payload, ensure_ascii=False), json.dumps(prepared or {'sections': {}})


def test_distill_health_flags_a_dead_loop_and_passes_a_live_one():
    from distill_health_audit import measure, MIN_TURNS
    broken = json.dumps(RESULT, ensure_ascii=False) + ' ' + render(DELIVERY)
    dead = measure([_job(broken) for _ in range(MIN_TURNS)])
    assert {f['kind'] for f in dead['flags']} == {'unreadable_results', 'no_execution_candidates'}
    assert dead['flags'][0]['by_provider'] == {'codex': {'calls': MIN_TURNS, 'unreadable': MIN_TURNS}}
    whole = json.dumps(RESULT, ensure_ascii=False)
    live = measure([_job(whole, {'sections': {'execution': {}}})] + [_job(whole) for _ in range(MIN_TURNS)])
    assert live['flags'] == [] and live['unchecked'] == [] and live['turns_with_candidates'] == 1
    quiet = measure([_job(broken)])
    assert quiet['flags'] == [] and quiet['unchecked'] == ['successful_runs_below_minimum']


def test_distill_health_report_is_not_clean_when_measurement_fails(monkeypatch, tmp_path):
    import distill_health_audit as audit
    from audit_lifecycle import normalize_result
    monkeypatch.setattr(audit, '_STATE_PATH', tmp_path / 'state.json')
    monkeypatch.setattr(audit, '_recent_rows', lambda: (_ for _ in ()).throw(RuntimeError('db closed')))
    report = normalize_result(audit.run_distill_health_check(force=True))
    assert report['audit_status'] == 'failed' and 'db closed' in report['error_message']
    broken = json.dumps(RESULT, ensure_ascii=False) + ' ' + render(DELIVERY)
    monkeypatch.setattr(audit, '_recent_rows', lambda: [_job(broken) for _ in range(audit.MIN_TURNS)])
    report = normalize_result(audit.run_distill_health_check(force=True))
    assert report['audit_status'] == 'findings' and report['unreadable'] == audit.MIN_TURNS


from test_unified_distill_2026_09_21 import env, candidate, deep_section  # noqa: E402,F401


@pytest.mark.parametrize('relation', ['SAME', 'NEW'])
def test_meeting_the_same_fact_again_raises_its_confirmation_time(env, relation):
    """R2: 통합 증류가 같은 사실을 다시 만나면 '마지막으로 확인된 때'(used_at)가 올라간다.

    통합 증류로 옮긴 뒤 이 갱신이 빠져 used_at 이 2026-09-14 에 멈춰 있었다(10~11월 생성 28행 전부 빈 값)."""
    from distill_memory_adapters import apply_deep, _version
    project, agent = env.job['project_path'], env.job['agent_id']
    ident = env.db.save(project, agent, env.job['user_message'], node='문체')
    row = env.db.read(project, agent, ident, touch=False)
    assert not row['used_at']
    row['version'] = _version(row)
    section = deep_section(env)
    section['known'] = [row]
    extra = {'relation': 'SAME', 'existing_id': ident, 'existing_version': row['version']} if relation == 'SAME' else {}
    assert apply_deep(env.job, section, candidate(**extra), 'again-1')['status'] == 'same'
    assert env.db.read(project, agent, ident, touch=False)['used_at']


class _Usage:
    """IBLUsageDB 대역 — 귀속 호출만 받아 적는다."""
    def __init__(self):
        self.by_id, self.by_code = [], []

    def update_success(self, example_id, success, elapsed_ms=None, tokens=None):
        self.by_id.append((example_id, success, elapsed_ms, tokens))

    def update_success_by_code(self, code, success, elapsed_ms=None, tokens=None):
        self.by_code.append((code, success, elapsed_ms, tokens))
        return True


@pytest.fixture
def usage(monkeypatch):
    import ibl_usage_db
    import ibl_usage_rag as rag
    stub = _Usage()
    monkeypatch.setattr(ibl_usage_db, 'IBLUsageDB', lambda: stub)
    monkeypatch.setattr(rag, '_alias_of_code', lambda code: '')
    monkeypatch.setattr(rag.IBLUsageRAG, 'clear_cache', lambda self: None)
    return stub


def _run(code, success=True, ms=10):
    return {'tool_name': 'execute_ibl', 'success': success, 'elapsed_ms': ms,
            'input': {'code': '#!ibl edition=2\n' + code, 'edition': 2}}


def _shown(*items):
    return [{'source': 'hippocampus', 'ids': [i for i, _ in items],
             'join': {'items': [{'id': i, 'code': '#!ibl edition=2\n' + c, 'kind': 'word', 'alias': ''} for i, c in items]}}]


READ, SEARCH = 'return [self:read]{path: "a.txt"}', 'return [sense:search]{query: "자동화"}'


def test_outcome_is_credited_by_use_not_by_score(usage):
    """R2: 낮은 점수로 제시됐어도 실제로 쓰였으면 성패가 적히고, 안 쓰인 항목은 높은 점수여도 안 적힌다."""
    from ibl_usage_rag import record_recall_outcome
    shown = _shown(('11', READ), ('22', SEARCH))
    assert record_recall_outcome(shown[0]['join']['items'][1]['code'], 0.66,
                                 [_run('return [self:read]{path: "b.txt"}')], turn_tokens=100, presented=shown)
    assert usage.by_id == [(11, True, 10, 100)] and usage.by_code == []


def test_unrelated_failure_does_not_punish_the_memory_that_was_used(usage):
    from ibl_usage_rag import record_recall_outcome
    calls = [_run('return [sense:nonexistent]{x: 1}', success=False), _run('return [self:read]{path: "b.txt"}', ms=7)]
    assert record_recall_outcome('', 0.7, calls, presented=_shown(('11', READ)))
    assert usage.by_id == [(11, True, 7, None)]


def test_memory_whose_every_use_failed_is_recorded_as_failed(usage):
    from ibl_usage_rag import record_recall_outcome
    calls = [_run('return [self:read]{path: "b.txt"}', success=False), _run('return [sense:search]{query: "x"}')]
    assert record_recall_outcome('', 0.7, calls, presented=_shown(('11', READ)))
    assert usage.by_id == [(11, False, None, None)]


def test_two_used_memories_are_both_credited_without_turn_tokens(usage):
    from ibl_usage_rag import record_recall_outcome
    calls = [_run('return [self:read]{path: "b.txt"}', ms=5), _run('return [sense:search]{query: "x"}', ms=9)]
    assert record_recall_outcome('', 0.7, calls, turn_tokens=100, presented=_shown(('11', READ), ('22', SEARCH)))
    assert usage.by_id == [(11, True, 5, None), (22, True, 9, None)]


from test_time_selection import db  # noqa: E402,F401


def test_confirmation_time_moves_only_on_a_successful_use(db, monkeypatch, tmp_path):
    """R3: '마지막으로 쓰여 성공한 때'는 성공에서만 오른다 — 편집·실패로 오르는 updated_at 과 다르다."""
    import hippo_tree
    monkeypatch.setattr(hippo_tree, 'DOC_DIR', str(tmp_path / 'tree'))
    ident = db.add_example('메일 확인', '#!ibl edition=2\nreturn 1', source='distilled')

    def confirmed():
        with db._get_connection() as conn:
            return conn.execute('SELECT confirmed_at FROM ibl_current_examples WHERE id=?', (ident,)).fetchone()[0]

    assert confirmed() is None
    db.update_success(ident, False)
    assert confirmed() is None
    db.update_success(ident, True, elapsed_ms=10)
    assert confirmed()


def test_recall_shows_when_a_memory_was_learned_and_last_confirmed():
    """R3: 날짜는 순위·삭제에 쓰지 않고 보여 주기만 한다. 기록이 없으면 속성도 없다."""
    from ibl_usage_db import UsageExample
    from ibl_usage_rag import IBLUsageRAG
    base = dict(nodes='sense', category='single', difficulty=1, success_rate=-1.0)
    lived = UsageExample(id=1, intent='메일 확인', ibl_code='#!ibl edition=2\nreturn 1', score=0.9,
                         source='distilled', learned_at='2026-08-12', confirmed_at='2026-11-03', **base)
    seed = UsageExample(id=2, intent='가격 조회', ibl_code='#!ibl edition=2\nreturn 2', score=0.8,
                        source='manual_seed', **base)
    xml = IBLUsageRAG()._format_references([lived, seed])
    assert 'learned="2026-08-12"' in xml and 'confirmed="2026-11-03"' in xml
    assert xml.count('learned="') == 1 and xml.count('confirmed="') == 1
    assert 'learned는 실제 실행에서 배운 날' in xml


def test_model_result_rides_only_when_the_screen_preview_differs():
    from ibl_result_transport import with_model_result
    whole = json.dumps({'success': True, 'value': 'x' * 4000})
    preview = whole[:3000] + '...'
    with pytest.raises(ValueError):
        json.loads(preview)
    event = with_model_result({'type': 'tool_result', 'result': preview}, whole)
    assert json.loads(event['model_result'])['success'] is True
    same = with_model_result({'type': 'tool_result', 'result': whole}, whole)
    assert 'model_result' not in same
