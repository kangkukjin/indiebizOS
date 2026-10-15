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
