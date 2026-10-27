"""기준의 의미 검토 소유권과 검사 중 정본 충돌의 조기 중단."""
import pytest
import boot_paths  # noqa: F401
from test_repair_receipt_flow import repair  # noqa: F401
from test_repair_workspace_completion import setup  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
import repair_policy as policy
from supervisor_handoff import criteria_contract


def test_executor_cannot_downgrade_semantic_criterion(repair, monkeypatch):
    root, wt, st, session, controller = repair
    controller._final_criteria_contract = criteria_contract('전수 대조해줘', {'criteria': [
        {'text': '전수 대조와 미확인 목록', 'verification_method': 'semantic'}]})
    session['verification_plan'] = [{'criterion_id': 'C1', 'method': 'test', 'command': 'pytest test.py'}]
    monkeypatch.setattr('repair_check_runner.check', lambda *a: pytest.fail('test cannot prove semantic criterion'))
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert result['stage'] == 'plan' and result['missing_criteria'] == ['C1']


def test_live_change_stops_remaining_expensive_checks(repair, monkeypatch):
    root, wt, st, session, controller = repair
    controller._final_criteria_contract = criteria_contract('수리', {'criteria': [{'text': 'a'}, {'text': 'b'}]})
    session['verification_plan'] = [{'criterion_id': 'C1', 'command': 'pytest first.py'},
                                    {'criterion_id': 'C2', 'command': 'pytest expensive.py'}]
    calls = []
    def check(*args):
        calls.append(args[3])
        (root / 'b.txt').write_text('concurrent change')
        return {'status': 'passed', 'test_report': {'passed': True}, 'id': 'first'}
    monkeypatch.setattr('repair_check_runner.check', check)
    result = policy.prepare(controller, str(root), session, lambda *a: pytest.fail('late gate'), st._candidate)
    assert result['stage'] == 'conflict' and result['changed_files'] == ['b.txt']
    assert calls == ['pytest first.py']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
