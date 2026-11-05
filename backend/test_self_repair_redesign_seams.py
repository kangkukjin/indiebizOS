"""자기수리의 검사 변경·재현 근거·전달 분리·예약 뒤 턴 닫기."""
import json
import shlex
import sys

import pytest
import boot_paths  # noqa: F401
from test_repair_receipt_flow import repair  # noqa: F401
from test_repair_workspace_completion import setup  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
import repair_policy as policy
from supervisor_handoff import criteria_contract


def _plan(session, command):
    session['verification_plan'] = [{'criterion_id': 'C1', 'method': 'test', 'command': command}]


def _test_file(wt, body):
    (wt / 'test_change.py').write_text(body)
    return shlex.quote(sys.executable) + ' -m pytest test_change.py'


def test_test_refactor_does_not_require_separate_semantic_approval(repair):
    root, wt, st, session, controller = repair
    (root / 'test_change.py').write_text('def test_a():\n    assert 1 == 1\n\ndef test_b():\n    assert 2 == 2\n')
    import subprocess
    subprocess.run(['git', 'add', 'test_change.py'], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-qm', 'tests'], cwd=root, check=True)
    st._candidate.refresh(str(root), session)
    (wt / 'a.txt').write_text('fixed')
    command = _test_file(wt, 'def test_a():\n    assert 1 == 1\n')   # test_b 삭제 = 약화
    controller._final_criteria_contract = criteria_contract('고쳐줘', {'criteria': [{'text': 'a 는 fixed'}]})
    _plan(session, command)
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert result['success'], result
    assert 'test_change.py' in session['sealed']


def test_before_failure_and_after_pass_are_preserved_without_machine_reproduction_claim(repair):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    command = _test_file(wt, 'def test_fix():\n    assert __import__("pathlib").Path("a.txt").read_text() == "fixed"\n')
    session['execution_checks'] = [
        {'id': 'before', 'command': command, 'status': 'failed', 'candidate_hash': 'h-old', 'before_hash': 'h-old'},
    ]
    controller._final_criteria_contract = criteria_contract('고쳐줘', {'criteria': [{'text': 'a 는 fixed'}]})
    _plan(session, command)
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert result['success'], result
    observations = session['execution_checks']
    assert observations[0]['id'] == 'before' and observations[0]['status'] == 'failed'
    assert observations[-1]['command'] == command and observations[-1]['status'] == 'passed'
    # A passing command is not automatically a proof of the original symptom.
    assert 'regression_evidence' not in session['readiness']


def test_symptom_recheck_is_unverified_without_reproduction_or_active_check(repair):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    command = _test_file(wt, 'def test_fix():\n    assert True\n')
    controller._final_criteria_contract = criteria_contract('고쳐줘', {'criteria': [{'text': 'a 는 fixed'}]})
    _plan(session, command)
    assert policy.prepare(controller, str(root), session, st.verify, st._candidate)['success']
    assert 'regression_evidence' not in session['readiness']
    verdict, note = policy.symptom_recheck(session, {}, root)
    assert verdict == 'unverified' and '재현' in note
    session.setdefault('activation_checks', {})['active_verify_cmd'] = {'state': 'passed'}
    assert policy.symptom_recheck(session, {}, root)[0] == 'verified'


def test_active_generation_bytes_compares_sealed_delta_with_active_generation(setup, tmp_path):
    root, wt, st, sess = setup
    from restart_protocol import atomic_json
    (wt / 'a.txt').write_text('approved')
    st._candidate.seal(str(root), sess, [], {'status': 'APPROVED'}, {'criteria': []})
    assert st._candidate.active_generation_bytes(root, sess)[0] == 'unknown'
    gen = tmp_path / 'gen'
    gen.mkdir()
    import hashlib
    sha = hashlib.sha256(b'approved').hexdigest()
    atomic_json(gen / 'manifest.json', {'generation': 'g', 'files': {'a.txt': sha}})
    atomic_json(root / 'data/restart_control/state.json', {'generation_dir': str(gen)})
    assert st._candidate.active_generation_bytes(root, sess)[0] == 'matched'
    atomic_json(gen / 'manifest.json', {'generation': 'g', 'files': {'a.txt': 'deadbeef'}})
    verdict, note = st._candidate.active_generation_bytes(root, sess)
    assert verdict == 'mismatch' and 'a.txt' in note


def test_tool_calls_after_scheduled_apply_are_not_executed(supervisor):
    supervisor.apply_scheduled = {'key': 'task', 'at': 1}
    out = json.loads(supervisor.run_tool('inspect', {'x': 1}, lambda: pytest.fail('executed after schedule')))
    assert out['not_executed'] and '예약' in out['supervisor_instruction']
    assert supervisor.calls == []


def test_completion_delivery_failure_is_retried_without_rerunning_completion(tmp_path, monkeypatch):
    import api_repair_continuation as consumer
    import repair_continuation as journal
    import repair_root
    from restart_protocol import atomic_json
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    task = 'task-deliver'
    job = tmp_path / 'data/system_ai_state/repair_sessions' / (task + '.apply.json')
    atomic_json(job, {'key': task, 'task_id': task, 'repo': str(tmp_path), 'scheduled_at': 'now', 'restart_request_id': 'red-x'})
    atomic_json(job.with_name(task + '.json'), {'status': 'applied', 'repair_policy': 2, 'task_scope': {'parent': 'parent'}})
    row = journal.save({'task_id': task, 'root_task_id': task, 'attempt': 1, 'failures': [], 'job_path': str(job),
                        'scheduled_at': 'now', 'status': 'waiting_apply', 'authorized_origin': 'user', 'goal': 'g',
                        'project_id': 'p', 'agent_id': 'a', 'system_ai': True, 'repair_policy': 2,
                        'phase': 'verify_remaining', 'response': '수정했습니다'}, tmp_path)
    atomic_json(tmp_path / 'data/restart_control/results/red-x.json', {'outcome': 'restarted'})
    atomic_json(tmp_path / 'data/system_ai_state/red_backups' / task / 'result.json', {'outcome': 'healthy'})
    monkeypatch.setattr(consumer, '_settle', lambda *a: None)
    monkeypatch.setattr(consumer, 'active_check', lambda row, base=None: journal.save({**row, 'phase': 'verify_remaining'}, base))
    monkeypatch.setattr('repair_policy.completion', lambda session, row, base: (True, '영수증 완료'))
    monkeypatch.setattr('repair_policy.symptom_recheck', lambda session, row, base: ('verified', '활성 확인'))
    monkeypatch.setattr(consumer, '_record_receipt_verdict', lambda *a, **k: None)
    attempts = []
    def deliver(row):
        attempts.append(row['reason'])
        if len(attempts) == 1:
            raise RuntimeError('채널 끊김')
    monkeypatch.setattr(consumer, '_deliver_blocked', deliver)
    consumer.process_pending(tmp_path, 'g2', lambda row: pytest.fail('완료 영수증이 있는데 실행자를 열었다'))
    view = repair_root.projection(tmp_path, task)
    assert view['complete'] and view['delivery_status'] == 'failed'
    assert journal.read(task, tmp_path)['delivery_pending']['completion'] is True
    consumer.process_pending(tmp_path, 'g2', lambda row: pytest.fail('전달 재시도가 완료를 반복했다'))
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert repair_root.projection(tmp_path, task)['delivery_status'] == 'delivered'
    assert 'delivery_pending' not in journal.read(task, tmp_path)


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
