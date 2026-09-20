"""과제 연결은 현재 모델의 선택만 소비하고 전경에 별도 AI·요약 호출을 추가하지 않는다."""
import boot_paths  # noqa: F401
import json
from types import SimpleNamespace

import pytest
import pursuit_bind as pb
from pursuit_ledger import PursuitLedger
from pursuit_tools import execute_pursuit


@pytest.fixture
def context(tmp_path, monkeypatch):
    ledger = PursuitLedger(tmp_path / 'db.sqlite', 'owner')
    row = ledger.create('보고서', '자료와 보고서 완성', 'seed')
    b = pb.Binding(None, ledger, 'owner', 'turn', '오늘 날씨는?', [])
    b.aliases = {'owner'}
    token = pb._current.set(b)
    monkeypatch.setattr('consciousness_agent.oneshot_ai_call', lambda *a, **k: pytest.fail('전경 AI'))
    monkeypatch.setattr(pb, 'summarize_pending', lambda *a, **k: pytest.fail('전경 요약'))
    yield b, row
    pb._current.reset(token)


def bind(b, row, **kw):
    return json.loads(execute_pursuit({'op': 'bind', 'id': row['id'], 'why': '현재 요청은 같은 보고서의 후속 작업', **kw},
                                     b.agent, b.task))


@pytest.mark.parametrize('message', ['오늘 날씨는?', '보고서와 무관한 질문', '그 보고서는?', 'id'])
def test_candidates_never_write_or_call_model(context, message):
    b, row = context
    b.message = row['id'] if message == 'id' else message
    before = b.ledger.get(row['id'])
    assert row['id'] in pb.prepare()
    assert b.row is None and b.ledger.get(row['id']) == before
    assert not b.ledger.turns(row['id'])


def test_bind_is_idempotent_and_records_model_source(context, monkeypatch):
    b, row = context
    events = []
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda *args: events.append(args))
    supervisor = SimpleNamespace(pursuit=b, original_pursuit=None)
    monkeypatch.setattr('supervision_bus.current', lambda *a: supervisor)
    assert bind(b, row)['success'] and bind(b, row)['success']
    assert len(b.ledger.turns(row['id'])) == 1
    assert events == [('pursuit.bound', {'id': row['id'], 'source': 'execution',
                                      'reason': '현재 요청은 같은 보고서의 후속 작업'})]
    assert supervisor.original_pursuit['goal_criteria'] == row['goal_criteria']


@pytest.mark.parametrize('why', ['', None, ' ', [], 'x' * 801])
def test_connection_requires_bounded_reason_before_writing(context, why):
    b, row = context
    assert not bind(b, row, why=why)['success']
    assert b.row is None and not b.ledger.turns(row['id'])


def test_owner_task_and_unknown_id_boundaries(context):
    b, row = context
    other = PursuitLedger(b.ledger.db_path, 'other').create('비공개', '타 자아 목표', 'seed')
    for candidate in [other, {'id': 'pursuit_missing'}]:
        assert not bind(b, candidate)['success']
    assert not json.loads(execute_pursuit({'op': 'bind', 'id': row['id'], 'why': 'x'}, b.agent, 'wrong-task'))['success']
    assert b.row is None and not b.ledger.turns(row['id'])
    b.message = other['id']
    assert other['id'] not in pb.prepare()


def test_busy_binding_failure_does_not_leave_phantom_row(context):
    b, row = context
    b.ledger.begin_turn(row['id'], 'another', '진행 중', execution=True)
    assert not bind(b, row)['success']
    assert b.row is None and b.seq == 0
    assert len(b.ledger.turns(row['id'])) == 1


def test_detached_turn_cannot_be_rebound_and_other_connection_needs_detach(context):
    b, row = context
    other = b.ledger.create('다른 과제', '다른 목표', 'other')
    assert bind(b, row)['success']
    assert not bind(b, other)['success'] and b.row['id'] == row['id']
    b.detach('현재 질문과 무관')
    assert not bind(b, row)['success'] and b.row is None
    assert bind(b, other)['success']
    assert not b.ledger.turns(row['id'], pending_only=True)


def test_pending_raw_survives_and_is_returned_without_summary(context):
    b, row = context
    b.ledger.begin_turn(row['id'], 'previous', '파일 생성')
    b.ledger.finish_turn(row['id'], 'previous', '만든 파일이 있음', [{'name': 'write'}], interrupted=True)
    result = bind(b, row)
    pending = result['result']['pending_turns']
    assert len(pending) == 1 and pending[0]['state'] == 'interrupted'
    assert pending[0]['response'] == '만든 파일이 있음'
    assert '실제 결과를 확인' in result['result']['directive']
    assert b.ledger.turns(row['id'])[0]['state'] == 'interrupted'


@pytest.mark.parametrize('patch', [ {'pursuit_id': 1}, {'pursuit_reason': ''},
                                   {'pursuit_id': 'unknown'}, {'task_framing': 'x' * 3001}])
def test_invalid_conscious_connection_has_no_writes(context, patch):
    b, row = context
    out = {'scope': 'pursuit', 'pursuit_id': row['id'], 'pursuit_reason': '후속 작업',
           'task_framing': '현재 문제', **patch}
    with pytest.raises(ValueError):
        pb.accept_output(out)
    assert b.row is None and b.ledger.list()['total'] == 1
    assert not b.ledger.turns(row['id'])


def test_conscious_selection_uses_existing_object_and_exposes_pending(context, monkeypatch):
    b, row = context
    b.ledger.begin_turn(row['id'], 'old', '작업')
    b.ledger.finish_turn(row['id'], 'old', '지난 결과', [])
    events = []
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda *args: events.append(args))
    out = {'scope': 'pursuit', 'pursuit_id': row['id'], 'pursuit_reason': '후속 작업',
           'task_framing': '현재 문제', 'title': '', 'goal_criteria': ''}
    pb.validate_output(out)
    assert b.row is None
    pb.accept_output(out)
    assert b.row['id'] == row['id'] and b.ledger.list()['total'] == 1
    assert b.row['goal_criteria'] == row['goal_criteria']
    assert '<pending>' in pb.refresh_memory('')
    assert events[0][1]['source'] == 'consciousness'


def test_reframe_can_connect_existing_without_creating_duplicate(context):
    b, row = context
    ch = SimpleNamespace(pursuit=b, original={}, execution_memory='')
    pb.revised(ch, {'scope': 'turn', 'pursuit_id': row['id'], 'pursuit_reason': '같은 목표의 정정',
                    'task_framing': '수정된 문제'}, '옛 전제', '현재 발화')
    assert b.row['id'] == row['id'] and b.ledger.list()['total'] == 1
    assert b.row['assumptions'][0]['status'] == 'broken'
    assert pb.audit_binding(b) == []


def test_catalog_budget_and_explicit_id_beyond_first_page(context):
    b, row = context
    for i in range(105):
        b.ledger.create(f'과제{i}', '<&>' * 500, f'seed{i}')
    b.message = row['id'] + '에 이어서'
    text = pb.prepare()
    assert row['id'] in text and len(text) < 6000
    assert 'read section=list' in text and '목표 발췌' in text
    assert '<&>' not in text and b.row is None


def test_mcp_transports_bind_and_original_turn_read(monkeypatch):
    import asyncio
    import mcp_server
    packets = []
    monkeypatch.setattr(mcp_server, '_http_identity', lambda ctx: ('owner', None, 'active-turn', None))
    monkeypatch.setattr(mcp_server, '_post_backend', lambda path, packet, timeout: packets.append(packet) or '{}')
    asyncio.run(mcp_server.pursuit('bind', id='existing', why='same goal'))
    asyncio.run(mcp_server.pursuit('read', id='existing', section='turns', detail=True, task_id='previous-turn'))
    assert packets[0]['payload']['op'] == 'bind' and packets[0]['payload']['why'] == 'same goal'
    assert packets[1]['task_id'] == 'active-turn'
    assert packets[1]['payload']['task_id'] == 'previous-turn' and packets[1]['payload']['detail'] is True


@pytest.mark.parametrize('prefix', ['', 'mcp__indiebizos__'])
def test_context_update_can_record_existing_pursuit_without_starting_new_work(prefix):
    from turn_scope import allows_context_tool
    for op in ['read', 'bind', 'note', 'goal', 'detach']:
        assert allows_context_tool(prefix + 'pursuit', {'op': op})
    for op in ['open', 'done', 'resume', 'abandon', 'park', 'wait']:
        assert not allows_context_tool(prefix + 'pursuit', {'op': op})


def test_busy_replacement_is_rejected_before_detaching_current(context):
    b, row = context
    assert bind(b, row)['success']
    other = b.ledger.create('다른 과제', '다른 목표', 'other')
    b.ledger.begin_turn(other['id'], 'other-turn', '작업 중', execution=True)
    with pytest.raises(ValueError, match='다른 턴'):
        pb.accept_output({'scope': 'turn', 'detach_pursuit': True, 'pursuit_id': other['id'],
                          'pursuit_reason': '대상 변경', 'task_framing': '현재 문제'})
    assert b.row['id'] == row['id']
    assert b.ledger.turns(row['id'])[0]['state'] == 'running'


def test_mcp_thread_binding_keeps_episode_trace_and_supervisor(context, monkeypatch):
    import asyncio
    import episode_logger as el
    import supervision_bus as bus
    from api_pursuits import bridge, ToolRequest
    b, row = context
    supervisor = SimpleNamespace(pursuit=b, original_pursuit=None, done_request=None, task=b.task)
    events = []
    monkeypatch.setattr(el, 'record_trajectory_event', lambda kind, data:
                        events.append((kind, el.current_trajectory_identity(), data)))
    with el.trajectory_scope(b.task, episode_id=9876):
        b.trace = el.capture_trace()
    with pb._lock:
        pb._sessions[b.task] = b
    bus.register(supervisor, [b.agent])
    token = pb._current.set(None)  # HTTP 워커에는 파이프라인의 ContextVar가 없다.
    try:
        result = asyncio.run(bridge(ToolRequest(agent_id=b.agent, task_id=b.task,
            payload={'op': 'bind', 'id': row['id'], 'why': '같은 보고서 후속 질문'})))
        assert result['success']
        assert b.ledger.turns(row['id'])[0]['episode_id'] == '9876'
        bound_event = next(e for e in events if e[0] == 'pursuit.bound')
        assert bound_event[1]['episode_id'] == 9876 and bound_event[1]['run_id'] == el.trajectory_run_id(b.task)
        assert supervisor.original_pursuit['id'] == row['id']
        assert el.capture_trace() is None
        result = asyncio.run(bridge(ToolRequest(agent_id=b.agent, task_id=b.task,
            payload={'op': 'detach', 'why': '연결을 정정'})))
        assert result['success'] and supervisor.original_pursuit is None
    finally:
        pb._current.reset(token)
        bus.unregister(supervisor)
        pb._sessions.pop(b.task, None)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
