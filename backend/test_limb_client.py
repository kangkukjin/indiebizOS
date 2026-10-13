"""IndieBiz OS 손발(폰) — 등록·IBL 봉투·거절·해제 계약 (docs/INDIEBIZ_BODY_AS_LIMB_DESIGN_2026_10_13.md)."""
import boot_paths  # noqa: F401
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api_resident_pcs
import device_registry
import limb_keys
import limb_client
import resident_pcs as pcs
import resident_store


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    return TestClient(app)


@pytest.fixture
def phone_env(tmp_path, monkeypatch):
    ud = tmp_path / 'phone' / 'userdata'
    ud.mkdir(parents=True)
    monkeypatch.setenv('INDIEBIZ_USERDATA', str(ud))
    monkeypatch.setattr(limb_client, '_body_profile', lambda: 'phone')
    return ud


def _enroll_phone(alias='삼성1', iid='c' * 32):
    inv = limb_keys.resident_invite(alias, 0)
    return limb_keys.resident_enroll(inv['key'], iid, alias, kind='phone', adapter='indiebiz-v1')


def _client(hub, rec, execute, cfg_extra=None):
    cfg = {'hub': 'http://hub', 'key': rec['key'], 'installation_id': rec['registration']['installation_id'],
           'alias': rec['alias'], 'device_id': rec['device_id'], **(cfg_extra or {})}
    limb_client.config_path().parent.mkdir(parents=True, exist_ok=True)
    limb_client.config_path().write_text(json.dumps(cfg), encoding='utf-8')

    def post(path, payload, timeout):
        r = hub.post(f'/limb/resident/{path}', json=payload)
        if r.status_code != 200:
            raise limb_client.LimbError(str(r.json().get('detail')), r.status_code)
        return r.json()
    return limb_client.LimbClient(cfg, 8765, post=post, execute=execute, card=lambda: {'identity': {'body': 'phone'}})


def test_phone_registration_runs_ibl_and_reports_result(hub, phone_env):
    rec = _enroll_phone()
    assert rec['registration']['adapter'] == 'indiebiz-v1' and rec['registration']['kind'] == 'phone'
    seen = []

    def execute(code, agent_id, timeout):
        seen.append((code, agent_id, timeout))
        return {'success': True, 'items': [{'ok': True}], 'message': '진동 400ms'}
    c = _client(hub, rec, execute)
    receipt = pcs.submit(rec['device_id'], {'op': 'ibl', 'ibl': "[limbs:phone]{op:'vibrate'}", 'timeout': 30}, 'req-1')
    assert receipt['state'] == 'queued'
    c.step(inline=True, wait=0)          # 작업 수신 + inline 실행 → 사건 spool
    assert seen == [("[limbs:phone]{op:'vibrate'}", 'limb', 30.0)]
    c.step(inline=True, wait=0)          # 사건 상행 → 허브 원장 반영
    result = resident_store.wait_result(receipt['job_id'], timeout=0)
    assert result['items'] == [{'ok': True}]
    history = resident_store.history(job=receipt['job_id'])
    assert history['tasks'][0]['state'] == 'succeeded'
    assert not list((limb_client.spool_dir() / 'events').glob('*.json'))   # ack 받은 사건은 지워진다
    # 허브가 신고받은 capabilities 로 몸을 안다
    reg = limb_keys.get_by_device(rec['device_id'])['registration']
    assert reg['capabilities']['adapter'] == 'indiebiz-v1' and reg['capabilities']['shell'] is False


def test_phone_body_refuses_shell_and_helper_refuses_ibl(hub, phone_env):
    phone = _enroll_phone()
    with pytest.raises(ValueError, match='unsupported_on_this_body'):
        pcs.submit(phone['device_id'], {'op': 'shell', 'cmd': 'ls'}, 'req-s')
    with pytest.raises(ValueError, match='ibl_code_required'):
        pcs.submit(phone['device_id'], {'op': 'ibl', 'ibl': '  '}, 'req-e')
    inv = limb_keys.resident_invite('desk', 0)
    pc = limb_keys.resident_enroll(inv['key'], 'd' * 32)
    with pytest.raises(ValueError, match='unsupported_resident_operation'):
        pcs.submit(pc['device_id'], {'op': 'ibl', 'ibl': '[self:read]{}'}, 'req-p')
    # 손발 쪽도 모르는 봉투는 정직하게 거절(허브 관문을 우회해 큐에 들어와도)
    c = _client(hub, phone, lambda *a: {'success': True})
    out = c._dispatch({'id': 'x', 'code': json.dumps({'op': 'shell', 'cmd': 'rm -rf /'})})
    assert out['success'] is False and out['error'] == 'unsupported_on_this_body'
    assert c._dispatch({'id': 'y', 'code': json.dumps({'op': 'info'})})['adapter'] == 'indiebiz-v1'


def test_failure_envelope_projects_to_failed_task(hub, phone_env):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *a: {'success': False, 'error': '마이크 권한 없음'})
    receipt = pcs.submit(rec['device_id'], {'op': 'ibl', 'ibl': "[sense:listen]{op:'record'}"}, 'req-f')
    c.step(inline=True, wait=0); c.step(inline=True, wait=0)
    assert resident_store.history(job=receipt['job_id'])['tasks'][0]['state'] == 'failed'


def test_remove_from_hub_wipes_phone_credential(hub, phone_env):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *a: {'success': True})
    pcs.remove(rec['device_id'])
    c.step(inline=True, wait=0)
    assert c.stopped.is_set() and not limb_client.config_path().exists()
    assert limb_keys.get_by_device(rec['device_id'])['registration']['state'] == 'removed'


def test_revoke_from_hub_wipes_phone_credential(hub, phone_env):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *a: {'success': True})
    limb_keys.revoke(rec['device_id'])
    c.step(inline=True, wait=0)
    assert c.stopped.is_set() and not limb_client.config_path().exists()


def test_restart_during_execution_reports_unknown_not_rerun(hub, phone_env):
    rec = _enroll_phone()
    calls = []
    c = _client(hub, rec, lambda *a: calls.append(a) or {'success': True})
    receipt = pcs.submit(rec['device_id'], {'op': 'ibl', 'ibl': "[limbs:phone]{op:'vibrate'}"}, 'req-r')
    c.step(inline=False, wait=0)                       # 수신만(워커는 띄우되 기록은 queued/running)
    c.stop()
    c._worker and c._worker.join(5)
    # 실행 중 죽은 것처럼 기록을 running 으로 되돌린다
    c._record(receipt['job_id'], state='running')
    for p in (limb_client.spool_dir() / 'events').glob('*.json'):
        p.unlink()
    c2 = _client(hub, rec, lambda *a: calls.append(a) or {'success': True})
    before = len(calls)
    c2._recover()
    assert len(calls) == before                        # 재실행 없음
    c2.step(inline=True, wait=0)
    task = resident_store.history(job=receipt['job_id'])['tasks'][0]
    assert task['state'] == 'unknown' and task['result']['unknown'] is True


def test_pc_profile_never_becomes_a_limb(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_client, '_body_profile', lambda: 'mac')
    monkeypatch.setenv('INDIEBIZ_USERDATA', str(tmp_path))
    limb_client.config_path().parent.mkdir(parents=True, exist_ok=True)
    limb_client.config_path().write_text(json.dumps({'hub': 'http://x', 'key': 'k', 'installation_id': 'i'}))
    assert limb_client.start(8765) is False


# ── 미디어 봉투(docs/MEDIA_SESSION_CONTRACT.md §6) → Kotlin MediaBridge 다리 ──────────────────────

def _media_session(**over):
    s = {'session_id': 'ab' * 16, 'purpose': 'camera',
         'grant': {'session_id': 'ab' * 16, 'role': 'device', 'device': 'd1', 'tracks': ['v0'],
                   'expires_at': 1e12, 'token': 'tok'},
         'tracks': [{'id': 'v0', 'kind': 'video', 'source': 'camera', 'from': 'device', 'to': 'hub', 'state': 'requested'}],
         'ice_servers': [{'urls': ['stun:stun.example:3478']}],
         'lease': {'lease_s': 20, 'keepalive_s': 5, 'reconnect_s': 30},
         'stream': {'url': 'wss://hub.example/limb/resident/media/' + 'ab' * 16}, 'timeout': 600}
    s.update(over)
    return s


class _FakeBridge:
    """Kotlin MediaBridge 의 가짜 — 호출 기록 + 정해진 답(JSON 문자열)."""
    def __init__(self, start_reply=None):
        self.calls = []
        self.start_reply = start_reply or {'accepted': True, 'session_id': 'ab' * 16}

    def start(self, envelope_json):
        self.calls.append(('start', json.loads(envelope_json)))
        return json.dumps(self.start_reply)

    def stop(self, sid, reason):
        self.calls.append(('stop', sid, reason))
        return json.dumps({'stopped': True, 'session_id': sid})

    def status(self):
        self.calls.append(('status',))
        return json.dumps({'session_id': None, 'state': 'idle'})

    def capabilities(self):
        return json.dumps({'media_session': {'camera': True, 'microphone': True, 'speaker': True,
                                             'playback': True, 'screen': False},
                           'abi': 'armeabi-v7a', 'sdk': 28, 'permissions': {'camera': True, 'record_audio': False}})


def _bare_client(monkeypatch, bridge):
    monkeypatch.setattr(limb_client, '_bridge_factory', (lambda: bridge) if bridge is not None else None)
    cfg = {'hub': 'http://hub', 'key': 'k' * 32, 'installation_id': 'i' * 32, 'alias': '삼성1', 'device_id': 'd1'}
    return limb_client.LimbClient(cfg, 8765, post=lambda *a: {}, execute=lambda *a: {'success': True},
                                  card=lambda: {'identity': {'body': 'phone'}})


def _media_job(action='start', session=None, **extra):
    env = {'op': 'media', 'action': action, **extra}
    if session is not None:
        env['session'] = session
    return {'id': 'm1', 'code': json.dumps(env)}


def test_media_op_is_unsupported_on_a_body_without_the_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv('INDIEBIZ_USERDATA', str(tmp_path))
    monkeypatch.setattr(limb_client, '_body_profile', lambda: 'mac')     # PC: jclass 자체가 없다
    c = _bare_client(monkeypatch, None)
    assert 'media' not in limb_client.supported_ops()
    out = c._dispatch(_media_job(session=_media_session()))
    assert out['success'] is False and out['error'] == 'unsupported_on_this_body'
    assert 'media' not in out['supported'] and 'media_session' not in c.capabilities()
    # 폰 프로파일이어도 다리 import 가 실패하면(구형 APK) 같은 정직한 거절
    monkeypatch.setattr(limb_client, '_body_profile', lambda: 'phone')
    assert c._dispatch(_media_job(action='status'))['error'] == 'unsupported_on_this_body'


def test_media_envelope_validation_rejects_before_touching_the_bridge(phone_env, monkeypatch):
    bridge = _FakeBridge()
    c = _bare_client(monkeypatch, bridge)
    bad = [
        (None, 'session_required'),
        (_media_session(session_id='x'), 'session_id_required'),
        (_media_session(grant={'role': 'device'}), 'grant_required'),
        (_media_session(purpose='teleport'), 'purpose_unknown'),
        (_media_session(stream={'url': 'https://hub.example/x'}), 'stream_url_required'),
        (_media_session(tracks=[]), 'tracks_required'),
    ]
    for session, why in bad:
        out = c._dispatch(_media_job(session=session))
        assert out == {'success': False, 'error': 'invalid_media_envelope', 'detail': why}, why
    assert bridge.calls == []                       # 결함 봉투는 다리에 닿지 않는다
    assert c._dispatch(_media_job(action='rewind'))['error'] == 'unsupported_media_action'


def test_media_start_passes_auth_and_returns_acceptance_only(phone_env, monkeypatch):
    bridge = _FakeBridge()
    c = _bare_client(monkeypatch, bridge)
    assert 'media' in limb_client.supported_ops()
    out = c._dispatch(_media_job(session=_media_session()))
    assert out['success'] is True and out['accepted'] is True and out['session_id'] == 'ab' * 16
    kind, payload = bridge.calls[0]
    assert kind == 'start'
    assert payload['auth'] == {'key': 'k' * 32, 'installation_id': 'i' * 32}   # WS 첫 프레임 재료
    assert payload['grant']['token'] == 'tok' and payload['stream']['url'].startswith('wss://')
    # 계약 §6 원형(op: media_session, 칸이 최상위)도 같은 길
    env = {'op': 'media_session', **_media_session(purpose='microphone', tracks=[
        {'id': 'a0', 'kind': 'audio', 'source': 'mic', 'from': 'device', 'to': 'hub', 'state': 'requested'}])}
    out2 = c._dispatch({'id': 'm2', 'code': json.dumps(env)})
    assert out2['success'] is True and bridge.calls[-1][1]['purpose'] == 'microphone'
    assert 'op' not in bridge.calls[-1][1]
    # stop / status 는 세션 id·사유를 그대로 넘긴다
    assert c._dispatch(_media_job(action='stop', session={'session_id': 'ab' * 16}, reason='user'))['stopped'] is True
    assert bridge.calls[-1] == ('stop', 'ab' * 16, 'user')
    assert c._dispatch(_media_job(action='status'))['state'] == 'idle'
    # 능력 신고에 media_session 이 든다(허브는 이걸로 폰의 트랙·권한을 안다)
    caps = c.capabilities()
    assert 'media' in caps['ops'] and caps['media_session']['camera'] is True
    assert caps['media_session']['permissions'] == {'camera': True, 'record_audio': False}
    assert caps['media_session']['sdk'] == 28


def test_media_bridge_failure_codes_project_to_failed_result(phone_env, monkeypatch):
    bridge = _FakeBridge(start_reply={'error': 'device_busy', 'message': '다른 세션', 'active_session': 'cd' * 16})
    c = _bare_client(monkeypatch, bridge)
    out = c._dispatch(_media_job(session=_media_session()))
    assert out['success'] is False and out['error'] == 'device_busy' and out['active_session'] == 'cd' * 16
    bridge.start_reply = {'error': 'needs_local_action', 'needs_local_action': {
        'code': 'camera_unavailable', 'message': '폰에서 카메라 대기 모드를 시작해 주세요'}}
    out = c._dispatch(_media_job(session=_media_session()))
    assert out['error'] == 'needs_local_action' and out['needs_local_action']['code'] == 'camera_unavailable'
    # 다리가 JSON 아닌 것을 돌려주거나 예외를 던져도 루프는 산다
    bridge.start = lambda j: 'not json'
    assert c._dispatch(_media_job(session=_media_session()))['error'] == 'media_bridge_bad_reply'
    bridge.start = lambda j: (_ for _ in ()).throw(RuntimeError('jni down'))
    assert c._dispatch(_media_job(session=_media_session()))['error'].startswith('media_bridge_exception')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
