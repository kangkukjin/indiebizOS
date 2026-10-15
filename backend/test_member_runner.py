"""회원 계획의 자료형 오류는 실행기 예외 전에 한 번 정정한다."""
import boot_paths  # noqa: F401
import json
from types import SimpleNamespace

import pytest
from member_runner import MemberRunner


@pytest.mark.parametrize('bad', [
    {'capability_focus': ['self:read']},
    {'imagined_ibl': {'code': '[self:read]{}'}},
    {'ibl_focus': {'highlight_actions': [1]}},
    {'criteria': '완료'},
])
def test_malformed_member_plan_is_corrected_before_execution(monkeypatch, tmp_path, bad):
    import consciousness_agent
    runner = MemberRunner.__new__(MemberRunner)
    runner.config = {}
    runner.project_path = tmp_path
    monkeypatch.setattr(runner, '_role_provider', lambda role: SimpleNamespace(is_ready=True))
    monkeypatch.setattr(runner, '_load_role', lambda: '회원 역할')
    monkeypatch.setattr(runner, '_build_system_prompt', lambda role: role)
    monkeypatch.setattr(runner, '_get_available_tools', lambda: ['execute_ibl'])
    good = {'task_framing': '출하량 비교', 'achievement_criteria': '보고서 저장 및 재독'}
    responses = iter([json.dumps({**good, **bad}), json.dumps(good)])
    calls = []
    def respond(provider, prompt, **kwargs):
        calls.append(prompt)
        return next(responses)
    monkeypatch.setattr(consciousness_agent, 'call_oneshot_provider', respond)
    assert runner._run_consciousness('보고서 작성', []) == good
    assert len(calls) == 2 and 'validation_error' in calls[-1]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
