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


def observation_fixture(monkeypatch, *, volume='17', mute='0', advertised=True):
    """Protocol responses, including real Samsung namespaces and zero values."""
    calls = []
    def request(url, *, data=None, headers=None):
        calls.append((url, data, headers))
        if url.endswith('/dmr'):
            services = ''.join(
                f'<service><serviceType>urn:schemas-upnp-org:service:{name}:1</serviceType>'
                f'<controlURL>/control/{name}</controlURL><SCPDURL>/{name}.xml</SCPDURL></service>'
                for name in ('RenderingControl', 'AVTransport'))
            return f'<root xmlns="urn:schemas-upnp-org:device-1-0"><device><serviceList>{services}</serviceList></device></root>'.encode()
        if url.endswith('.xml'):
            actions = ['GetVolume', 'GetMute', 'GetTransportInfo', 'GetPositionInfo'] if advertised else []
            return ('<scpd xmlns="urn:schemas-upnp-org:service-1-0"><actionList>' + ''.join(
                f'<action><name>{a}</name></action>' for a in actions) + '</actionList></scpd>').encode()
        action = headers['SOAPAction'].strip('"').split('#')[1]
        urn = headers['SOAPAction'].strip('"').split('#')[0]
        values = {'GetVolume': f'<CurrentVolume>{volume}</CurrentVolume>',
                  'GetMute': f'<CurrentMute>{mute}</CurrentMute>',
                  'GetTransportInfo': '<CurrentTransportState>PLAYING</CurrentTransportState>',
                  'GetPositionInfo': '<Track>1</Track><RelTime>0:01:12</RelTime><TrackDuration>0:03:00</TrackDuration>'}
        return (f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                f'<u:{action}Response xmlns:u="{urn}">{values[action]}</u:{action}Response></s:Body></s:Envelope>').encode()
    monkeypatch.setattr(tv, 'observation_request', request)
    return calls


def test_status_reads_volume_mute_and_scoped_playback_without_mutations(monkeypatch):
    calls = observation_fixture(monkeypatch, volume='0')
    monkeypatch.setattr(tv, 'status', lambda _: {'reachable': True, 'power': 'on', 'verified': True, 'apps': {}})
    result = tv.execute({'op': 'status'}, {'ip': '192.0.2.1'}, lambda _: pytest.fail('token write'), ROOT)
    obs = result['observations']
    assert obs['volume']['value'] == 0 and obs['volume']['verified']
    assert obs['mute']['value'] is False
    assert obs['dlna_transport']['value'] == 'PLAYING'
    assert obs['dlna_transport']['scope'] == 'dlna_renderer'
    assert obs['dlna_position']['value']['position'] == '0:01:12'
    assert obs['input_source']['state'] == 'unsupported'
    assert obs['media_playback']['state'] == 'not_configured'
    assert result['verification_scope'] == 'power_only'
    assert all('#Get' in headers['SOAPAction'] for _, data, headers in calls if data)


@pytest.mark.parametrize('volume,mute', [('101', '7'), ('', ''), ('NaN', 'not-muted')])
def test_invalid_observations_never_become_zero_or_false(monkeypatch, volume, mute):
    observation_fixture(monkeypatch, volume=volume, mute=mute)
    obs = tv.upnp_observations({'ip': '192.0.2.1'})
    for key in ('volume', 'mute'):
        assert obs[key]['value'] is None and obs[key]['state'] == 'invalid_response'
    assert obs['dlna_transport']['verified']


def test_unadvertised_action_is_not_executed(monkeypatch):
    calls = observation_fixture(monkeypatch, advertised=False)
    obs = tv.upnp_observations({'ip': '192.0.2.1'})
    assert obs['volume']['state'] == 'unsupported'
    assert not any(data for _, data, _ in calls)


def test_unreachable_is_not_unsupported(monkeypatch):
    def fail(*args, **kwargs):
        raise tv.ObservationError('unavailable', 'connection_failed')
    monkeypatch.setattr(tv, 'observation_request', fail)
    obs = tv.upnp_observations({'ip': '192.0.2.1'})
    assert all(x['state'] == 'unavailable' and x['value'] is None for x in obs.values())


@pytest.mark.parametrize('path', ['http://192.0.2.2:9197/control', '//192.0.2.1:80/x',
                                  'http://user:secret@192.0.2.1:9197/x', 'file:///etc/passwd'])
def test_service_advertisements_cannot_redirect_observation(path):
    with pytest.raises(tv.ObservationError):
        tv.service_url({'ip': '192.0.2.1'}, 'http://192.0.2.1:9197/dmr', path)


def test_xml_fault_and_invalid_response_do_not_verify():
    with pytest.raises(tv.ObservationError):
        tv.observation_xml(b'<!DOCTYPE root [<!ENTITY x "secret">]><root>&x;</root>')
    with pytest.raises(tv.ObservationError):
        tv.observation_xml(b'<broken')


def test_smartthings_old_report_never_claims_live_verification(monkeypatch):
    seen = []
    def request(url, **kwargs):
        seen.append((url, kwargs))
        return json.dumps({'components': {'main': {
            'audioVolume': {'volume': {'value': 42, 'timestamp': '2020-01-01T00:00:00Z'}},
            'audioMute': {'mute': {'value': 'unmuted'}},
            'mediaInputSource': {'inputSource': {'value': 'HDMI2', 'timestamp': '2020-01-01T00:00:00Z'}},
            'mediaPlayback': {'playbackStatus': {'value': 'playing'}}}}}).encode()
    monkeypatch.setattr(tv, 'observation_request', request)
    result = tv.cloud_observations({'smartthings': {'device_id': 'test-tv', 'token': 'secret'}})
    assert result['input_source']['value'] == 'HDMI2'
    assert result['input_source']['reported_at'] == '2020-01-01T00:00:00Z'
    assert result['mute']['value'] is False
    assert result['media_playback']['reported_at'] is None
    assert all(v['state'] == 'reported' and not v['verified'] for v in result.values())
    assert seen[0][1]['headers']['Authorization'] == 'Bearer secret'
    assert 'secret' not in json.dumps(result)


def test_cloud_fallback_preserves_local_evidence_and_power(monkeypatch):
    monkeypatch.setattr(tv, 'status', lambda _: {'reachable': False, 'power': 'unknown', 'verified': False, 'apps': {}})
    monkeypatch.setattr(tv, 'upnp_observations', lambda _: {
        'volume': tv.observation(0), 'input_source': tv.observation(state='unsupported')})
    monkeypatch.setattr(tv, 'cloud_observations', lambda _: {
        'volume': tv.observation(99, state='reported', source='smartthings'),
        'input_source': tv.observation('HDMI1', state='reported', source='smartthings')})
    result = tv.detailed_status({})
    assert result['observations']['volume']['value'] == 0
    assert result['observations']['input_source']['state'] == 'reported'
    assert result['local_observations']['input_source']['state'] == 'unsupported'
    assert result['power'] == 'unknown' and not result['verified']


def test_cloud_unauthorized_and_missing_capabilities(monkeypatch):
    monkeypatch.setattr(tv, 'observation_request', lambda *a, **kw: b'{"components":{"main":{}}}')
    cfg = {'smartthings': {'device_id': 'test-tv', 'token': 'secret'}}
    assert all(x['state'] == 'unsupported' for x in tv.cloud_observations(cfg).values())
    def unauthorized(*a, **kw):
        raise tv.ObservationError('unauthorized', 'http_401')
    monkeypatch.setattr(tv, 'observation_request', unauthorized)
    assert all(x['state'] == 'unauthorized' for x in tv.cloud_observations(cfg).values())


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
