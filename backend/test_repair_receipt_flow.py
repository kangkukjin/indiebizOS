"""작은 수리는 실검사→고정 적용으로 닫고, 실패는 원인을 그대로 돌려준다."""
import json
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from test_repair_workspace_completion import setup  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
import repair_policy as policy
from repair_check_runner import execute
from repair_test_results import invocation, summary


@pytest.mark.parametrize('case,item,expected', [
    ('complete', 'activation', 'achieved'),
    ('missing_session', 'applied', 'unverified'),
    ('missing_continuation', 'completion_notice', 'unverified'),
    ('wrong_commit', 'commit', 'failed'),
    ('unconfirmed_notice', 'completion_notice', 'unverified'),
    ('missing_function', 'live_function', 'unverified'),
    ('failed_function', 'live_function', 'failed'),
    ('wrong_identity', 'activation', 'unverified'),
])
def test_p2_observes_exact_receipts_from_another_project(tmp_path, monkeypatch, case, item, expected):
    """P2의 실제 IBL·파일 입구를 실행한다. 다른 프로젝트의 상대경로·미관측 오판을 막는다."""
    from ibl_v2_adapters import Adapter, load_registry
    from ibl_v2_entry import handle_request

    root = tmp_path / 'canonical'
    project = tmp_path / 'study'
    project.mkdir()
    key = 'receipt-probe'
    session = {'key': key, 'status': 'applied', 'verified': True,
               'commit': {'success': True, 'commit': 'abcdef12'}}
    continuation = {'task_id': key, 'status': 'completed', 'pending_delivery': False,
                    'result': {'outcome': 'healthy', 'report': {'outcome': 'healthy', 'generation': 'g1'}},
                    'evaluation': {'goal_status': 'ACHIEVED', 'method': 'repair_receipts'}}
    if case == 'unconfirmed_notice':
        continuation['evaluation'] = {}
    if case == 'wrong_identity':
        continuation['task_id'] = 'another-task'
    for folder, value in [('repair_sessions', session), ('repair_continuations', continuation)]:
        path = root / 'data/system_ai_state' / folder / (key + '.json')
        path.parent.mkdir(parents=True)
        if (case, folder) not in {('missing_session', 'repair_sessions'),
                                  ('missing_continuation', 'repair_continuations')}:
            path.write_text(json.dumps(value))

    def script(runtime, args, target_node=None):
        op = args['args']['op']
        if op == 'commit':
            return {'observed': True, 'matches': case != 'wrong_commit'}
        if case == 'missing_function':
            return {'observed': False, 'error': 'probe unavailable'}
        if op == 'pytest':
            return {'observed': True, 'exit_code': 1 if case == 'failed_function' else 0}
        return {'observed': True, 'requirement_met': True}

    registry = load_registry(str(project))
    for name, run in [('self:script', script),
                      ('self:patch', lambda *a, **kw: {'items': [{'key': key}]})]:
        registry[name] = Adapter(registry[name].contract, run)
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: registry)
    source = Path(__file__).resolve().parents[1] / 'docs/experiments/long_sentence_imagination/round_97/p2_v1.ibl'
    output = tmp_path / 'report.json'
    request = {'edition': 2, 'origin': 'training', 'code': source.read_text(), 'inputs': {
        '러너본문': '# fixture only', '정본': str(root), 'key': key,
        '경로': str(root / 'subject.py'), '검증자': 'fixture', '씨앗': 'fixture', '보고경로': str(output)}}
    result = handle_request(request, project_path=str(project))
    assert result['success'], result.get('error')
    rows = json.loads(output.read_text())
    verdicts = {r['item']: r['verdict'] for r in rows}
    assert verdicts[item] == expected, verdicts
    assert result['value']['reread'] == 6
    if case == 'complete':
        assert set(verdicts.values()) == {'achieved'}
    if case.startswith('missing_') and case != 'missing_function':
        assert any(r['evidence'].get('read_error') for r in rows)


@pytest.fixture
def repair(setup, supervisor, monkeypatch):
    root, wt, st, session = setup
    session['repair_policy'] = 2
    supervisor.configure(policy.direct_framing(supervisor.message), repair=True)
    supervisor.task = session['key']
    monkeypatch.setattr('red_report.current_owner', lambda: 'owner')
    monkeypatch.setattr('supervision_bus.current', lambda: supervisor)
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: root)
    # This fixture applies to an isolated file repository, not the running body.
    import red_apply
    post_verify = red_apply._run_post_verify
    monkeypatch.setattr(red_apply, '_run_post_verify',
                        lambda *a, **kw: post_verify(*a, **kw, live_read=False))
    from test_repair_staging import _load_handler
    handler = _load_handler()
    handler._REPO_ROOT = root
    handler._staging_mod = lambda: st
    monkeypatch.setattr('red_apply._load_handler', lambda job: handler)
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
    cmd = command(wt)
    before = execute(str(root), session, st._candidate, cmd, controller)
    assert before['status'] == 'failed'
    (wt / 'a.txt').write_text('fixed')
    # This runs an actual isolated pytest subprocess and consumes its XML report.
    first = execute(str(root), session, st._candidate, cmd, controller)
    assert first['test_report']['passed'], first
    st._save_session(str(root), session)
    import repair_check_runner
    monkeypatch.setattr(repair_check_runner, 'execute', lambda *a, **kw: pytest.fail('duplicate test'))
    result = st.op_apply({'_repo_root': str(root), '_grant_key': session['key']})
    assert result.get('complete'), result
    assert (root / 'a.txt').read_text() == 'fixed'
    saved = st.read_session(str(root), session['key'])
    assert policy.completion(saved, {}, root)[0]
    assert not policy.receipt_completion(controller)  # 실제 업무 완료는 기존 최종평가에서 판단.
    (root / 'a.txt').write_text('later mutation')
    assert not policy.completion(saved, {}, root)[0]


def test_failed_command_is_reported_then_executor_can_apply_without_replaying_it(repair, monkeypatch):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    cmd = command(wt, 'assert False, "actual cause"')
    result = prepare(repair, cmd)
    assert result['stage'] == 'test'
    assert 'actual cause' in result['checks'][0]['output']
    assert (root / 'a.txt').read_text() == 'before'
    st._save_session(str(root), session)
    monkeypatch.setattr('repair_check_runner.execute', lambda *a, **kw: pytest.fail('old failed plan replayed'))
    result = st.op_apply({'_repo_root': str(root), '_grant_key': session['key']})
    assert result['complete'], result
    assert (root / 'a.txt').read_text() == 'fixed'
    saved = st.read_session(str(root), session['key'])
    assert saved['execution_checks'][0]['status'] == 'failed'


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


def test_requested_command_can_generate_sources_before_publication(repair):
    root, wt, st, session, controller = repair
    cmd = command(wt, '__import__("pathlib").Path("a.txt").write_text("mutated")')
    result = prepare(repair, cmd)
    assert result['success'], result
    assert (wt / 'a.txt').read_text() == 'mutated'
    assert session['sealed']['a.txt']['after'] == st._candidate.fingerprint(wt / 'a.txt')


def test_optional_skipped_case_does_not_negate_executed_test(repair):
    from repair_check_runner import execute
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    (wt / 'test_skip.py').write_text(
        'import pytest\nfrom pathlib import Path\n'
        'def test_change(): assert Path("a.txt").read_text() == "fixed"\n'
        '@pytest.mark.skip(reason="optional integration unavailable")\n'
        'def test_optional(): pass\n')
    row = execute(str(root), session, st._candidate,
                  shlex.quote(sys.executable) + ' -m pytest test_skip.py', controller)
    assert row['status'] == 'passed'
    assert row['test_report']['tests'] == 2 and row['test_report']['skipped'] == 1
    assert row['test_report']['scope']['skipped'] == ['test_skip.py::test_optional']


def test_verify_does_not_sync_live_after_receipt(repair):
    root, wt, st, session, controller = repair
    (root / 'b.txt').write_text('new dependency')
    ok, checks = st.verify(str(root), session)
    assert ok, checks
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


def test_direct_repair_does_not_call_planning_model(monkeypatch):
    from cognitive_consciousness import CognitiveConsciousnessMixin
    import thread_context
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'user')
    monkeypatch.setattr('cognitive_consciousness.CognitiveConsciousnessMixin._run_consciousness', lambda *a: pytest.fail('planning model'))
    result = CognitiveConsciousnessMixin()._run_consciousness_or_reuse('#repair 영어 상태 표시 수정', [], repair=True)
    assert result['_repair_policy'] == 2
    assert result['criteria'][0]['text'] == '#repair 영어 상태 표시 수정'


def test_deferred_success_closes_without_new_executor(consumer, tmp_path, monkeypatch):
    from test_repair_continuation import record, receipt
    import repair_continuation as journal
    module, deliveries, settled = consumer
    row = record(tmp_path, repair_policy=2)
    receipt(tmp_path)
    monkeypatch.setattr(module, '_commit_ready', lambda *a: None)
    monkeypatch.setattr(policy, 'completion', lambda *a: (True, 'verified'))
    from restart_protocol import atomic_json
    atomic_json(tmp_path / 'data/system_ai_state/repair_sessions/task-repair.json', {'commit': {'commit': 'a' * 40}, 'task_scope': {'parent': 'parent'}})
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


def test_code_and_artifact_share_verified_apply_but_output_is_not_in_git(repair):
    import subprocess
    root, wt, st, session, controller = repair
    for directory in (root, wt):
        with (directory / '.gitignore').open('a') as f:
            f.write('outputs/\n')
    st._candidate.refresh(str(root), session)
    cmd = command(wt, 'assert __import__("pathlib").Path("outputs/helper").read_bytes() == b"\\0binary"')
    before = execute(str(root), session, st._candidate, cmd, controller)
    assert before['status'] == 'failed'
    st._save_session(str(root), session)
    (wt / 'a.txt').write_text('fixed')
    (wt / 'outputs').mkdir()
    (wt / 'outputs/helper').write_bytes(b'\0binary')
    result = st.op_apply({'_repo_root': str(root), '_grant_key': session['key'],
                         'artifact_paths': ['outputs/helper'],
                         'verification_plan': [{'criterion_id': 'C1', 'method': 'test', 'command': cmd}]})
    assert result.get('complete'), result
    saved = st.read_session(str(root), session['key'])
    assert policy.completion(saved, {}, root)[0]
    assert (root / 'outputs/helper').read_bytes() == b'\0binary'
    assert subprocess.check_output(['git', 'ls-tree', '-r', 'HEAD', '--', 'outputs'], cwd=root) == b''
    (root / 'outputs/helper').unlink()
    assert not policy.completion(saved, {}, root)[0]
