"""과제 원장의 실제 SQLite 계약과 S1~S3. 모델/실사용 데이터 없이 경계를 검증한다."""
import boot_paths  # noqa: F401
import associative_recall
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


def test_s1_current_consciousness_connects_and_rewrites_without_shrinking_goal(bound, row):
    bound.message = row['id'] + ' 아니 서울이 아니라 부산이야'
    memory = pb.prepare()
    assert bound.row is None
    original = bound.runner._run_consciousness
    bound.runner._run_consciousness = lambda *a, **k: {
        **original(), 'pursuit_id': row['id'], 'pursuit_reason': '현재 사용자 대상 정정'}
    out = pb.run_consciousness(bound.runner, bound.message, [], memory)
    updated = bound.ledger.get(row['id'])
    assert '부산' in updated['framing'] and out['achievement_criteria'] == '부산 데이터 조회'
    assert updated['goal_criteria'] == row['goal_criteria']
    assert out['_framing_source'] == 'fresh_consciousness'
    assert updated['assumptions'][0]['text'] == '대상은 부산이다'


def test_s2_executor_chooses_old_pursuit_after_other_work(bound, row, monkeypatch):
    bound.ledger.create('다른 일', '다른 기준', 'unrelated')
    monkeypatch.setattr(pb, 'ask_json', lambda *a, **k: pytest.fail('전경 AI 호출'))
    memory = pb.prepare()
    assert bound.row is None and row['id'] in memory
    bound.aliases = {'agent'}
    result = json.loads(execute_pursuit({'op': 'bind', 'id': row['id'],
                                       'why': '최근 대화의 월별 보고서 후속 작업'}, 'agent'))
    assert result['success'] and result['result']['progress'] == '원본 수집 완료'
    assert result['result']['pending_turns'] == []
    assert result['result']['goal_criteria'] == row['goal_criteria']


def test_current_consciousness_owns_criteria_despite_old_framing(bound, row):
    bound.ledger.apply(row['id'], 'seed', row['version'],
                       {'framing_meta': {'guide_files': ['old.md'], 'imagined_ibl': '옛 경로'}}, 'seed', 0)
    pb.connect(bound, row['id'], '사용자가 이 과제의 대상 정정')
    out = pb.run_consciousness(bound.runner, bound.message, [], pb.refresh_memory(pb.prepare()))
    assert out['task_framing'] == '부산의 월별 보고서를 만든다'
    assert out['achievement_criteria'] == '부산 데이터 조회'
    assert not out.get('guide_files') and not out.get('imagined_ibl')
    assert bound.ledger.get(row['id'])['goal_criteria'] == row['goal_criteria']


@pytest.mark.parametrize('wrong_binding', [False, True])
def test_episode3762_wrong_selection_cannot_replace_current_question(bound, row, monkeypatch, wrong_binding):
    bound.message = '그런데 부정적인 여론에도 제주 방문이 계속되는 이유는?'
    bound.history = [{'role': 'user', 'content': '제주 방문 증가와 당시 정책은?'},
                     {'role': 'assistant', 'content': '관광과 투자를 나누어 제주 정책을 조사했습니다.'}]
    before = bound.ledger.get(row['id'])
    monkeypatch.setattr(pb, 'ask_json', lambda *a, **k: pytest.fail('별도 연결 판단 금지'))
    memory = pb.prepare()
    assert bound.row is None and not bound.ledger.turns(row['id'])
    if wrong_binding:
        pb.connect(bound, row['id'], '잘못된 연결을 주입해 회수를 검증')
    calls = []
    def fresh(message, history, memory):
        calls.append(message)
        assert history[-1]['content'].startswith('관광과 투자')
        return {'scope': 'turn', 'detach_pursuit': True, 'pursuit_id': None,
                'task_framing': '제주 유입 지속 원인을 설명한다', 'achievement_criteria': '원인 설명'}
    bound.runner._run_consciousness = fresh
    out = pb.run_consciousness(bound.runner, bound.message, bound.history, memory)
    assert len(calls) == 1 and out['achievement_criteria'] == '원인 설명'
    assert bound.row is None and '<pursuit ' not in pb.refresh_memory(memory)
    assert pb.finish('현재 제주 질문의 답변') is None
    after = bound.ledger.get(row['id'])
    assert after['version'] == before['version']
    assert after['framing'] == before['framing'] and after['next'] == before['next']
    assert not bound.ledger.turns(row['id'], pending_only=True)


def test_executor_detach_keeps_evidence_and_blocks_late_summary(bound, row):
    bound.aliases = {'agent'}
    bound.bind(row)
    seq = bound.seq
    bound.ledger.observe(row['id'], bound.task, {'result': '실제 관찰'}, 1)
    result = json.loads(execute_pursuit({'op': 'detach', 'why': '현재 요청과 무관'}, 'agent'))
    assert result['success'] and bound.row is None
    assert bound.ledger.get(row['id'])['status'] == 'active'
    turn = bound.ledger.turns(row['id'])[0]
    assert turn['state'] == 'detached' and turn['tools'] == [{'result': '실제 관찰'}]
    unchanged = bound.ledger.apply(row['id'], bound.task, row['version'],
        {'next': '잘못된 후속 질문'}, 'late-summary', seq, summary=True)
    assert unchanged['next'] == row['next']
    assert not bound.ledger.turns(row['id'], pending_only=True)


def test_detach_and_new_pursuit_do_not_mix_records(bound, row):
    bound.bind(row)
    pb.accept_output({'scope': 'pursuit', 'detach_pursuit': True,
                      'title': '새 요청', 'goal_criteria': '새 목표', 'task_framing': '새 문제'})
    assert bound.row['id'] != row['id'] and bound.row['goal_criteria'] == '새 목표'
    assert bound.ledger.turns(row['id'])[0]['state'] == 'detached'


def test_same_turn_creation_after_detach_does_not_revive_old_object(ledger):
    first = ledger.create('잘못된 과제', '옛 목표', 'same_turn')
    ledger.begin_turn(first['id'], 'same_turn', '현재 요청')
    ledger.detach_turn(first['id'], 'same_turn', '잘못된 규정')
    second = ledger.create('새 과제', '현재 목표', 'same_turn')
    assert second['id'] != first['id']
    assert ledger.create('재시도', '현재 목표', 'same_turn')['id'] == second['id']


def test_reframe_after_executor_detach_does_not_resurrect_old_goal(bound, row):
    bound.bind(row)
    bound.output = {'scope': 'pursuit', 'goal_criteria': '옛 전체 목표'}
    memory = pb.render_body(row)
    bound.detach('오연결')
    channel = SimpleNamespace(pursuit=bound, original={'task_framing': '옛 문제',
        'achievement_criteria': '옛 기준'}, execution_memory=memory)
    out = {'scope': 'turn', 'task_framing': '현재 질문', 'achievement_criteria': '현재 답변'}
    pb.revised(channel, out, '옛 과제와 무관', '최근 대화')
    assert bound.row is None and '<pursuit ' not in channel.execution_memory
    assert bound.output['task_framing'] == '현재 질문'
    assert not pb.audit_binding(bound)


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


def test_s3_pending_read_does_not_wait_for_summary(bound, row, monkeypatch):
    bound.ledger.begin_turn(row['id'], 'a', '보고서 생성')
    bound.ledger.finish_turn(row['id'], 'a', '보고서 생성 완료', [{'name': 'write', 'result': 'report.pdf'}])
    monkeypatch.setattr(pb, 'ask_json', lambda *a, **k: pytest.fail('전경 요약 금지'))
    bound.message = row['id'] + ' 이어서'
    memory = pb.prepare()
    assert bound.row is None and row['id'] in memory
    bound.aliases = {'agent'}
    result = json.loads(execute_pursuit({'op': 'bind', 'id': row['id'], 'why': '보고서 후속 검증'}, 'agent'))
    assert result['success']
    assert result['result']['pending_turns'][0]['response'] == '보고서 생성 완료'
    assert next(t for t in bound.ledger.turns(row['id']) if t['task_id'] == 'a')['state'] == 'pending'
    assert '반복 실행 금지' in pb.refresh_memory(memory)


@pytest.mark.parametrize('recovers', [True, False])
def test_background_summary_validates_all_fields_and_preserves_raw(ledger, row, monkeypatch, recovers):
    ledger.begin_turn(row['id'], 'previous', '자료를 정리해')
    ledger.finish_turn(row['id'], 'previous', '정리한 원문', [])
    calls = []
    invalid = {'progress': '가' * 3001, 'next': '나' * 601}
    def model(prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps(invalid, ensure_ascii=False)
        assert 'progress: 3000자' in prompt and 'next: 600자' in prompt
        assert ledger.get(row['id'])['progress'] == row['progress']
        return json.dumps({'progress': '정리 완료', 'next': '현재 질문 검토'} if recovers else invalid)
    monkeypatch.setattr('consciousness_agent.oneshot_ai_call', model)
    if recovers:
        pb.summarize_pending(ledger, row['id'])
        assert ledger.get(row['id'])['next'] == '현재 질문 검토'
    else:
        with pytest.raises(ValueError, match='진행 요약'):
            pb.summarize_pending(ledger, row['id'])
    assert len(calls) == 2
    previous = next(t for t in ledger.turns(row['id']) if t['task_id'] == 'previous')
    assert previous['response'] == '정리한 원문'
    assert (previous['state'] == 'applied') == recovers
    assert bool(previous['error']) != recovers


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


@pytest.mark.parametrize("lane", ["EXECUTE", "REFLEX", "THINK"])
def test_pipeline_connects_in_current_model_without_preflight(tmp_path, monkeypatch, lane):
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
            result = json.loads(execute_pursuit({'op': 'bind', 'id': row['id'], 'why': '사용자 대상 정정'}, 'agent'))
            assert result['success']
            yield {'type': 'tool_start', 'name': 'lookup', 'input': {'city': '부산'}}
            yield {'type': 'tool_result', 'result': '부산 조회 완료'}
            yield {'type': 'final', 'content': '부산 조회 완료'}
    class Runner(ap.CognitivePipelineMixin, CognitiveConsciousnessMixin):
        config = {'name': 'agent'}
        agent_id = 'agent'
        project_path = tmp_path
        full_calls = 0
        def _sync_execution_gear(self): pass
        _associate = associative_recall.stub('', 0.99 if lane == 'REFLEX' else 0, 'lookup' if lane == 'REFLEX' else '')
        def _classify_request(self, *a):
            assert lane == 'THINK'
            return 'THINK'
        def _run_consciousness(self, *a, **kw):
            self.full_calls += 1
            return {'task_framing': '부산만 조회한다', 'achievement_criteria': '', 'assumptions': ['대상 부산'],
                    'pursuit_id': row['id'], 'pursuit_reason': '사용자의 대상 정정'}
        def _consciousness_needs_repair(self, out): return False
        def _build_system_prompt_split(self, role, out, memory): return 'system', memory
        def _apply_consciousness_to_history(self, history, out): return history
        def _extract_achievement_criteria(self, out): return ''
        def _after_response_async(self, *a, **kw): packets.append(kw.get('pursuit_packet'))
    runner = Runner(); runner.ai = AI()
    monkeypatch.setattr(ap, '_reload_gate_notice', lambda: '')
    monkeypatch.setattr(core, '_restore_provider', lambda *a: None)
    monkeypatch.setattr(core, '_switch_to_midtier', lambda *a: None)
    # 감독 신원 연결 후 이 통합 시험도 최종 검수에 도달한다. 실제 CLI/모델 호출은 금지.
    monkeypatch.setattr('final_evaluator.invoke', lambda *a, **k: json.dumps({
        'status': 'UNKNOWN', 'reason': '조회만 끝났고 전체 보고서는 아직 완성되지 않았다'}))
    monkeypatch.setattr(pb, 'ask_json', lambda *a, **k: pytest.fail('전경 과제 AI 호출'))
    monkeypatch.setattr('model_resolver.consciousness_enabled', lambda: lane == 'THINK')
    try:
        events = list(runner.cognitive_stream(row['id'] + ' 아니 부산으로 조회해'))
        assert runner.full_calls == (1 if lane == 'THINK' else 0)
        if lane != 'THINK':
            assert not any(e.get('type') == 'cognition' and e.get('decision') == 'think' for e in events)
        assert packets and packets[0]['id'] == row['id']
        turn = ledger.turns(row['id'])[-1]
        assert turn['state'] == 'pending' and '부산 조회' in turn['response']
        assert pb.current() is None and 'pipeline_turn' not in pb._sessions
        assert '<pursuits ' in seen[0]
        assert ('<pursuit ' in seen[0]) == (lane == 'THINK')
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
    assert row['id'] in pb.prepare()
    pb.connect(bound, row['id'], '사용자 명시 재개'); bound.aliases = {'agent'}
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


def test_turns_read_is_brief_by_default_and_full_on_detail(ledger, row, bound):
    """2026-09-16 ep3814: 턴 2건 읽기에 3만 자가 들어오던 자리 — 기본은 요약, 전문은 detail=true 로 고른 턴만."""
    long_response = '응답 본문 ' * 300
    tools = [{'tool_name': 'execute_ibl', 'input': {'code': '[self:time]{}'}, 'success': True},
             {'tool_name': 'execute_ibl', 'input': {'code': '[sense:search]{query:"x"}'}, 'success': False}]
    ledger.begin_turn(row['id'], 'old_turn', '수원에서 속초 가는 길 ' * 30)
    ledger.finish_turn(row['id'], 'old_turn', long_response, tools)
    bound.bind(row); bound.aliases = {'agent'}
    read = lambda **extra: json.loads(execute_pursuit({'op': 'read', 'id': row['id'], 'section': 'turns', **extra},
                                                       'agent', bound.task))['result']
    brief = read()
    item = [t for t in brief['items'] if t['task_id'] == 'old_turn'][0]
    assert brief['detail'] is False and item['tools'] == {'count': 2, 'failed': 1, 'names': ['execute_ibl']}
    assert item['response'].endswith('자)') and len(item['response']) < 450 and len(item['input']) < 260
    assert item['full_chars'] > len(json.dumps(item, ensure_ascii=False))
    full = read(detail=True, task_id='old_turn')
    assert full['detail'] is True and len(full['items']) == 1 and full['items'][0]['tools'] == tools
    assert full['items'][0]['response'] == long_response
    # 기본 read 의 pending_turns 도 요약이다
    default = json.loads(execute_pursuit({'op': 'read', 'id': row['id']}, 'agent', bound.task))['result']
    assert all('full_chars' in t and isinstance(t['tools'], dict) for t in default['pending_turns'])
