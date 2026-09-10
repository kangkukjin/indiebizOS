"""과제 원장의 실제 SQLite 계약과 S1~S3. 모델/실사용 데이터 없이 경계를 검증한다."""
import boot_paths  # noqa: F401
import json
from types import SimpleNamespace

import pytest
import pursuit_bind as pb
from pursuit_ledger import PursuitLedger, Conflict
from pursuit_tools import execute_pursuit


@pytest.fixture
def ledger(tmp_path):
    return PursuitLedger(tmp_path / 'conversations.db', 'agent')


@pytest.fixture
def row(ledger):
    return ledger.create('월별 보고서', '수집·보고서·PDF 자동화 완료', 'origin',
                         framing='서울의 월별 보고서를 만든다', progress='원본 수집 완료', next='보고서 만들기')


@pytest.fixture
def bound(ledger, row, monkeypatch):
    runner = SimpleNamespace(_run_consciousness=lambda *a, **k: {
        'task_framing': '부산의 월별 보고서를 만든다', 'achievement_criteria': '부산 데이터 조회',
        'assumptions': ['대상은 부산이다']})
    b = pb.Binding(runner, ledger, 'agent', 'turn_b', '아니 서울이 아니라 부산이야', [])
    token = pb._current.set(b)
    monkeypatch.setattr(pb, 'ask_json', lambda p, **kwargs: {'action': 'rewrite', 'criteria': '부산 조회',
                         'broken_assumption': '대상은 서울이다', 'evidence': '사용자 정정'})
    yield b
    pb._current.reset(token)


def test_owner_isolation_and_idempotent_create(ledger, row):
    same = ledger.create('다른 제목', '다른 기준', 'origin')
    assert same['id'] == row['id'] and same['title'] == row['title']
    other = PursuitLedger(ledger.db_path, 'other')
    assert other.list()['total'] == 0
    with pytest.raises(KeyError):
        other.get(row['id'])


@pytest.mark.parametrize('system_ai', [False, True])
def test_runner_config_identity_binds_without_thread_agent(tmp_path, monkeypatch, system_ai):
    import thread_context as tc
    import system_ai_memory
    monkeypatch.setattr(tc, 'get_current_agent_id', lambda: None)
    monkeypatch.setattr(tc, 'get_current_task_id', lambda: 'http_turn')
    system_db = tmp_path / 'system_ai_memory.db'
    monkeypatch.setattr(system_ai_memory, 'MEMORY_DB_PATH', system_db)
    agent = 'system_ai' if system_ai else 'project_agent'
    runner = SimpleNamespace(config={'id': agent, '_is_system_ai': system_ai},
                             project_path=tmp_path)
    token = pb.enter(runner, '계속 진행', [])
    try:
        b = pb.current()
        assert b is not None and b.agent == agent and b.task == 'http_turn'
        row = b.ledger.create('과제', '완료 기준', b.task)
        expected_db = system_db if system_ai else tmp_path / 'conversations.db'
        owner = 'system_ai:' + agent if system_ai else agent
        assert PursuitLedger(expected_db, owner).get(row['id'])['title'] == '과제'
        assert pb.resolve_session(agent, 'http_turn') is b
    finally:
        pb.leave(token)
    monkeypatch.setattr(tc, 'get_current_task_id', lambda: None)
    assert pb.owner_for(runner) is None  # 무상태 호출은 config만으로 과제를 만들지 않는다.


def test_s1_same_pursuit_correction_rewrites_without_shrinking_goal(bound, row):
    bound.message = row['id'] + ' 아니 서울이 아니라 부산이야'
    memory, needs_review = pb.prepare('memory')
    assert needs_review and bound.row['id'] == row['id']  # EXECUTE에서도 이 신호가 THINK 승격을 요구
    out = pb.run_consciousness(bound.runner, bound.message, [], memory)
    updated = bound.ledger.get(row['id'])
    assert '부산' in updated['framing'] and out['achievement_criteria'] == '부산 데이터 조회'
    assert updated['goal_criteria'] == row['goal_criteria']
    assert updated['assumptions'][0]['status'] == 'broken'
    assert any(e['kind'] == 'framing.revised' for e in bound.ledger.events(row['id']))


def test_s2_choose_old_pursuit_after_other_work(bound, row, monkeypatch):
    bound.ledger.create('다른 일', '다른 기준', 'unrelated')
    answers = iter([{'id': row['id']}, {'action': 'keep', 'criteria': '다음 단계'}])
    monkeypatch.setattr(pb, 'ask_json', lambda p, **kwargs: next(answers))
    memory, needs_review = pb.prepare('')
    assert not needs_review and bound.row['progress'] == '원본 수집 완료'
    assert row['id'] in memory and '<goal_criteria>' in memory
    assert '<pending>' not in memory  # 자기 running 턴을 미처리 과거로 오인하지 않는다


def test_ambiguous_selection_is_unbound(bound, monkeypatch):
    monkeypatch.setattr(pb, 'ask_json', lambda p, **kwargs: {'id': None})
    _, needs_review = pb.prepare('')
    assert bound.row is None and not needs_review


def test_s3_old_summary_cannot_undo_later_correction(ledger, row):
    pid = row['id']
    a = ledger.begin_turn(pid, 'a', '파일 생성')
    ledger.finish_turn(pid, 'a', '파일 생성됨', [])
    b = ledger.begin_turn(pid, 'b', '그 파일은 틀렸으니 폐기해')
    latest = ledger.apply(pid, 'b', row['version'], {'progress': '잘못된 파일 폐기', 'next': '재생성 보류'}, 'b-note', b)
    with pytest.raises(Conflict):
        ledger.apply(pid, 'a', row['version'], {'progress': '파일 생성 완료'}, 'a-summary', a, summary=True)
    updated = ledger.apply(pid, 'a', latest['version'], {'progress': '파일 생성 완료'}, 'a-summary', a, summary=True)
    assert updated['progress'] == '잘못된 파일 폐기'
    event = ledger.events(pid)[-1]
    assert event['payload']['patch']['progress'] == '파일 생성 완료'
    assert event['payload']['superseded_fields'] == ['progress']
    again = ledger.apply(pid, 'a', latest['version'], {'progress': '파일 생성 완료'}, 'a-summary', a, summary=True)
    assert again['version'] == updated['version']


def test_s3_pending_read_catches_up_before_execution(bound, row, monkeypatch):
    a = bound.ledger.begin_turn(row['id'], 'a', '보고서 생성')
    bound.ledger.finish_turn(row['id'], 'a', '보고서 생성 완료', [{'name': 'write', 'result': 'report.pdf'}])
    answers = iter([{'progress': '보고서 생성 완료', 'next': 'PDF 검증'}, {'action': 'keep', 'criteria': '검증'}])
    monkeypatch.setattr(pb, 'ask_json', lambda p, **kwargs: next(answers))
    bound.message = row['id'] + ' 이어서'
    memory, _ = pb.prepare('')
    assert '보고서 생성 완료' in memory and bound.row['next'] == 'PDF 검증'
    assert next(t for t in bound.ledger.turns(row['id']) if t['task_id'] == 'a')['state'] == 'applied'


def test_pending_failure_stops_execution_and_retains_raw(bound, row, monkeypatch):
    bound.ledger.begin_turn(row['id'], 'a', '파일 만들기')
    bound.ledger.finish_turn(row['id'], 'a', 'file created', [{'result': 'file.txt'}])
    bound.message = row['id']
    monkeypatch.setattr(pb, 'ask_json', lambda p, **kwargs: (_ for _ in ()).throw(ValueError('model unavailable')))
    with pytest.raises(ValueError, match='진행 갱신'):
        pb.prepare('')
    assert bound.row is None
    t = bound.ledger.turns(row['id'])[0]
    assert t['response'] == 'file created' and t['error']


def test_summary_cas_retries_after_actual_concurrent_write(ledger, row, monkeypatch):
    pid = row['id']; a = ledger.begin_turn(pid, 'a', 'a')
    ledger.finish_turn(pid, 'a', '완료', [])
    calls = []
    def model(prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            b = ledger.begin_turn(pid, 'b', '정정')
            ledger.apply(pid, 'b', row['version'], {'next': '사용자 정정'}, 'b', b)
        return {'progress': '완료', 'next': '옛 다음 단계'}
    monkeypatch.setattr(pb, 'ask_json', model)
    pb.summarize_pending(ledger, pid)
    assert len(calls) == 2 and ledger.get(pid)['next'] == '사용자 정정'


def test_field_limits_and_budget(ledger, row):
    with pytest.raises(ValueError):
        ledger.create('x', 'goal', 'x', progress='x' * 3001)
    full = dict(row, framing='가' * 3000, progress='나' * 3000, next='다' * 600,
                goal_criteria='목' * 1500)
    rendered = pb.render_body(full)
    assert len(rendered) <= 3000 and full['goal_criteria'] in rendered
    assert 'omitted="true"' in rendered
    assert 'pursuit read' in rendered
    assert len(pb.render_body(dict(full, goal_criteria='&' * 1500))) <= 3000


def test_unbounded_events_and_paged_read(ledger, row):
    for i in range(205):
        ledger.begin_turn(row['id'], f't{i}', f'message {i}')
    assert len(ledger.turns(row['id'])) == 205
    assert len(ledger.events(row['id'], offset=200)) == 6


@pytest.mark.parametrize('offset,limit', [(0, 101), (0, 0), (-1, 30)])
def test_invalid_page_requests_are_rejected_across_surfaces(bound, row, offset, limit):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api_pursuits import router
    bound.bind(row); bound.aliases = {'agent'}
    with pytest.raises(ValueError):
        bound.ledger.list(offset=offset, limit=limit)
    with pytest.raises(ValueError):
        bound.ledger.events(row['id'], offset=offset, limit=limit)
    for section in ('list', 'events', 'turns'):
        result = json.loads(execute_pursuit({'op': 'read', 'section': section,
                                            'offset': offset, 'limit': limit}, 'agent', bound.task))
        assert not result['success']
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        response = client.get('/pursuits', params={'offset': offset, 'limit': limit})
        assert response.status_code == 422


def test_recovery_preserves_observed_tools(ledger, row):
    ledger.begin_turn(row['id'], 'a', 'file write')
    ledger.observe(row['id'], 'a', {'type': 'tool_result', 'result': 'file.txt'}, 1)
    with ledger.connect(True) as c:
        c.execute("UPDATE pursuit_turn SET process='old process'")
    reopened = PursuitLedger(ledger.db_path, ledger.agent_key)
    assert reopened.recover() == 1 and reopened.recover() == 0
    pending = reopened.turns(row['id'], pending_only=True)
    assert pending[0]['state'] == 'interrupted' and pending[0]['tools'][0]['result'] == 'file.txt'
    assert '반복 실행 금지' in pb.render_body(reopened.get(row['id']), pending)


def test_atomic_delete_rollback(ledger, row):
    with ledger.connect(True) as c:
        c.execute("CREATE TRIGGER reject_event_delete BEFORE DELETE ON pursuit_event BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    with pytest.raises(Exception, match='blocked'):
        ledger.delete(row['id'], row['version'])
    assert ledger.get(row['id']) and ledger.events(row['id'])
    with ledger.connect(True) as c:
        c.execute('DROP TRIGGER reject_event_delete')
    ledger.delete(row['id'], row['version'])
    with ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM pursuit_event').fetchone()[0] == 0


def test_lifecycle_and_revival(ledger, row):
    start = row['last_turn_at']
    assert ledger.maintain(start + 31 * 86400) == 1
    assert ledger.get(row['id'])['status'] == 'parked'
    assert ledger.maintain(start + 121 * 86400) == 1
    now = ledger.get(row['id'])
    assert now['status'] == 'abandoned'
    seq = ledger.begin_turn(row['id'], 'resume', '다시 진행')
    ledger.apply(row['id'], 'resume', now['version'], {'status': 'active'}, 'resume', seq, why='사용자 재개')
    assert ledger.events(row['id'])[-1]['kind'] == 'revived'


def test_summary_cannot_change_goal_or_status(ledger, row):
    seq = ledger.begin_turn(row['id'], 'a', 'a')
    with pytest.raises(ValueError):
        ledger.apply(row['id'], 'a', row['version'], {'status': 'done'}, 'bad', seq, why='x', summary=True)
    with pytest.raises(ValueError):
        ledger.apply(row['id'], 'a', row['version'], {'goal_criteria': '오늘만'}, 'bad2', seq)


def test_executor_note_done_and_read(bound, row):
    bound.bind(row); bound.aliases = {'agent'}
    result = json.loads(execute_pursuit({'op': 'note', 'progress': '보고서 검증 완료'}, 'agent', bound.task))
    assert result['success']
    assert bound.row['status'] == 'active'
    assert not json.loads(execute_pursuit({'op': 'done'}, 'agent', bound.task))['success']
    result = json.loads(execute_pursuit({'op': 'done', 'why': '전체 산출물 확인'}, 'agent', bound.task))
    assert result['result']['status'] == 'done'
    assert json.loads(execute_pursuit({'op': 'read', 'section': 'list'}, 'agent', bound.task))['result']['total'] == 1


def test_concurrent_execution_is_rejected(ledger, row):
    ledger.begin_turn(row['id'], 'a', 'work', execution=True)
    with pytest.raises(ValueError, match='실행 중'):
        ledger.begin_turn(row['id'], 'b', 'other', execution=True)


def test_bridge_uses_same_contract(bound, row):
    import asyncio
    from api_pursuits import bridge, ToolRequest
    bound.bind(row); bound.aliases = {'agent'}
    with pb._lock:
        pb._sessions[bound.task] = bound
    try:
        result = asyncio.run(bridge(ToolRequest(agent_id='agent', task_id=bound.task,
                                               payload={'op': 'note', 'next': '검증'})))
        assert result['success'] and result['result']['next'] == '검증'
    finally:
        pb._sessions.pop(bound.task, None)


def test_pipeline_reflex_correction_and_durable_finish(tmp_path, monkeypatch):
    import thread_context as tc
    import agent_pipeline as ap
    import system_ai_core as core
    from cognitive_consciousness import CognitiveConsciousnessMixin
    tc.clear_all_context()
    tc.set_current_agent_id('agent'); tc.set_current_task_id('pipeline_turn')
    ledger = PursuitLedger(tmp_path / 'conversations.db', 'agent')
    row = ledger.create('대상 보고서', '보고서 완성', 'origin', framing='서울을 조회한다')
    seen, packets = [], []
    class AI:
        _provider = SimpleNamespace(agent_id='agent')
        def process_message_stream(self, **kwargs):
            seen.append(kwargs['message_content'])
            yield {'type': 'tool_start', 'name': 'lookup', 'input': {'city': '부산'}}
            yield {'type': 'tool_result', 'result': '부산 조회 완료'}
            yield {'type': 'final', 'content': '부산 조회 완료'}
    class Runner(ap.CognitivePipelineMixin, CognitiveConsciousnessMixin):
        config = {'name': 'agent'}
        agent_id = 'agent'
        project_path = tmp_path
        full_calls = 0
        def _sync_execution_gear(self): pass
        def _build_execution_memory(self, *a, **kw): return '', 0.99, 'lookup'
        def _decide_request_type(self, *a): return 'EXECUTE', 'lookup'
        def _run_consciousness(self, *a, **kw):
            self.full_calls += 1
            return {'task_framing': '부산만 조회한다', 'achievement_criteria': '', 'assumptions': ['대상 부산']}
        def _consciousness_needs_repair(self, out): return False
        def _build_system_prompt_split(self, role, out, memory): return 'system', memory
        def _apply_consciousness_to_history(self, history, out): return history
        def _extract_achievement_criteria(self, out): return ''
        def _after_response_async(self, *a, **kw): packets.append(kw.get('pursuit_packet'))
    runner = Runner(); runner.ai = AI()
    monkeypatch.setattr(ap, '_reload_gate_notice', lambda: '')
    monkeypatch.setattr(core, '_restore_provider', lambda *a: None)
    monkeypatch.setattr(core, '_switch_to_midtier', lambda *a: pytest.fail('정정 턴이 Reflex에 남았다'))
    # 감독 신원 연결 후 이 통합 시험도 최종 검수에 도달한다. 실제 CLI/모델 호출은 금지.
    monkeypatch.setattr('supervisor_runtime.invoke', lambda *a, **k: json.dumps({
        'status': 'UNKNOWN', 'reason': '조회만 끝났고 전체 보고서는 아직 완성되지 않았다'}))
    monkeypatch.setattr(pb, 'ask_json', lambda p, **kwargs: {'action': 'rewrite', 'criteria': '',
                         'broken_assumption': '대상 서울', 'evidence': '사용자 부산 정정'})
    try:
        events = list(runner.cognitive_stream(row['id'] + ' 아니 부산으로 조회해'))
        assert runner.full_calls == 1
        assert any(e.get('type') == 'cognition' and e.get('decision') == 'think' for e in events)
        assert packets and packets[0]['id'] == row['id']
        turn = ledger.turns(row['id'])[-1]
        assert turn['state'] == 'pending' and '부산 조회' in turn['response']
        assert pb.current() is None and 'pipeline_turn' not in pb._sessions
        assert '<pursuit ' in seen[0]
        assert '<framing>부산만 조회한다</framing>' in seen[0]
    finally:
        tc.clear_all_context()


def test_explicit_completed_pursuit_can_resume(bound, row, monkeypatch):
    seq = bound.ledger.begin_turn(row['id'], 'done', '전체 완료')
    done = bound.ledger.apply(row['id'], 'done', row['version'], {'status': 'done'}, 'done', seq, why='확인')
    bound.ledger.finish_turn(row['id'], 'done', '', [])
    with bound.ledger.connect(True) as c:
        c.execute("UPDATE pursuit_turn SET state='applied'")
    bound.message = row['id'] + ' 다시 이어가'
    monkeypatch.setattr(pb, 'ask_json', lambda p, **kwargs: {'action': 'keep', 'criteria': '재개'})
    pb.prepare(''); bound.aliases = {'agent'}
    result = json.loads(execute_pursuit({'op': 'resume', 'why': '사용자 재개'}, 'agent', bound.task))
    assert result['result']['status'] == 'active'


def test_creation_triggers_and_goal_eval_does_not_close(bound, monkeypatch):
    import thread_context as tc
    tc.clear_goal_eval_outcome()
    out = {'task_framing': '여러 날의 일', 'scope': 'pursuit', 'title': '새 과제', 'goal_criteria': '전체 완료'}
    pb.accept_output(out)
    tc.set_goal_eval_outcome(True, 0)
    packet = pb.finish('오늘 단계 완료', [])
    assert packet and bound.ledger.get(packet['id'])['status'] == 'active'
    tc.clear_goal_eval_outcome()


@pytest.mark.parametrize('trigger', ['question', 'not_achieved'])
def test_mechanical_promotion_retains_pending_turn(bound, trigger):
    import thread_context as tc
    tc.clear_goal_eval_outcome()
    if trigger == 'not_achieved': tc.set_goal_eval_outcome(False, 2)
    packet = pb.finish('사용자 확인 필요', [], clarification=trigger == 'question')
    assert packet and bound.ledger.turns(packet['id'])[-1]['state'] == 'pending'
    tc.clear_goal_eval_outcome()


def test_mcp_transports_explicit_clears(monkeypatch):
    import asyncio
    import mcp_server
    captured = []
    monkeypatch.setattr(mcp_server, '_http_identity', lambda ctx: ('agent', None, 'turn', None))
    monkeypatch.setattr(mcp_server, '_post_backend', lambda path, packet, timeout: captured.append(packet) or '{}')
    asyncio.run(mcp_server.pursuit('note', progress='', next='', open_questions=[]))
    assert captured[0]['payload']['progress'] == ''
    assert captured[0]['payload']['next'] == ''
    assert captured[0]['payload']['open_questions'] == []
    assert captured[0]['task_id'] == 'turn'


def test_audit_detects_unpersisted_scope_and_revision(bound, row, monkeypatch):
    import world_pulse_health as health
    reports = []
    monkeypatch.setattr(health, 'save_self_check', reports.append)
    bound.output = {'scope': 'pursuit'}
    assert 'G1' in pb.audit_binding(bound)[0]
    bound.bind(row); bound.revision_count = 1
    assert 'G2' in pb.audit_binding(bound)[0]
    assert len(reports) == 2 and all(not r['success'] for r in reports)


def test_old_breaks_do_not_crowd_out_current_assumptions():
    previous = {'assumptions': [{'text': f'옛 전제 {i}', 'status': 'broken', 'evidence': '과거', 'turn': 'old'} for i in range(12)]}
    patch = pb.framing_patch({'task_framing': '현재 지도', 'assumptions': ['현재 검증할 전제']}, previous)
    assert patch['assumptions'][0]['text'] == '현재 검증할 전제'
    assert len(patch['assumptions']) == 12


def test_new_assumptions_over_limit_are_rejected_not_cut(ledger, row):
    patch = pb.framing_patch({'task_framing': '새 지도', 'assumptions': [f'새 전제 {i}' for i in range(13)]})
    assert len(patch['assumptions']) == 13
    seq = ledger.begin_turn(row['id'], 'write', '전제 갱신')
    with pytest.raises(ValueError, match='12항목'):
        ledger.apply(row['id'], 'write', row['version'], patch, 'overflow', seq)
    assert ledger.get(row['id'])['framing'] == row['framing']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
