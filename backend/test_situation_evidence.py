"""Real producer receipts reach the active execution without a supervisor."""
import boot_paths  # noqa: F401
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest
import execution_turn
import principal
from thread_context import actor_context
from situation_evidence import attach, file_validation
from supervision_store import TurnStore
from test_conversation_handoff import store as conversations  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def active(tmp_path):
    runner = SimpleNamespace(project_path=tmp_path, config={'id': 'executor'}, ai=None)
    with actor_context(agent_id='executor', task_id='situation-test', origin='training'):
        token = execution_turn.enter(runner, request='매출 보고서를 작성하세요')
        binding = execution_turn.current()
        attach(binding, TurnStore(tmp_path / 'evidence'))
        try:
            yield binding
        finally:
            execution_turn.leave(token)


def module(name):
    spec = importlib.util.spec_from_file_location('situation_' + name,
        ROOT / 'data/packages/installed/tools/system_essentials' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_observation_failure_preserves_completed_tool_result(active, monkeypatch):
    from execution_situation import run_tool
    def unavailable(*args):
        raise OSError('evidence disk unavailable')
    monkeypatch.setattr(active.situation, 'evidence', unavailable)
    assert run_tool('save', {}, lambda: {'saved': True}) == {'saved': True}


def test_draft_validation_does_not_certify_original_file(active, tmp_path):
    from document_workspace import DocumentWorkspace
    workspace = DocumentWorkspace(tmp_path / 'office')
    workspace.validate_output({'id': 'doc', 'source_format': 'txt', 'encoding': 'utf-8',
                               'source_uri': str(tmp_path / 'original.txt')}, b'new draft')
    rows = active.situation.snapshot()['observations']
    validation = next(r['latest'] for r in rows if r['latest']['source'] == 'validator')
    assert validation['subject']['kind'] == 'office_blob'
    assert validation['subject_revision'] == hashlib.sha256(b'new draft').hexdigest()
    assert validation['value']['publication'] == 'not_established_by_validation'
    assert not any(r['latest']['subject']['kind'] == 'file' for r in rows)


def test_file_changed_after_validation_reaches_real_openai_request(active, tmp_path):
    from providers.openai import OpenAIProvider
    from situation_delivery import PREFIX
    io = module('essentials_file_io')
    p = tmp_path / 'revenue.csv'
    io.atomic_write_text(p, 'amount\n10\n')
    old = p.read_bytes()
    file_validation(p, old, check='sum', outcome='passed')
    io.atomic_write_text(p, 'amount\n20\n')
    captured = []
    provider = OpenAIProvider(api_key='test', model='test', system_prompt='fixed')
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **args: captured.append(args) or iter(['response']))))
    messages = [{'role': 'system', 'content': 'fixed'}, {'role': 'user', 'content': '보고서를 마무리하세요'}]
    stream = provider._create_stream_with_retry({'messages': messages})
    assert not active.situation.cursors
    assert list(stream) == ['response']
    payload = json.loads(captured[0]['messages'][-1]['content'].removeprefix(PREFIX))
    check = next(r for r in payload['observations'] if r['latest']['facet'] == 'validation:sum')
    assert check['availability'] == 'needs_recheck'
    assert check['latest']['subject_revision'] == hashlib.sha256(old).hexdigest()
    assert messages[0] == {'role': 'system', 'content': 'fixed'}
    assert active.situation.cursors


def test_read_producer_receipt_uses_same_file_identity(active, tmp_path):
    import source_observation as so
    p = tmp_path / 'source.txt'
    io = module('essentials_file_io')
    io.atomic_write_text(p, 'old')
    before = so.file_state(p)
    evidence = so.file_evidence(p, before, hashlib.sha256(b'old').hexdigest(), {'complete': True})
    receipt = so.publish(evidence, 'old')
    rows = [r for r in active.situation.snapshot()['observations'] if r['latest']['facet'] == 'version']
    assert len(rows) == 1
    assert rows[0]['latest']['source_ref']['source_observation_ref'] == receipt


def test_acceptance_timeout_and_failed_result_remain_distinct(active, monkeypatch):
    import task_receipts as tasks
    ref = tasks.receipt('render', 'job')['task_ref']
    monkeypatch.setattr(tasks, '_adapter', lambda *args: lambda ref: tasks.view(ref, tasks.RUNNING))
    assert tasks.wait(ref, timeout=0)['timed_out'] is True
    task = next(r for r in active.situation.snapshot()['observations'] if r['latest']['facet'] == 'receipt')
    assert task['first']['value']['accepted'] is True
    assert task['latest']['value']['state'] == 'running' and task['latest']['value']['timed_out']
    from execution_situation import run_tool
    result = {'success': True, 'result': {'state': 'failed', 'error': 'render unavailable', 'exit': 1}}
    assert run_tool('render_status', {}, lambda: result) is result
    outcomes = [r['latest']['value'] for r in active.situation.snapshot()['observations']
                if r['latest']['facet'] == 'reported_outcome']
    assert {'success': True} in outcomes
    assert {'state': 'failed', 'error': 'render unavailable', 'exit': 1} in outcomes


def test_store_read_observes_committed_document_version(active, tmp_path):
    from office_store import OfficeStore
    store = OfficeStore(tmp_path / 'office')
    store.put('document', {'id': 'doc', 'revision_id': 'v1', 'source_sha256': 'hash1'})
    store.get('document', 'doc')
    store.put('document', {'id': 'doc', 'revision_id': 'v2', 'source_sha256': 'hash2'})
    store.get('document', 'doc')
    rows = [r for r in active.situation.snapshot()['observations'] if r['latest']['subject']['kind'] == 'office_document']
    assert rows[0]['first']['subject_revision'] == 'hash1'
    assert rows[0]['latest']['subject_revision'] == 'hash2'


def test_mcp_response_has_separate_context_preserving_business_value(active, monkeypatch):
    import mcp_server
    from api_supervision import situation_context
    from execution_situation import emit
    emit({'kind': 'result'}, 'state', 'pending', source='producer')
    raw = json.dumps({'success': True, 'value': {'count': 3}})
    def post(path, payload, *args):
        if path == '/ibl/situation':
            return situation_context(payload['agent_id'], payload['task_id'])
        return raw
    monkeypatch.setattr(mcp_server, '_post_backend', post)
    monkeypatch.setattr(mcp_server, 'DEFAULT_AGENT_ID', active.agent)
    monkeypatch.setattr(mcp_server, 'DEFAULT_TASK_ID', active.task)
    blocks = asyncio.run(mcp_server.execute_ibl(code='return 3'))
    assert isinstance(blocks, list) and len(blocks) == 2
    assert json.loads(blocks[0])['value'] == {'count': 3}
    assert blocks[1].startswith('[Execution situation')
    assert not active.situation.cursors  # MCP does not pretend to have a client acknowledgement.


def test_cross_thread_lookup_checks_principal_and_task(active):
    from api_supervision import situation_context
    from execution_situation import emit
    emit({'kind': 'result'}, 'private', 'owned', source='producer')
    def read():
        assert situation_context(active.agent, active.task)['context']
        assert situation_context(active.agent, 'other') == {'active': False}
        with principal._Scope(principal.Principal(kind='member', id='other')):
            assert situation_context(active.agent, active.task) == {'active': False}
    with ThreadPoolExecutor(1) as pool:
        pool.submit(read).result()


def test_no_tools_has_no_extra_model_context(active):
    assert active.situation.prepare('execution') is None


def test_todo_is_model_interpretation_not_completion(active, tmp_path):
    todo = module('essentials_todo')
    todo.write({'todos': [{'content': 'done', 'activeForm': 'doing', 'status': 'completed'}]},
               tmp_path / 'todo.json', module('essentials_file_io'))
    row = next(r for r in active.situation.snapshot()['observations'] if r['latest']['facet'] == 'todos')
    assert row['latest']['basis'] == 'model_interpretation'


def test_resident_registered_job_refreshes_local_result_only(active, monkeypatch):
    import resident_store as resident
    rec = {'device_id': 'device', 'registration': {'generation': 'g', 'state': 'active'}}
    jid = resident.submit(rec, {'op': 'probe'}, 'once')
    active.situation.prepare('executor')
    resident.observe(rec, [{'job_id': jid, 'event_id': 'finished', 'kind': 'result',
                            'payload': {'exit': 0, 'stdout': 'ready'}}])
    payload = active.situation.prepare('executor', budget=12000)
    row = next(r for r in payload['observations'] if r['latest']['subject']['kind'] == 'resident_job')
    assert row['first']['value']['state'] == 'queued'
    assert row['latest']['value'] == {'state': 'succeeded', 'result_observed': True,
                                    'request_id': 'once', 'op': 'probe', 'cwd': None}
    output = next(r['latest'] for r in payload['observations'] if 'stdout' in r['latest']['value'])
    assert output['subject']['context']['device'] == 'device'
    assert output['subject']['context']['task_ref']['task_id'] == jid
    assert output['value']['stdout']['text'] == 'ready'
    assert len(active.situation.refreshers) == 1


def test_interrupted_conversation_restores_last_observation_not_old_goal(conversations, tmp_path):
    import conversation_sessions as sessions
    from conversation_handoff import Handoff
    from execution_situation import emit
    sid = conversations.create()['id']
    runner = SimpleNamespace(project_path=tmp_path, config={'id': 'executor'}, ai=None)
    first = conversations.begin(sid)
    with sessions.scope(first), actor_context(agent_id='executor', task_id='before'):
        handoff = Handoff()
        token = execution_turn.enter(runner, request='old request')
        attach(execution_turn.current(), TurnStore(tmp_path / 'before'), handoff)
        emit({'kind': 'file', 'path': '/source'}, 'version', 'v1', source='producer', observed_at=1)
        execution_turn.leave(token)
        handoff.finish(False)
    conversations.finish(first, 'interrupted')
    second = conversations.begin(sid)
    with sessions.scope(second), actor_context(agent_id='executor', task_id='after'):
        handoff = Handoff()
        assert 'v1' in handoff.recovery()
        token = execution_turn.enter(runner, request='current request')
        try:
            attach(execution_turn.current(), TurnStore(tmp_path / 'after'), handoff)
            state = execution_turn.current().situation
            row = next(r for r in state.snapshot()['observations'] if r['latest']['facet'] == 'version')
            assert row['availability'] == 'last_observed_before_resume'
            assert row['first']['value'] == 'v1'
            assert not state.refreshers
            emit({'kind': 'file', 'path': '/source'}, 'version', 'v1', source='producer', observed_at=2)
            row = next(r for r in state.snapshot()['observations'] if r['latest']['facet'] == 'version')
            assert row['availability'] == 'last_observed'
            assert row['first']['observed_at'] == 1
        finally:
            execution_turn.leave(token)


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
