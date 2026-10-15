"""회원 완료 판정은 저장한 파일 유무와 한도 중단을 구별한다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace

import pytest
import member_runtime
import member_session
import member_bridge
from providers import base


@pytest.mark.parametrize('delivered', [False, True])
def test_limit_is_not_user_cancel_or_success_even_after_partial_delivery(tmp_path, monkeypatch, delivered):
    monkeypatch.setattr(member_session, '_base', lambda: tmp_path)
    monkeypatch.setattr(member_bridge, 'connected', lambda device: False)
    reason = '설정된 전체 작업 토큰 한도에 도달했습니다'
    monkeypatch.setattr(base, 'turn_limit_reason', lambda: {'code': 'token_limit', 'reason': reason})
    def stream(*args, **kwargs):
        if delivered:
            member_runtime.current()['delivered_files'] = [{'path': 'partial.txt', 'saved': True}]
        yield {'type': '_turn_meta', 'turn_tokens': 64001}
        yield {'type': 'final', 'content': '사용자가 작업을 중단했습니다.'}
    def init(session):
        session.runner = SimpleNamespace(config={}, cognitive_stream=stream)
    monkeypatch.setattr(member_session.MemberSession, '_ensure_runner', init)
    result = member_session.MemberSessionManager(tmp_path).turn('member', 'device', 4, 'name', '대사 보고서')
    assert result['success'] is False
    assert result['error'] == reason
    assert result['response'] == reason
    assert len(result['files']) == int(delivered)
    assert result['tokens'] == 64001


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_default_budget_is_unlimited_and_usage_survives_failed_turn(tmp_path, monkeypatch):
    import json
    import time
    import member_activity
    monkeypatch.setattr(member_session, '_base', lambda: tmp_path)
    monkeypatch.setattr(member_bridge, 'connected', lambda device: False)
    manager = member_session.MemberSessionManager(tmp_path)
    assert all(manager.policy[k] is None for k in ('hard_token_limit', 'deadline_s', 'max_model_calls', 'max_jobs_per_turn', 'daily_turns', 'global_daily_turns'))
    day = time.strftime('%Y-%m-%d')
    (tmp_path / 'data').mkdir(exist_ok=True)
    (tmp_path / 'data/member_usage.json').write_text(json.dumps({'member': {day: {'turns': 500, 'tokens': 12}}}))
    def stream(*args, **kwargs):
        assert member_runtime.current()['deadline'] == float('inf')
        base.ProviderMetrics().record_usage(1, {'input_tokens': 70000, 'output_tokens': 14000})
        assert base.turn_limit_reason() is None
        raise RuntimeError('model disconnected')
        yield
    monkeypatch.setattr(member_session.MemberSession, '_ensure_runner', lambda session: setattr(session, 'runner', SimpleNamespace(config={}, cognitive_stream=stream)))
    result = manager.turn('member', 'device', 4, 'name', '월별 매출 비교')
    assert not result['success']
    assert manager._usage()['member'][day] == {'turns': 501, 'tokens': 84012}
    task = member_activity.recent(tmp_path, 'member')[0]
    assert task['status'] == 'failed' and task['tokens'] == 84000
    assert task['request'] == '월별 매출 비교'
    manager.policy['daily_turns'] = 1
    assert manager.turn('member', 'device', 4, 'name', '다음 작업')['error_type'] == 'limit'
