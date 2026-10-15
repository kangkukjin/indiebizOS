"""회원 데스크톱의 능력 협상과 실제 poll 모델 경계."""
import boot_paths  # noqa: F401
import asyncio
import api_limb


def test_desktop_connect_rejects_missing_protocol_before_touch(monkeypatch):
    monkeypatch.setattr(api_limb.limb_keys, 'validate', lambda key: {'desktop': {'public_key': 'test'}})
    monkeypatch.setattr(api_limb.limb_keys, 'is_member', lambda rec: True)
    for env in (None, {}, {'protocol': 1}):
        result = asyncio.run(api_limb.limb_connect(api_limb.ConnectRequest(key='test', mode='member', env=env)))
        assert result['error'] == 'unsupported_desktop_protocol'


def test_desktop_poll_uses_negotiated_environment(monkeypatch):
    rec = {'desktop': {'public_key': 'test'}, 'env': {'protocol': 2}, 'device_id': 'pc', 'member_id': 'member', 'session': 'now', 'approved': True}
    monkeypatch.setattr(api_limb.limb_keys, 'validate', lambda key: rec)
    monkeypatch.setattr(api_limb.dr, 'heartbeat', lambda device: None)
    import member_jobs
    monkeypatch.setattr(member_jobs, 'pull_blocking', lambda *args: [])
    req = api_limb.PollRequest(key='test', session='now', wait=0)
    assert asyncio.run(api_limb.limb_poll(req))['success']
    rec['env']['protocol'] = 1
    assert asyncio.run(api_limb.limb_poll(req))['error'] == 'unsupported_desktop_protocol'


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
