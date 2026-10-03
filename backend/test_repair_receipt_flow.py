"""작은 수리는 실검사→고정 적용으로 닫고, 실패는 원인을 그대로 돌려준다."""
import json
import shlex
import sys
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from test_repair_workspace_completion import setup  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
import repair_policy as policy
from repair_check_runner import execute
from repair_test_results import invocation, summary


@pytest.fixture
def repair(setup, supervisor, monkeypatch):
    root, wt, st, session = setup
    session['repair_policy'] = 2
    supervisor.configure(policy.direct_framing(supervisor.message), repair=True)
    supervisor.task = session['key']
    monkeypatch.setattr('red_report.current_owner', lambda: 'owner')
    monkeypatch.setattr('supervision_bus.current', lambda: supervisor)
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: root)
    monkeypatch.setattr('red_apply._load_handler', lambda job: SimpleNamespace(_staging_mod=lambda: st))
    monkeypatch.setattr('final_evaluator.invoke', lambda *a, **kw: pytest.fail('unexpected AI review'))
    st._save_session(str(root), session)
    return root, wt, st, session, supervisor


def prepare(repair, command):
    root, wt, st, session, controller = repair
    session['verification_plan'] = [{'criterion_id': 'C1', 'method': 'test', 'command': command}]
    return policy.prepare(controller, str(root), session, st.verify, st._candidate)


def command(wt, source='assert __import__("pathlib").Path("a.txt").read_text() == "fixed"'):
    (wt / 'test_change.py').write_text('def test_changed_behavior():\n    ' + source + '\n')
    return shlex.quote(sys.executable) + ' -m pytest test_change.py'


def test_real_test_apply_and_completion_without_ai(repair, monkeypatch):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    cmd = command(wt)
    # This runs an actual isolated pytest subprocess and consumes its XML report.
    first = execute(str(root), session, st._candidate, cmd, controller)
    assert first['test_report']['passed'], first
    st._save_session(str(root), session)
    import repair_check_runner
    monkeypatch.setattr(repair_check_runner, 'execute', lambda *a, **kw: pytest.fail('duplicate test'))
    result = st.op_apply({'_repo_root': str(root), '_grant_key': session['key'],
                         'verification_plan': [{'criterion_id': 'C1', 'method': 'test', 'command': cmd}]})
    assert result.get('complete'), result
    assert (root / 'a.txt').read_text() == 'fixed'
    saved = st.read_session(str(root), session['key'])
    assert policy.completion(saved, {}, root)[0]
    events = list(controller.finalize('검사 후 반영했습니다', [], lambda ev: None))
    assert '미완료' not in events[-1]['content']
    from thread_context import get_goal_eval_outcome
    assert get_goal_eval_outcome()['method'] == 'repair_receipts'
    (root / 'a.txt').write_text('later mutation')
    assert not policy.completion(saved, {}, root)[0]


def test_failed_test_preserved_and_identical_prepare_not_repeated(repair, monkeypatch):
    root, wt, st, session, controller = repair
    cmd = command(wt, 'assert False, "actual cause"')
    result = prepare(repair, cmd)
    assert result['stage'] == 'test'
    assert 'actual cause' in result['checks'][0]['output']
    import repair_check_runner
    monkeypatch.setattr(repair_check_runner, 'execute', lambda *a, **kw: pytest.fail('same failure repeated'))
    repeated = prepare(repair, cmd)
    assert repeated['reused'] and repeated['checks'] == result['checks']
    assert (root / 'a.txt').read_text() == 'before'


def test_report_rejects_zero_skip_and_shell_success(tmp_path):
    assert invocation('echo passed', tmp_path) is None
    assert invocation('python -m pytest test_a.py > /dev/null', tmp_path) is None
    spec = invocation('python -m pytest test_a.py', tmp_path)
    from pathlib import Path
    for xml in ('<testsuite/>', '<testsuite><testcase name="x"><skipped/></testcase></testsuite>'):
        Path(spec['report']).write_text(xml)
        assert not summary(spec, '', 0)['passed']
    node = invocation('node --test a.test.mjs', tmp_path)
    output = '# tests 1\n# pass 1\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n'
    assert summary(node, output, 0)['passed']
    assert not summary(node, 'passed', 0)['passed']


def test_test_that_mutates_candidate_cannot_be_reused_as_pass(repair):
    root, wt, st, session, controller = repair
    cmd = command(wt, '__import__("pathlib").Path("a.txt").write_text("mutated")')
    result = prepare(repair, cmd)
    assert not result['success']
    assert result['checks'][0]['status'] == 'unverified'
    assert not session.get('readiness')


def test_verify_does_not_sync_live_after_receipt(repair):
    root, wt, st, session, controller = repair
    (root / 'b.txt').write_text('new dependency')
    ok, checks = st.verify(str(root), session)
    assert not ok and checks[0]['gate'] == 'live_sync'
    assert (wt / 'b.txt').read_text() == 'before'


def test_failure_details_survive_adapter():
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    payload = policy.failure('semantic', 'missing observation', missing_criteria=['C1'],
                             decision={'status': 'UNKNOWN', 'reason': 'browser output missing'})
    with pytest.raises(Fault) as exc:
        decode_envelope(payload, {})
    assert exc.value.details['decision'] == payload['decision']
    assert exc.value.details['missing_criteria'] == ['C1']
    assert exc.value.details['stage'] == 'semantic'


def test_semantic_approval_without_coverage_is_not_enough(repair, monkeypatch):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    session['verification_plan'] = [{'criterion_id': 'C1', 'method': 'semantic'}]
    monkeypatch.setattr(policy, 'semantic_review', lambda *a: {'status': 'APPROVED'})
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert not result['success'] and result['stage'] == 'semantic'


def test_direct_repair_does_not_call_planning_model(monkeypatch):
    from cognitive_consciousness import CognitiveConsciousnessMixin
    import thread_context
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'user')
    monkeypatch.setattr('pursuit_bind.run_consciousness', lambda *a: pytest.fail('planning model'))
    result = CognitiveConsciousnessMixin()._run_consciousness_or_reuse('#repair 영어 상태 표시 수정', [], repair=True)
    assert result['_repair_policy'] == 2
    assert result['criteria'][0]['text'] == '#repair 영어 상태 표시 수정'


def test_semantic_only_checks_selected_condition_and_retrieves_original(repair, monkeypatch):
    root, wt, st, session, controller = repair
    controller.store.put_response('수정 결과')
    record = {'id': 'observation', 'output': 'x' * 35000 + 'tail proof'}
    ref = controller.store.evidence(record)
    record['evidence_ref'] = ref
    seen = []
    def invoke(c, **kw):
        assert kw['phase'] == 'semantic'
        packet = c._evaluation_packet
        assert [r['id'] for r in packet['context']['criteria_contract']['criteria']] == ['C2']
        seen.append(packet)
        if len(seen) == 1:
            return json.dumps({'status': 'UNKNOWN', 'recoverable': True, 'reason': ref['id']})
        assert 'tail proof' in packet['context']['recovered_evidence'][0]['text']
        return json.dumps({'status': 'APPROVED', 'workspace_coverage': [
            {'criterion_id': 'C2', 'status': 'passed', 'evidence_ids': ['observation']}]})
    monkeypatch.setattr('final_evaluator.invoke', invoke)
    contract = {'user_goal': controller.message, 'criteria': [{'id': 'C1', 'text': 'machine'}, {'id': 'C2', 'text': 'meaning'}]}
    result = policy.semantic_review(controller, contract, [contract['criteria'][1]], session, [record])
    assert result['status'] == 'APPROVED', result
    assert len(seen) == 2


def test_deferred_success_closes_without_new_executor(consumer, tmp_path, monkeypatch):
    from test_repair_continuation import record, receipt
    import repair_continuation as journal
    module, deliveries, settled = consumer
    row = record(tmp_path, repair_policy=2)
    receipt(tmp_path)
    monkeypatch.setattr(module, '_commit_ready', lambda *a: None)
    monkeypatch.setattr(policy, 'completion', lambda *a: (True, 'verified'))
    from restart_protocol import atomic_json
    atomic_json(tmp_path / 'data/system_ai_state/repair_sessions/task-repair.json', {'commit': {'commit': 'a' * 40}})
    module.process_pending(tmp_path, 'new-generation', lambda *a: pytest.fail('unnecessary executor'))
    assert settled == ['completed']
    assert journal.read(row['task_id'], tmp_path)['evaluation']['method'] == 'repair_receipts'
    module.process_pending(tmp_path, 'new-generation', lambda *a: pytest.fail('duplicate executor'))
    assert len(deliveries) == 1


from test_repair_continuation import consumer  # noqa: E402, F401


def test_policy_pinned_when_session_created(repair):
    root, wt, st, session, controller = repair
    new = st.ensure_session(str(root), 'new-policy-task')
    assert new['repair_policy'] == 2
    controller.framing.pop('_repair_policy')
    assert st.ensure_session(str(root), 'new-policy-task')['repair_policy'] == 2


def test_v2_build_gate_checks_without_generating(repair, monkeypatch):
    root, wt, st, session, controller = repair
    from subprocess import CompletedProcess
    build = wt / 'scripts/build_ibl_nodes.py'
    build.parent.mkdir()
    build.write_text('# fixture')
    st._candidate.collect(str(root), session)
    monkeypatch.setattr(st, '_live_build_inputs_touched', lambda *a: True)
    commands = []
    def run(argv, **kwargs):
        commands.append(argv)
        return CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(st, '_sandbox_check', run)
    assert st.verify(str(root), session)[0]
    assert next(c for c in commands if 'scripts/build_ibl_nodes.py' in c)[-1] == '--check'


def test_same_semantic_service_failure_has_bounded_retries(repair, monkeypatch):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    session['verification_plan'] = [{'criterion_id': 'C1', 'method': 'semantic'}]
    calls = []
    def unavailable(*args):
        calls.append(1)
        return {'status': 'UNKNOWN', 'reason': 'service unavailable', 'retryable': True}
    monkeypatch.setattr(policy, 'semantic_review', unavailable)
    for _ in range(4):
        result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
        assert not result['success'] and result['stage'] == 'semantic'
    assert len(calls) == 2
    assert result['reused']
    st._save_session(str(root), session)
    events = list(controller.finalize('진행 상태', [], lambda ev: None))
    assert 'service unavailable' in events[-1]['content']
    assert '정본 반영·활성 확인·커밋이 완료되지' not in events[-1]['content']


def test_new_policy_does_not_reinterpret_legacy_session(repair, monkeypatch):
    root, wt, st, session, controller = repair
    session['repair_policy'] = 1
    (wt / 'a.txt').write_text('fixed')
    monkeypatch.setattr(policy, 'prepare', lambda *a: pytest.fail('legacy policy changed'))
    monkeypatch.setattr('final_evaluator.invoke', lambda *a, **kw: json.dumps({'status': 'UNKNOWN', 'reason': 'legacy review'}))
    result = controller.prepare_repair(str(root), session, st.verify, st._candidate)
    assert not result['success']
    assert controller._repair_completion_policy == 1


def test_status_details_survive_items_projection(repair):
    root, wt, st, session, controller = repair
    session['preparation_result'] = {'result': policy.failure('test', 'specific failure', missing_criteria=['C1'])}
    st._save_session(str(root), session)
    raw = st.op_status({'_repo_root': str(root), '_grant_key': session['key']})
    from ibl_v2_adapters import decode_envelope
    rows, _ = decode_envelope(raw, {'value_path': '/items'})
    current = next(row for row in rows if row['current'])
    assert current['repair_policy'] == 2
    assert current['last_preparation']['error'] == 'specific failure'
    assert current['last_preparation']['missing_criteria'] == ['C1']


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
