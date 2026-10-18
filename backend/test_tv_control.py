"""TV control: truthful observations, bounded toggles and shared app contracts."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path
import json
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tv_control', ROOT / 'data/instruments/tv_control.py')
tv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tv)


def test_unreachable_is_unknown_and_missing_power_is_not_on(monkeypatch):
    monkeypatch.setattr(tv, 'rest', lambda *a: (_ for _ in ()).throw(TimeoutError()))
    assert tv.status({}) == {'reachable': False, 'power': 'unknown', 'verified': False, 'apps': {},
                             'message': 'TV 응답 없음. 전원·네트워크 상태는 확인되지 않았습니다.'}
    monkeypatch.setattr(tv, 'rest', lambda *a: '{"device":{}}')
    assert tv.status({})['power'] == 'unknown'
    assert not tv.status({})['verified']


def test_off_sends_once_and_unreachable_does_not_verify(monkeypatch):
    observations = iter([{'power': 'on'}, {'power': 'unknown', 'reachable': False}])
    monkeypatch.setattr(tv, 'status', lambda cfg: next(observations))
    calls = []
    monkeypatch.setattr(tv, 'send_keys', lambda *args: calls.append(args) or {'sent': ['KEY_POWER']})
    result = tv.execute({'op': 'off'}, {}, lambda _: None, ROOT)
    assert len(calls) == 1 and result['verified'] is False
    assert result['power'] == 'unknown'


def test_unknown_power_blocks_toggle_before_transport(monkeypatch):
    monkeypatch.setattr(tv, 'status', lambda cfg: {'power': 'unknown'})
    monkeypatch.setattr(tv, 'send_keys', lambda *a: pytest.fail('toggle sent'))
    with pytest.raises(RuntimeError):
        tv.execute({'op': 'off'}, {}, lambda _: None, ROOT)


def test_launch_failure_is_not_wrapped_as_success(monkeypatch):
    monkeypatch.setattr(tv, 'status', lambda cfg: {'power': 'on'})
    monkeypatch.setattr(tv, 'rest', lambda *a: '')
    monkeypatch.setattr(tv, 'app_state', lambda *a: {'visible': False})
    monkeypatch.setattr(tv.time, 'sleep', lambda _: None)
    result = tv.execute({'op': 'launch', 'app': '123'}, {}, lambda _: None, ROOT)
    assert result['success'] is False and result['verified'] is False


def test_launch_visible_is_not_video_playback(monkeypatch):
    monkeypatch.setattr(tv, 'status', lambda cfg: {'power': 'on'})
    monkeypatch.setattr(tv, 'rest', lambda *a: '')
    monkeypatch.setattr(tv, 'app_state', lambda *a: {'visible': True})
    monkeypatch.setattr(tv.time, 'sleep', lambda _: None)
    result = tv.execute({'op': 'launch', 'app': '123'}, {}, lambda _: None, ROOT)
    assert result['verified'] is True and '별도 확인' in result['message']


@pytest.mark.parametrize('keys', [[], ['INVALID'], ['KEY_HOME:10'], ['KEY_HOME:nan'], ['KEY_HOME'] * 41])
def test_invalid_key_sequence_never_connects(monkeypatch, keys):
    monkeypatch.setattr(tv, 'Remote', lambda *a: pytest.fail('transport opened'))
    with pytest.raises(ValueError):
        tv.send_keys({}, keys, lambda _: None)


def test_transport_closed_after_partial_failure(monkeypatch):
    events = []
    class Remote:
        def __init__(self, *a): pass
        def key(self, key): raise OSError('lost after send')
        def close(self): events.append('closed')
    monkeypatch.setattr(tv, 'Remote', Remote)
    with pytest.raises(OSError):
        tv.send_keys({}, ['KEY_MUTE'], lambda _: None)
    assert events == ['closed']


def test_handshake_eof_is_bounded():
    class Socket:
        def recv(self, n): return b''
    remote = object.__new__(tv.Remote)
    remote.s = Socket()
    with pytest.raises(EOFError):
        remote._n(1)


def test_registered_target_required_and_connection_cannot_be_overridden(monkeypatch):
    import hardware_registry
    monkeypatch.setattr(tv, 'registry', lambda: (hardware_registry, ROOT))
    monkeypatch.setattr(hardware_registry, 'connection', lambda _: (_ for _ in ()).throw(PermissionError('paused')))
    monkeypatch.setattr(tv, 'execute', lambda *a: pytest.fail('wrong target executed'))
    with pytest.raises(ValueError):
        tv.run({'target': 'tv', 'ip': '192.0.2.1'})
    with pytest.raises(PermissionError):
        tv.run({'target': 'tv'})


def test_all_app_modes_share_target_and_compilable_script_contract():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from iblbuild_appview import check_app_templates_edition2
    app = yaml.safe_load((ROOT / 'data/instruments/living_tv.yaml').read_text())
    for mode in app['modes']:
        assert all(i['key'] != 'target' for i in mode.get('inputs', []))
        for item in [mode] + mode.get('buttons', []):
            assert 'id:"TV제어"' in item['action'] and 'target:"거실TV"' in item['action']
            assert '$target' not in item['action']
            assert 'assert $r.success == true' in item['action']
            assert 'config.json' not in item['action'] and 'guestpc' not in item['action']
    data = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text())
    data['nodes']['self']['actions']['test_tv'] = {'app': app}
    issues, warnings = check_app_templates_edition2(data, ROOT)
    assert not issues, issues


@pytest.mark.parametrize('refresh', [False, True])
@pytest.mark.parametrize('page', ['1', '2', '8', ' 3 '])
def test_now_broadcast_text_page_reaches_registered_script(monkeypatch, tmp_path, page, refresh):
    import ibl_engine
    from ibl_callable_contract import checked_values
    from ibl_v2_entry import handle_request

    app = yaml.safe_load((ROOT / 'data/instruments/living_tv.yaml').read_text())
    mode = next(mode for mode in app['modes'] if mode['name'] == '지금 방송')
    code = mode['buttons'][0]['action'] if refresh else mode['action']
    contract = yaml.safe_load((ROOT / 'data/scripts/registry.yaml').read_text())['TV제어']['callable_contract']
    calls = []

    def execute(step, project_path, agent_id=None):
        assert (step['_node'], step['action'], step['params']['id']) == ('self', 'script', 'TV제어')
        _, args = checked_values(contract, step['params']['args'])
        calls.append(args)
        return {'success': True, 'value': {
            'success': True, 'op': args['op'], 'target': args['target'],
            'verified': True, 'page': args['page'],
            'items': [{'ch': 1, 'name': '시험 채널', 'title': '시험 방송'}],
        }}

    monkeypatch.setattr(ibl_engine, 'execute_ibl', execute)
    result = handle_request({'edition': 2, 'code': code,
                             'inputs': {'page': page},
                             'declared_inputs': ['page']}, str(tmp_path), None)
    assert result['success'], result.get('error') or result.get('issues')
    assert len(calls) == 1
    assert calls[0]['target'] == '거실TV'
    assert type(calls[0]['page']) is int and calls[0]['page'] == int(page)
    assert calls[0].get('refresh', False) is refresh
    assert result['value']['items'][0]['title'] == '시험 방송'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
