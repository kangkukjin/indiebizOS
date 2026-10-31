"""원래 업무→한정 구현 수리→원래 업무의 연결과 통제 기반 변경 거절."""
import boot_paths  # noqa: F401
import json
import sqlite3
import subprocess
import sys
import shlex
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import conversation_sessions as sessions
import component_continuation as parents
import execution_turn
import repair_continuation as journal
import task_repair as repair
import red_grant
import model_resolver  # noqa: F401 — 임시 몸 경로를 패치하기 전에 정본 설정 경로를 결속
from thread_context import actor_context
from providers.base import turn_token_scope, ProviderMetrics, read_turn_tokens
from test_repair_staging import _make_repo, _load_handler
from test_essentials_component_repair import invoke
from test_conscious_supervisor import supervisor, verdict, finish  # noqa: F401


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path / 'repo')
    path = repo / 'backend/ibl/ibl_v2_parser.py'
    path.parent.mkdir()
    path.write_text('VALUE = 1\n')
    (repo / 'backend/test_parser_behavior.py').write_text(
        'def test_parser_value():\n    import runpy\n    assert runpy.run_path("backend/ibl/ibl_v2_parser.py")["VALUE"] == 2\n')
    boot = repo / 'backend/boot_paths.py'
    boot.write_text(boot.read_text().replace('"base", "cognition"', '"base", "cognition", "ibl"'))
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.test'], cwd=repo, check=True)
    (repo / '.gitignore').write_text('.worktrees/\ndata/system_ai_state/\ndata/restart_control/\nconversations.db*\n')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.test',
                    'commit', '-qm', 'parser fixture'], cwd=repo, check=True)
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: repo)
    monkeypatch.setattr('runtime_utils.get_code_root', lambda: repo)
    monkeypatch.setattr('runtime_utils.get_source_root', lambda: repo)
    monkeypatch.setattr(journal, 'state_root', lambda: repo / 'data/system_ai_state')
    monkeypatch.setattr('runtime_work.registry', lambda: NS(generation='original'))
    monkeypatch.setattr('principal.is_owner', lambda: True)
    db = repo / 'conversations.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT, content TEXT, source TEXT)')
    store = sessions.SessionStore(db, 'conversations', 'system_ai')
    bound = store.begin(store.create()['id'])
    runner = NS(config={'_is_system_ai': True})
    controller = NS(repair_granted=False, framing={'achievement_criteria': '결과 보고서 저장'},
                    store=NS(directory=repo / 'evidence'), apply_scheduled=None)
    monkeypatch.setattr('supervision_bus.current', lambda *a, **kw: controller)
    turn = execution_turn.Binding(runner, 'system_ai', 'original', context={}, conversation=bound,
                                 request='자료를 정리해서 보고서로 저장해줘', component_repair_allowed=True)
    handler = _load_handler(); handler._REPO_ROOT = repo
    token = execution_turn._current.set(turn)
    try:
        with actor_context(agent_id='system_ai', task_id='original', origin='user'), sessions.scope(bound), \
                turn_token_scope('system_ai', 'original', hard_token_limit=1000, deadline_s=600):
            ProviderMetrics().record_request(1, 100, 20)
            yield NS(repo=repo, path=path, handler=handler, turn=turn, controller=controller, store=store)
    finally:
        red_grant.revoke_grant()
        execution_turn._current.reset(token)


def propose(e):
    result = invoke(e.handler, e.repo, 'patch_op', {'op': 'propose', 'path': str(e.path),
                     'reason': '관측한 파서 구현 결함이 자료 처리를 막음', 'content': 'VALUE = 2\n'})
    assert result.get('pending_repair'), result
    parent = journal.read(e.turn.continuation_key)
    return parent, journal.read(parent['repair_child'])


def test_propose_preserves_parent_and_stages_without_grant(env):
    parent, child = propose(env)
    assert parent['goal'] == env.turn.request
    assert parent['framing']['achievement_criteria'] == '결과 보고서 저장'
    assert parent['budget']['input'] + parent['budget']['output'] == 120
    assert parent['status'] == 'waiting_repair' and repair.pending() == parent
    assert child['task_id'] != child['resume_task_id']
    assert child['task_scope']['paths'] == ['backend/ibl/ibl_v2_parser.py']
    assert child['framing']['_repair_policy'] == 2
    assert red_grant.active_grant(task_id='original') is None
    assert env.path.read_text() == 'VALUE = 1\n'
    candidate = env.repo / child['worktree'] / 'backend/ibl/ibl_v2_parser.py'
    assert candidate.read_text() == 'VALUE = 2\n'
    parents.finish(env.turn, '수리 대기')
    assert journal.read(parent['task_id'])['status'] == 'waiting_repair'


def test_invalid_candidate_reports_error_without_arming_parent(env):
    result = invoke(env.handler, env.repo, 'patch_op', {'op': 'propose', 'path': str(env.path),
                    'reason': '파서 결함', 'content': 'def broken(:'})
    assert not result['success'] and '구문' in result['error']
    assert not env.turn.continuation_key
    assert env.path.read_text() == 'VALUE = 1\n'


@pytest.mark.parametrize('path', ['backend/cognition/agent_pipeline.py', 'backend/datastore/red_grant.py',
    'data/common_prompts/consciousness_prompt.md', 'data/ibl_nodes_src/self.yaml',
    'data/packages/installed/tools/system_essentials/tool_fake.py',
    'data/packages/installed/tools/web/tests/test_handler.py', 'backend/test_ibl_v2_parser.py',
    'backend/ibl/../ibl/ibl_v2_parser.py'])
def test_control_contract_and_checks_are_not_automatic_repair_targets(path):
    assert not repair.eligible(path)


@pytest.mark.parametrize('path', [
    'backend/services/restart_controller.py', 'backend/base/control_base.py',
    'backend/base/restart_process.py', 'data/packages/installed/tools/web/handler.py',
    'data/packages/installed/tools/web/parsers/news.py', 'backend/ibl/ibl_scanner.py',
])
def test_related_runtime_implementations_can_be_repaired(path):
    assert repair.eligible(path)


@pytest.mark.parametrize('path', sorted(repair.CONTROL_GOVERNANCE))
def test_runtime_ownership_does_not_include_authority_and_completion(path):
    assert not repair.eligible(path)


def test_diagnostic_request_keeps_original_bytes_and_allows_declared_sibling(env):
    sibling = env.repo / 'backend/ibl/ibl_scanner.py'
    sibling.write_text('VALUE = 1\n')
    paths = ['backend/ibl/ibl_v2_parser.py', 'backend/ibl/ibl_scanner.py']
    result = invoke(env.handler, env.repo, 'patch_op', {
        'op': 'propose', 'path': str(env.path), 'paths': paths,
        'reason': '입력 처리가 실패하여 파서와 스캐너의 원인 진단 필요'})
    assert result.get('pending_repair'), result
    child = journal.read(result['key'])
    assert child['task_scope']['paths'] == paths
    assert '"diagnose_first": true' in child['goal']
    st = env.handler._staging_mod()
    session = st.read_session(str(env.repo), child['staging_task_id'])
    assert session['files'] == {}
    candidate = env.repo / child['worktree']
    for rel in paths:
        assert (candidate / rel).read_text() == 'VALUE = 1\n'
        (candidate / rel).write_text('VALUE = 2\n')
    st._candidate.collect(str(env.repo), session)
    assert {r['rel'] for r in session['files'].values()} == set(paths)
    assert env.path.read_text() == sibling.read_text() == 'VALUE = 1\n'


@pytest.mark.parametrize('paths', [[], 'backend/ibl/ibl_v2_parser.py',
    ['backend/ibl/ibl_scanner.py'], ['backend/ibl/ibl_v2_parser.py'] * 2,
    ['backend/ibl/ibl_v2_parser.py', 'backend/services/restart_controller.py'],
    ['backend/ibl/ibl_v2_parser.py', 'backend/cognition/final_evaluator.py']])
def test_diagnostic_scope_cannot_mix_units_or_add_governance(env, paths):
    result = invoke(env.handler, env.repo, 'patch_op', {'path': str(env.path), 'paths': paths, 'reason': '실패'})
    assert not result['success'] and 'paths' in result['error']
    assert not env.turn.continuation_key


def test_child_budget_grant_and_candidate_cannot_change_parent_criteria(env, monkeypatch):
    parent, child = propose(env)
    with journal.resuming(child), actor_context(agent_id='system_ai', task_id=child['resume_task_id'], origin='user'), \
            turn_token_scope('system_ai', child['resume_task_id'], hard_token_limit=2000):
        turn = execution_turn.Binding(env.turn.runner, 'system_ai', child['resume_task_id'],
                                    request=child['goal'], context={}, conversation=env.turn.conversation)
        repair.inherit_budget(turn)
        assert read_turn_tokens() == 120
        env.controller.framing = {'achievement_criteria': '子 수리 기준'}
        ProviderMetrics().record_request(1, 30, 5)
        assert journal.read(parent['task_id'])['budget']['input'] == 130
        assert journal.read(parent['task_id'])['framing'] == parent['framing']
        grant = red_grant.issue_grant('system_ai', child['resume_task_id'])
        assert grant['task_scope'] == child['task_scope']
        with pytest.raises(PermissionError, match='다른 세션'):
            repair.check_delta({}, ['backend/ibl/ibl_v2_parser.py'])
        switched = invoke(env.handler, env.repo, 'patch_op', {'op': 'apply', 'proposal_id': 'unscoped'})
        assert not switched['success'] and '다른 제안' in switched['error']
        denied = invoke(env.handler, env.repo, 'write_file',
                        {'path': 'backend/cognition/victim.py', 'content': 'CHANGED = True'})
        assert not denied['success'] and '범위 밖' in denied['error']
        st = env.handler._staging_mod()
        sess = st.read_session(str(env.repo), child['staging_task_id'])
        (env.repo / sess['worktree'] / 'backend/cognition/victim.py').write_text('CHANGED = True')
        with pytest.raises(PermissionError, match='범위 밖'):
            st._candidate.collect(str(env.repo), sess)


def test_pending_apply_preserves_scope_without_self_cycle_and_parent_returns(env, monkeypatch):
    import api_task_repair
    import api_component_continuation
    from conversation_handoff import Handoff
    parent, child = propose(env)
    Handoff().finish(True, repair.NOTICE)
    env.store.finish(env.turn.conversation)

    def execute(row):
        bound = sessions.current()
        assert bound.session_id == env.turn.conversation.session_id
        task = row['resume_task_id']
        st = env.handler._staging_mod()
        sess = st.read_session(str(env.repo), task)
        sess['status'] = 'apply_scheduled'; st._save_session(str(env.repo), sess)
        (env.repo / 'data/system_ai_state/repair_sessions' / (task + '.apply.json')).write_text(
            json.dumps({'task_id': task, 'scheduled_at': 'now'}))
        c = NS(repair_granted=True, cancelled=lambda: False, task=task, runner=env.turn.runner,
               message=child['goal'], framing=child['framing'], delivery=NS(manifest=lambda: []),
               verifications=NS(records=[]), store=env.controller.store, owner='system_ai', episode_id=None)
        pending = journal.defer(c, '적용 예약', env.repo)
        assert pending['task_scope'] == child['task_scope']
        assert journal.read(child['task_id'])['child_task_id'] == task != child['task_id']
        journal.save({**pending, 'status': 'completed', 'response': '수리 완료'})
        return {'response': '수리 완료'}

    with journal.resuming(child):
        api_task_repair.execute(child, execute)
    monkeypatch.setattr('repair_policy.completion', lambda *a: (True, '활성·커밋 영수증'))
    called = []

    def resume(row):
        assert row['goal'] == parent['goal'] and row['repair_result']['success']
        assert row['framing'] == parent['framing']
        assert sessions.current().session_id == env.turn.conversation.session_id
        assert red_grant.active_grant(task_id=row['resume_task_id']) is None
        called.append(row['goal'])
        return {'response': '보고서 저장 완료'}

    parent = journal.read(parent['task_id'])
    api_component_continuation.consume(parent, env.repo, 'after-apply', resume)
    assert called == [parent['goal']]
    assert journal.read(parent['task_id'])['attempt'] == 0
    assert journal.read(parent['task_id'])['status'] == 'completed'


def test_child_waits_for_parent_segment_to_finish(env):
    import api_task_repair
    parent, child = propose(env)
    assert not api_task_repair.ready(child)
    with pytest.raises(RuntimeError, match='아직 끝나지'):
        api_task_repair.execute(child, lambda row: pytest.fail('부모와 동시 실행'))
    env.store.finish(env.turn.conversation)
    assert api_task_repair.ready(child)


def test_failed_child_returns_evidence_and_repeated_candidate_is_rejected(env):
    parent, child = propose(env)
    journal.save({**child, 'status': 'blocked', 'reason': '범위 밖 원인'})
    resumed = repair.advance_parent(parent, env.repo, lambda *a: (False, '반영되지 않음'))
    assert resumed['status'] == 'waiting'
    assert resumed['repair_result']['failure'] == '범위 밖 원인'
    result = invoke(env.handler, env.repo, 'patch_op', {'op': 'propose', 'path': str(env.path),
                    'reason': '반복', 'content': 'VALUE = 2\n'})
    assert not result['success'] and '같은 수정' in result['error']


@pytest.mark.parametrize('reason', ['cancel', 'conversation_cancel', 'new_request', 'budget'])
def test_child_is_stopped_when_parent_no_longer_authorizes_it(env, monkeypatch, reason):
    parent, child = propose(env)
    if reason == 'cancel':
        journal.cancel_pending('', 'system_ai', env.repo)
    elif reason == 'conversation_cancel':
        env.store.finish(env.turn.conversation, 'cancelled')
    elif reason == 'new_request':
        env.store.finish(env.turn.conversation)
        env.store.begin(env.turn.conversation.session_id)
    else:
        parent['budget']['hard_token_limit'] = 120
        journal.save(parent)
    with pytest.raises(PermissionError):
        repair.parent_of(child)


@pytest.mark.parametrize('stage', ['initial', 'followup', 'adoption'])
def test_pipeline_yields_pending_instead_of_claiming_original_work_complete(env, monkeypatch, stage):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from test_reflex_execution import AI
    from thread_context import get_goal_eval_outcome

    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin):
        pass

    if stage == 'initial':
        propose(env)
    else:
        def submit_repair(*args, **kwargs):
            with monkeypatch.context() as patch:
                patch.setattr('supervision_bus.current', lambda *a, **kw: env.controller)
                propose(env)
            yield from ()
            return '원래 업무까지 완료했습니다'
        target = 'task_continuation.continue_task' if stage == 'followup' else 'capability_guard.adopt_response'
        monkeypatch.setattr(target, submit_repair)
    r = Runner(); r.config = {'_is_system_ai': True}
    r.ai = AI([[{'type': 'final', 'content': '원래 업무까지 완료했습니다'}]])
    r._associate = lambda *a, **kw: None
    r._decide_request_type = lambda *a, **kw: ('EXECUTE', None)
    r._load_role = lambda: 'role'
    r._build_system_ai_prompt_split = lambda *a, **kw: ('System structure + IBL + rules', '')
    r._after_response_async = lambda *a, **kw: None
    monkeypatch.setattr('supervision_bus.current', lambda *a, **kw: None)
    monkeypatch.setattr('unified_distill.capture_model', lambda *a: None)
    with r.turn_ai_scope():
        events = list(r._cognitive_stream_body(env.turn.request, []))
    assert [e['content'] for e in events if e['type'] == 'final'] == [repair.NOTICE], events
    assert get_goal_eval_outcome()['status'] == 'PENDING_REPAIR'
    assert len(r.ai.calls) == 1


def test_supervisor_revision_suspends_before_another_evaluation(supervisor, monkeypatch):
    rounds, requested = [], []

    def evaluate(controller, *args, **kwargs):
        rounds.append(1)
        return verdict(controller, 'REWORK', instruction='도구 결함 확인')

    def revise(prompt, **kwargs):
        requested.append(True)
        yield {'type': 'final', 'content': '수리 요청을 접수했습니다'}

    supervisor.runner.ai.process_message_stream = revise
    monkeypatch.setattr('final_evaluator.invoke', evaluate)
    monkeypatch.setattr(repair, 'pending_response', lambda: repair.NOTICE if requested else None)
    events = finish(supervisor, '첫 방법 실패')
    assert rounds == [1]
    assert events[-1]['content'] == repair.NOTICE


@pytest.mark.system
@pytest.mark.parametrize('diagnostic', [False, True])
def test_scoped_candidate_real_check_and_separate_process_apply(env, monkeypatch, diagnostic):
    """별도 적용 프로세스가 허용 델타만 각인한다. 실제 백엔드 재기동은 기존 프로세스 배터리 담당."""
    import repair_policy
    from repair_policy import direct_framing
    from conversation_handoff import Handoff
    paths = ['backend/ibl/ibl_v2_parser.py']
    if diagnostic:
        paths.append('backend/ibl/ibl_scanner.py')
        (env.repo / paths[1]).write_text('VALUE = 1\n')
        with (env.repo / 'backend/test_parser_behavior.py').open('a') as f:
            f.write('    assert runpy.run_path("backend/ibl/ibl_scanner.py")["VALUE"] == 2\n')
        subprocess.run(['git', 'add', '.'], cwd=env.repo, check=True)
        subprocess.run(['git', 'commit', '-qm', 'related implementation fixture'], cwd=env.repo, check=True)
        result = invoke(env.handler, env.repo, 'patch_op', {
            'path': str(env.path), 'paths': paths, 'reason': '입력 처리가 실패하여 관련 구현 진단 필요'})
        assert result.get('pending_repair'), result
        parent = journal.read(env.turn.continuation_key)
        child = journal.read(result['key'])
    else:
        parent, child = propose(env)
    st = env.handler._staging_mod()
    monkeypatch.setenv('INDIEBIZ_REPAIR_NO_SPAWN', '1')
    controller = NS(repair_granted=True, cancelled=lambda: False, message=child['goal'],
                    framing=direct_framing(child['goal']), _final_criteria_contract=None,
                    store=NS(tool_index=lambda **kw: [], evidence=lambda value: {'id': 'check', 'chars': 1}),
                    log=lambda *a, **kw: None)
    controller.prepare_repair = lambda repo, sess, verify, candidate: repair_policy.prepare(controller, repo, sess, verify, candidate)
    monkeypatch.setattr('supervision_bus.current', lambda *a, **kw: controller)
    command = shlex.quote(sys.executable) + ' -m pytest backend/test_parser_behavior.py'
    session = st.read_session(str(env.repo), child['staging_task_id'])
    candidate_path = env.repo / session['worktree'] / 'backend/ibl/ibl_v2_parser.py'
    candidate_path.write_text('VALUE = 1\n')
    from repair_check_runner import execute
    failed = execute(str(env.repo), session, st._candidate, command, controller)
    assert failed['status'] == 'failed', failed
    st._save_session(str(env.repo), session)
    candidate_path.write_text('VALUE = 2\n')
    if diagnostic:
        (env.repo / session['worktree'] / paths[1]).write_text('VALUE = 2\n')
    with journal.resuming(child), actor_context(agent_id='system_ai', task_id=child['resume_task_id'], origin='user'):
        red_grant.issue_grant('system_ai', child['resume_task_id'])
        result = st.op_apply({'_repo_root': str(env.repo), '_grant_key': child['resume_task_id'],
                             'verification_plan': [{'criterion_id': 'C1', 'command': command}]})
    assert result.get('scheduled'), result
    assert env.path.read_text() == 'VALUE = 1\n'
    Handoff().finish(True, repair.NOTICE)
    env.store.finish(env.turn.conversation)
    # 새 프로세스는 부모·사본 원장의 경계와 취소를 다시 검사한다.
    code = ('import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import boot_paths; '
            'import runtime_utils; runtime_utils.get_base_path=lambda:Path(sys.argv[2]); '
            'from test_repair_staging import _load_handler; h=_load_handler(); h._REPO_ROOT=Path(sys.argv[2]); '
            'print(json.dumps(h._staging_mod().perform_scheduled_apply(sys.argv[2],sys.argv[3])))')
    applied = subprocess.run([sys.executable, '-c', code, str(Path(__file__).parent), str(env.repo), child['resume_task_id']],
                             capture_output=True, text=True, timeout=60)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    result = json.loads(applied.stdout.splitlines()[-1])
    assert result.get('applied'), result
    assert env.path.read_text() == 'VALUE = 2\n'
    session = st.read_session(str(env.repo), child['staging_task_id'])
    committed = st._candidate.commit(str(env.repo), session, env.handler._load_sibling('body_ops'))
    assert committed['success'], committed
    session['commit'] = committed; st._save_session(str(env.repo), session)
    assert set(session['sealed']) == set(paths)
    # 수정 전 실패·후 통과를 실제 검사기가 남긴 영수증으로 완료 판정한다.
    monkeypatch.setattr('red_apply._load_handler', lambda *a: env.handler)
    passed, reason = repair_policy.completion(session, child, env.repo)
    assert passed, reason
    journal.save({**child, 'status': 'completed', 'response': '구현 검사·반영 완료'})
    resumed = repair.advance_parent(journal.read(parent['task_id']), env.repo, repair_policy.completion)
    assert resumed['goal'] == env.turn.request and resumed['repair_result']['success']
    assert resumed['framing'] == parent['framing']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
