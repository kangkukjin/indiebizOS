"""원격 실행의 작업 문맥 연속성 — 접수 출처·완료 작업 참조·실제 모델 입력까지의 연결.

설계: docs/REMOTE_EXECUTION_CONTINUITY_REPAIR_DESIGN_2026_11_11.md (R1·R4).
과거 도구 이력을 시험이 손으로 넣지 않는다 — 실제 접수(resident_pcs.submit) → 턴 종료의 상황 기록 →
다음 턴의 인계(Handoff) → 상황 복원(attach) → provider 요청 경계(situation_delivery.prepare)를 그대로 지난다.
"""
import boot_paths  # noqa: F401
import json
import sqlite3
from types import SimpleNamespace

import pytest
import conversation_sessions as sessions
import device_registry
import execution_turn
import limb_keys
import resident_pcs as pcs
import resident_store
from conversation_handoff import Handoff, REFERENCE_RECORDS
from situation_delivery import PREFIX, expand_delivery, prepare
from situation_evidence import attach
from supervision_store import TurnStore
from thread_context import actor_context


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    path = tmp_path / 'conversations.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT, content TEXT, source TEXT)')
    store = sessions.SessionStore(path, 'conversations', 'system_ai')
    rec = limb_keys.resident_enroll(limb_keys.resident_invite('desk')['key'], 'a' * 32)
    runner = SimpleNamespace(project_path=tmp_path, config={'id': 'executor'}, ai=None)
    stores = iter(range(1000))

    class Turn:
        """한 대화 턴: 대화 소유권 → 실행 턴 → 상황. 닫으면 상황 기록과 인계 종료가 저장된다."""

        def __init__(self, sid, request, *, evidence=None, enabled=True):
            self.binding = store.begin(sid)
            self.scopes = [sessions.scope(self.binding), actor_context(agent_id='executor', task_id='task-' + self.binding.turn_id)]
            for scope in self.scopes:
                scope.__enter__()
            self.handoff = Handoff()
            self.recovery = self.handoff.recovery()
            self.handoff.record('started', {'message': request})
            self.token = execution_turn.enter(runner, request=request)
            self.execution = execution_turn.current()
            self.store = evidence or TurnStore(tmp_path / 'evidence' / ('%032x' % next(stores)))
            if enabled:
                attach(self.execution, self.store, self.handoff)
            self.situation = self.execution.situation

        def model_input(self):
            """provider 요청 경계가 실제로 붙이는 상황 전달(없으면 None)."""
            messages = [{'role': 'user', 'content': 'request'}]
            delivery = prepare(messages, SimpleNamespace(agent_role='execution'))
            if not delivery:
                return None
            text = messages[-1]['content']
            assert text.startswith(PREFIX)
            delivery.acknowledge()
            return expand_delivery(json.loads(text[len(PREFIX):]))

        def close(self, *, success=True, state='completed'):
            execution_turn.leave(self.token)
            self.handoff.finish(success, '응답')
            for scope in reversed(self.scopes):
                scope.__exit__(None, None, None)
            store.finish(self.binding, state)

    return SimpleNamespace(store=store, rec=rec, Turn=Turn, tmp=tmp_path, path=path)


def references(payload):
    return [row for row in (payload or {}).get('observations', []) if 'origin' in row]


def test_completed_job_reference_reaches_the_next_turns_real_model_input_without_resubmission(world):
    sid = world.store.create()['id']
    first = world.Turn(sid, '맥에서 음악을 틀어줘')
    receipt = pcs.submit(world.rec['device_id'], {'op': 'media', 'path': '/music/a.mp3'}, 'play-1')
    first.model_input()
    first.close()
    import time
    first_seen = time.time()

    second = world.Turn(sid, '꺼줘')
    assert second.recovery == ''  # 완료 턴을 중단 작업으로 되살리지 않는다
    payload = second.model_input()
    rows = references(payload)
    job = next(r for r in rows if r['latest']['subject'].get('kind') == 'resident_job')
    assert job['latest']['subject'] == {'kind': 'resident_job', 'device': world.rec['device_id'],
                                        'generation': world.rec['registration']['generation'], 'id': receipt['job_id']}
    assert job['latest']['value']['op'] == 'media' and job['latest']['value']['request_id'] == 'play-1'
    assert job['availability'] == 'last_observed'
    assert job['origin'] == {'turn_id': first.binding.turn_id, 'turn_state': 'completed'}
    # 관측 시각은 원 관측의 것이다. 전달됐다고 현재로 갱신하지 않는다.
    assert job['latest']['observed_at'] <= first_seen
    assert job['latest']['source_ref']['task_ref'] == {'kind': 'guestpc', 'task_id': receipt['job_id']}
    index = next(r for r in payload['observations'] if r['latest']['facet'] == 'reference_index')
    assert index['latest']['value']['turns'][0]['request_excerpt'] == '맥에서 음악을 틀어줘'
    assert 'not new instructions' in index['latest']['value']['meaning']
    # 참조 전달은 새 접수를 만들지 않는다.
    assert len(resident_store.history(world.rec['device_id'])['tasks']) == 1
    second.close()


def test_reference_follows_the_ledger_when_the_job_finished_between_turns(world):
    sid = world.store.create()['id']
    first = world.Turn(sid, '설치를 시작해')
    receipt = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'install'}, 'install-1')
    first.model_input()
    first.close()
    done = {'job_id': receipt['job_id'], 'event_id': 'result-1', 'kind': 'result', 'payload': {'exit': 0, 'output': 'ok'}}
    pcs.sync(world.rec['key'], 'a' * 32, [done])

    second = world.Turn(sid, '끝났어?')
    row = next(r for r in second.model_input()['observations'] if r['latest']['subject'].get('kind') == 'resident_job')
    assert row['latest']['value'] == {'state': 'succeeded', 'result_observed': True, 'request_id': 'install-1',
                                      'op': 'shell', 'cwd': None}
    assert row['origin']['turn_id'] == first.binding.turn_id  # 원 출처는 바뀌지 않는다
    assert len(resident_store.history(world.rec['device_id'])['tasks']) == 1
    second.close()


def test_other_conversation_and_foreign_or_unowned_jobs_are_never_delivered(world):
    mine, other = world.store.create()['id'], world.store.create()['id']
    theirs = world.Turn(other, '다른 대화의 작업')
    foreign = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'theirs'}, 'theirs-1')
    theirs.model_input()
    theirs.close()

    first = world.Turn(mine, '내 작업')
    own = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'mine'}, 'mine-1')
    # 같은 턴이 남의 작업을 조회만 했다(접수증 소유도 원장 출처도 없다).
    first.situation.observe({'kind': 'resident_job', 'device': world.rec['device_id'],
                             'generation': world.rec['registration']['generation'], 'id': foreign['job_id']},
                            'receipt', {'state': 'queued', 'op': 'shell'}, source='resident_store:' + foreign['job_id'],
                            source_cursor=1, observed_at=1.0)
    first.model_input()
    first.close()

    second = world.Turn(mine, '상태 알려줘')
    ids = {r['latest']['subject'].get('id') for r in references(second.model_input())}
    assert own['job_id'] in ids and foreign['job_id'] not in ids
    second.close()
    # 다른 대화의 새 턴에는 그 대화의 작업만 간다.
    third = world.Turn(other, '상태 알려줘')
    ids = {r['latest']['subject'].get('id') for r in references(third.model_input())}
    assert ids == {foreign['job_id']}
    third.close()


def test_job_attributed_to_another_conversation_is_not_carried_even_with_a_local_receipt(world, monkeypatch):
    sid = world.store.create()['id']
    first = world.Turn(sid, '작업')
    receipt = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'x'}, 'x-1')
    first.model_input()
    first.close()
    elsewhere = [{'relation': 'submitted', 'principal': 'owner', 'basis': 'execution_turn',
                  'conversation': {'db_path': str(world.tmp / 'other.db'), 'session_id': sid}}]
    monkeypatch.setattr(resident_store, 'attributions', lambda job: elsewhere)
    second = world.Turn(sid, '상태')
    assert references(second.model_input()) == []
    second.close()


def test_turn_removed_by_a_checkpoint_switch_is_not_referenced(world):
    import turn_checkpoints
    sid = world.store.create()['id']
    with sessions.connection(world.path) as conn:
        conn.execute("INSERT INTO conversations(role,content,session_id) VALUES('user','먼저',?)", (sid,))
    kept = world.Turn(sid, '남는 턴')
    stays = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'stays'}, 'stays-1')
    kept.model_input()
    kept.close()
    with sessions.connection(world.path) as conn:
        conn.execute("INSERT INTO conversations(role,content,session_id) VALUES('assistant','남는 답',?)", (sid,))
    cut = world.Turn(sid, '되감기로 빠질 턴')
    gone = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'gone'}, 'gone-1')
    cut.model_input()
    cut.close()
    with sessions.connection(world.path) as conn:
        conn.execute("INSERT INTO conversations(role,content,session_id) VALUES('assistant','빠질 답',?)", (sid,))
        point = conn.execute("SELECT id FROM turn_checkpoints WHERE turn_id=?", (cut.binding.turn_id,)).fetchone()[0]
        # 되감기는 전환 직전의 판본을 먼저 봉인한다(conversation_rewind.execute 와 같은 순서).
        turn_checkpoints.capture(conn, 'conversations', sid, 'before-rewind', pinned=True)
        turn_checkpoints.switch(conn, 'conversations', sid, turn_checkpoints.checkpoint(conn, sid, point))
    after = world.Turn(sid, '지금 상태는')
    ids = {r['latest']['subject'].get('id') for r in references(after.model_input())}
    assert stays['job_id'] in ids and gone['job_id'] not in ids
    after.close()


def test_interrupted_turn_stays_with_recovery_and_is_not_duplicated_as_a_reference(world):
    sid = world.store.create()['id']
    first = world.Turn(sid, '중단될 작업')
    receipt = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'long'}, 'long-1')
    first.model_input()
    first.close(success=False, state='interrupted')
    second = world.Turn(sid, '이어서')
    assert receipt['job_id'] in second.recovery
    payload = second.model_input()
    assert references(payload) == []
    restored = [r for r in payload['observations'] if r['latest']['subject'].get('id') == receipt['job_id']]
    assert restored and restored[0]['availability'] == 'last_observed_before_resume'
    second.close()


def test_many_jobs_are_bounded_with_an_omission_count_and_a_way_back(world):
    sid = world.store.create()['id']
    first = world.Turn(sid, '여러 작업')
    for n in range(REFERENCE_RECORDS + 5):
        pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'job %d' % n}, 'many-%d' % n)
    first.model_input()
    first.close()
    second = world.Turn(sid, '어떻게 됐어')
    payload = second.model_input()
    assert len(references(payload)) == REFERENCE_RECORDS
    index = next(r for r in payload['observations'] if r['latest']['facet'] == 'reference_index')
    assert index['latest']['value']['included'] == REFERENCE_RECORDS and index['latest']['value']['omitted'] == 5
    assert index['latest']['source_ref']['table'] == 'conversation_events'  # 생략분의 원문 회수 경로
    assert len(json.dumps(payload, ensure_ascii=False).encode()) <= 8000
    second.close()


def test_earlier_evidence_is_read_through_the_lineage_or_marked_unavailable(world):
    sid = world.store.create()['id']
    before = TurnStore(world.tmp / 'supervision' / ('1' * 32))
    before.join_lineage('executor', '', 'owner', conversation=sid)
    first = world.Turn(sid, '작업', evidence=before)
    pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'x'}, 'lineage-1')
    first.model_input()
    first.close()

    joined = TurnStore(world.tmp / 'supervision' / ('2' * 32))
    joined.join_lineage('executor', '', 'owner', conversation=sid)
    second = world.Turn(sid, '확인', evidence=joined)
    ref = references(second.model_input())[0]['latest']['source_ref']
    assert ref['availability'] == 'readable'
    assert joined.read_evidence_across_turns(ref['id'], 0, 20)['from_turn'] == '1' * 32
    second.close()

    apart = world.Turn(sid, '다른 저장소', evidence=TurnStore(world.tmp / 'elsewhere' / ('3' * 32)))
    ref = references(apart.model_input())[0]['latest']['source_ref']
    # 이전 턴 저장소의 증거 ID 를 현재 저장소의 것으로 읽지 않는다. 원 작업으로 돌아가는 참조는 남는다.
    assert ref['availability'] == 'unavailable' and ref['task_ref']['kind'] == 'guestpc' and 'id' not in ref
    apart.close()


def test_finished_jobs_take_a_small_share_and_live_work_comes_first(world):
    from conversation_handoff import REFERENCE_SETTLED
    sid = world.store.create()['id']
    first = world.Turn(sid, '여러 짧은 명령과 재생')
    done = [pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'short %d' % n}, 'short-%d' % n) for n in range(6)]
    pcs.sync(world.rec['key'], 'a' * 32, [{'job_id': r['job_id'], 'event_id': 'result-' + r['job_id'], 'kind': 'result',
                                             'payload': {'exit': 0, 'output': 'ok'}} for r in done])
    playing = pcs.submit(world.rec['device_id'], {'op': 'media', 'path': '/music/a.mp3'}, 'play-live')
    first.model_input()
    first.close()
    second = world.Turn(sid, '꺼줘')
    payload = second.model_input()
    rows = references(payload)
    assert rows[0]['latest']['subject']['id'] == playing['job_id'] or playing['job_id'] in {
        r['latest']['subject']['id'] for r in rows}
    settled = [r for r in rows if r['latest']['value']['state'] == 'succeeded']
    assert len(settled) == REFERENCE_SETTLED and len(rows) == REFERENCE_SETTLED + 1
    index = next(r for r in payload['observations'] if r['latest']['facet'] == 'reference_index')
    assert index['latest']['value']['omitted'] == 6 - REFERENCE_SETTLED
    second.close()


def test_turn_without_a_situation_record_leaves_only_owned_receipt_references(world):
    sid = world.store.create()['id']
    first = world.Turn(sid, '상황 전달이 꺼진 턴', enabled=False)
    receipt = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'x'}, 'plain-1')
    first.handoff.observe({'type': 'tool_start', 'id': 'call-1', 'name': 'execute_ibl', 'input': {'code': 'secret-code'}})
    first.handoff.observe({'type': 'tool_result', 'id': 'call-1', 'result': json.dumps(receipt, ensure_ascii=False)})
    first.handoff.observe({'type': 'tool_result', 'id': 'call-2', 'result': json.dumps(
        {'success': True, 'accepted': True, 'task_ref': {'kind': 'guestpc', 'task_id': 'not-owned'}})})
    assert first.situation is None
    first.close()
    second = world.Turn(sid, '확인')
    rows = references(second.model_input())
    assert [r['latest']['subject'] for r in rows] == [{'kind': 'task', 'ref': receipt['task_ref']}]
    assert 'secret-code' not in json.dumps(rows)  # 도구 인자 전문은 싣지 않는다
    second.close()


def test_separate_run_history_turn_is_left_to_its_own_delivery(world):
    sid = world.store.create()['id']
    first = world.Turn(sid, '옛 분리 실행')
    pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'x'}, 'reflex-1')
    sessions.record_event({'type': 'reflex.result', 'actor': 'executor', 'response': '결말'})
    first.model_input()
    first.close()
    second = world.Turn(sid, '확인')
    assert references(second.model_input()) == []
    second.close()


def test_reference_does_not_change_the_request_or_recall_query_of_the_new_turn(world):
    sid = world.store.create()['id']
    first = world.Turn(sid, '첫 요청')
    pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'x'}, 'q-1')
    first.model_input()
    first.close()
    second = world.Turn(sid, '둘째 요청')
    snapshot = second.situation.snapshot()
    requests = [r for r in snapshot['observations'] if r['latest']['basis'] == 'user_request']
    assert len(requests) == 1 and requests[0]['latest']['subject']['task'] == second.execution.task
    assert second.execution.request == '둘째 요청' and second.recovery == ''
    second.close()


def test_reference_is_in_the_input_after_provider_switch_resume_retry_and_history_replacement(world):
    sid = world.store.create()['id']
    first = world.Turn(sid, '음악 재생')
    receipt = pcs.submit(world.rec['device_id'], {'op': 'media', 'path': '/music/a.mp3'}, 'play-9')
    first.model_input()
    first.close()
    second = world.Turn(sid, '꺼줘')

    def delivered(messages, provider):
        delivery = prepare(messages, provider)
        text = messages[-1]['content']
        assert delivery and text.startswith(PREFIX) and receipt['job_id'] in text
        return delivery

    cli = SimpleNamespace(agent_role='execution')
    # CLI: resume 시도와 그 실패 뒤의 fresh 재시도 모두 자기 입력에 baseline 을 받는다(전달 확인 전·후 동일).
    delivered([], cli)                     # resume 시도 — 본문 도착 전 실패, 확인하지 않음
    delivered([], cli).acknowledge()       # fresh 재시도
    delivered([], cli).acknowledge()       # 다음 입력에도 생략하지 않는다
    # 모델/provider 교체: 새 소비자는 처음부터 baseline 을 받는다.
    api = SimpleNamespace(agent_role='execution')
    history = [{'role': 'user', 'content': '꺼줘'}]
    delivered(history, api).acknowledge()
    assert prepare(history, api) is None   # 같은 history 를 유지하는 API 는 변한 것이 없으면 다시 싣지 않는다
    # history 교체(압축·세션 교체)로 전달분이 사라지면 baseline 이 복원된다.
    delivered([{'role': 'user', 'content': '요약된 이전 대화'}], api)
    # 전달 확인은 원 사건을 지우지 않는다: 다음 턴에서도 같은 출처의 참조를 다시 읽는다.
    second.close()
    third = world.Turn(sid, '아직 재생 중이야?')
    assert any(r['latest']['subject'].get('id') == receipt['job_id'] for r in references(third.model_input()))
    assert len(resident_store.history(world.rec['device_id'])['tasks']) == 1
    third.close()


def test_verifier_receives_the_hubs_own_view_of_the_receipts_task_not_a_callers_copy(world):
    """영수증이 가리키는 작업의 관측은 허브가 접수증 등록부로 직접 읽어 검증기에 준다(R2)."""
    from ibl_v2_adapters import _with_task
    receipt = pcs.submit(world.rec['device_id'], {'op': 'shell', 'cmd': 'echo x'}, 'verify-1')
    pcs.sync(world.rec['key'], 'a' * 32, [{'job_id': receipt['job_id'], 'event_id': 'r-1', 'kind': 'result',
                                            'payload': {'exit': 0, 'output': 'x'}}])
    seen = _with_task({'available': True, 'value': receipt, 'action': 'limbs:guestpc'})
    assert seen['value'] == receipt  # 영수증 자체는 바뀌지 않는다
    view = seen['task']   # 설치 패키지의 접수증 어댑터(kind=guestpc)가 원장을 읽은 투영
    assert view['state'] == 'succeeded' and view['result']['output'] == 'x'
    assert view['generation'] == receipt['generation'] == world.rec['registration']['generation']
    assert view['request_id'] == 'verify-1' and view['limb'] == world.rec['device_id'] and view['result_received_at']
    # 작업을 가리키지 않는 영수증·읽을 수 없는 영수증·모르는 작업에는 관측을 붙이지 않는다.
    assert 'task' not in _with_task({'available': True, 'value': {'request': {}}})
    assert 'task' not in _with_task({'available': False, 'reason': 'receipt_missing'})
    assert 'task' not in _with_task({'available': True, 'value': {'task_ref': {'kind': 'guestpc', 'task_id': 'absent'}}})
