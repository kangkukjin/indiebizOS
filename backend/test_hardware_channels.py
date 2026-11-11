"""한 PC 의 사용자 세션 헬퍼와 관리 서비스는 손발 하나다 — 묶음·분배·표시·해제 계약."""
import boot_paths
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_resident_pcs
import device_registry
import limb_keys
import resident_pcs as pcs
import resident_store


@pytest.fixture
def pair(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)

    def enrolled(name, installation, scope, hostname='DESKTOP-1', **caps):
        invite = limb_keys.resident_invite(name)
        rec = limb_keys.resident_enroll(invite['key'], installation * 32)
        limb_keys.resident_update(rec['device_id'], last_seen=time.time(), capabilities={
            'os': 'windows', 'arch': 'amd64', 'hostname': hostname, 'service_scope': scope,
            'elevation': True, **caps})
        return rec

    user = enrolled('tv', 'a', 'user_login')
    service = enrolled('tv 관리', 'b', 'machine', elevation_unattended=True, execution_account='LocalSystem')
    return user, service, enrolled


def rows():
    return {r['alias']: r for r in pcs.devices() if (r.get('registration') or {}).get('adapter') != 'network-api'}


def test_unattached_service_is_its_own_row_with_a_proposed_pc(pair):
    user, service, _ = pair
    listed = rows()
    assert set(listed) == {'tv', 'tv 관리'}
    assert listed['tv 관리']['attach_candidate'] == {'device_id': user['device_id'], 'alias': 'tv'}
    assert 'attach_candidate' not in listed['tv']
    # 묶기 전에는 관리자 명령도 이름이 가리킨 사용자 세션 헬퍼로 간다(종전 동작).
    receipt = pcs.submit('tv', {'op': 'shell', 'cmd': 'whoami', 'elevate': True})
    assert receipt['limb'] == user['device_id'] and 'channel' not in receipt


def test_attached_service_folds_into_one_limb_and_takes_unattended_elevation(pair):
    user, service, _ = pair
    limb_keys.resident_attach(service['device_id'], user['device_id'])
    listed = rows()
    assert set(listed) == {'tv'}
    assert [c['device_id'] for c in listed['tv']['channels']] == [service['device_id']]
    assert limb_keys.hardware_of(service['device_id']) == user['device_id']
    assert limb_keys.hardware_of(user['device_id']) is None

    elevated = pcs.submit('tv', {'op': 'shell', 'cmd': 'whoami', 'elevate': True})
    assert elevated['limb'] == service['device_id'] and elevated['limb_name'] == 'tv'
    assert elevated['channel'] == 'machine' and elevated['hardware'] == user['device_id']
    assert elevated['execution_account'] == 'LocalSystem'
    # 권한을 요구하지 않은 명령·화면 작업은 사용자 세션에 남는다.
    plain = pcs.submit('tv', {'op': 'shell', 'cmd': 'whoami'})
    assert plain['limb'] == user['device_id'] and 'channel' not in plain
    screen = pcs.submit('tv', {'op': 'screen', 'mode': 'interactive'})
    assert screen['limb'] == user['device_id']
    # 한 PC 의 이력은 통로를 가리지 않고 함께 읽힌다.
    jobs = {t['id'] for t in resident_store.history(device=pcs.hardware_devices('tv'))['tasks']}
    assert {elevated['job_id'], plain['job_id'], screen['job_id']} <= jobs


def test_elevation_falls_back_to_the_user_session_when_the_service_is_unavailable(pair):
    user, service, _ = pair
    limb_keys.resident_attach(service['device_id'], user['device_id'])
    command = {'op': 'shell', 'cmd': 'whoami', 'elevate': True}
    limb_keys.resident_update(service['device_id'], last_seen=time.time() - 600)
    assert pcs.submit('tv', command)['limb'] == user['device_id']
    limb_keys.resident_update(service['device_id'], last_seen=time.time(), paused=True)
    assert pcs.submit('tv', command)['limb'] == user['device_id']
    limb_keys.resident_update(service['device_id'], paused=False)
    assert pcs.submit('tv', command)['limb'] == service['device_id']
    # 대화형 세션의 권한 상승은 사용자 화면의 일이다.
    assert pcs.channel_for(pcs.resolve('tv'), {**command, 'mode': 'interactive'})['device_id'] == user['device_id']
    # 통로를 직접 지명하면 그 통로가 받는다.
    assert pcs.submit(service['device_id'], {'op': 'shell', 'cmd': 'whoami'})['limb'] == service['device_id']


def test_attach_requires_matching_roles_and_the_same_computer(pair):
    user, service, enrolled = pair
    with pytest.raises(ValueError, match='방향이나 종류'):
        limb_keys.resident_attach(user['device_id'], service['device_id'])
    other = enrolled('office', 'c', 'user_login', hostname='DESKTOP-2')
    with pytest.raises(ValueError, match='컴퓨터 이름이 다릅니다'):
        limb_keys.resident_attach(service['device_id'], other['device_id'])
    with pytest.raises(ValueError, match='찾지 못했습니다'):
        limb_keys.resident_attach(service['device_id'], service['device_id'])
    limb_keys.resident_attach(service['device_id'], user['device_id'])
    second = enrolled('tv 관리2', 'd', 'machine', elevation_unattended=True)
    with pytest.raises(ValueError, match='이미 관리 서비스가 묶여'):
        limb_keys.resident_attach(second['device_id'], user['device_id'])
    # 같은 이름의 컴퓨터가 둘이면 후보를 제안하지 않는다 — 주인이 고를 일이다.
    limb_keys.resident_attach(service['device_id'], None)
    enrolled('twin', 'e', 'user_login')
    assert 'attach_candidate' not in rows()['tv 관리']


def test_removing_or_pausing_the_pc_covers_its_service_and_orphans_stay_visible(pair):
    user, service, _ = pair
    limb_keys.resident_attach(service['device_id'], user['device_id'])
    pcs.set_paused('tv', True)
    assert limb_keys.get_by_device(service['device_id'])['registration']['paused'] is True
    pcs.set_paused('tv', False)
    pcs.remove('tv')
    for device in (user, service):
        assert limb_keys.get_by_device(device['device_id'])['registration']['state'] == 'removal_pending'
    # 주 등록이 사라진 뒤에도 통로가 남아 있다면 숨기지 않는다.
    limb_keys.resident_update(user['device_id'], state='removed')
    assert limb_keys.hardware_of(service['device_id']) is None
    assert 'tv 관리' in rows()


def test_attach_endpoint_binds_and_releases(pair):
    user, service, _ = pair
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    with TestClient(app) as client:
        bound = client.post('/remote-pcs/attach', json={'target': service['device_id'], 'primary': user['device_id']})
        assert bound.status_code == 200 and bound.json()['registration']['attached_to'] == user['device_id']
        listed = [r for r in client.get('/remote-pcs').json()['items'] if r['alias'].startswith('tv')]
        assert [r['alias'] for r in listed] == ['tv'] and listed[0]['channels'][0]['alias'] == 'tv 관리'
        assert client.post('/remote-pcs/attach', json={'target': service['device_id']}).status_code == 200
        assert {r['alias'] for r in client.get('/remote-pcs').json()['items']} >= {'tv', 'tv 관리'}
        wrong = client.post('/remote-pcs/attach', json={'target': user['device_id'], 'primary': service['device_id']})
        assert wrong.status_code == 400
