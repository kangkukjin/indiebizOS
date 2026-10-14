"""미디어 세션 — 임대·권한·시그널 질서·확장관계 어댑터·통화 초대/수락 계약 (docs/MEDIA_SESSION_CONTRACT.md)."""
import boot_paths  # noqa: F401
import json
import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_media
import api_resident_pcs
import device_registry
import limb_keys
import media_sessions as ms
import media_signaling as sig
import media_store
import resident_pcs as pcs
import resident_store
import resident_terminal_lan
import session_lease


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('INDIEBIZ_MEDIA_NO_SWEEPER', '1')
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    monkeypatch.setattr(resident_terminal_lan, 'offer', lambda *a, **k: {})
    policy = json.loads(json.dumps(sig.policy()))   # 실제 data/media_policy.yaml 위에 시험용 대기 시간만 줄인다
    policy['signaling']['bundle_wait_s'] = 0.2
    monkeypatch.setattr(sig, '_policy_cache', (None, policy))
    monkeypatch.setattr(sig, 'policy', lambda: policy)
    monkeypatch.setattr(sig, 'relay_base', lambda: '')
    sent = []
    monkeypatch.setattr(ms, 'nostr', sig.NostrTransport(sender=lambda to, content, tags: sent.append((to, json.loads(content), tags)) or True))
    monkeypatch.setattr(ms.nostr, 'my_pubkey_hex', lambda: 'f' * 64)
    ms.reset_for_tests()
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    app.include_router(api_media.router)
    client = TestClient(app, base_url='http://localhost')
    client.sent = sent
    yield client
    ms.reset_for_tests()


def _device(alias='cam-pc', kind='pc', adapter='resident-v1', caps=None):
    inv = limb_keys.resident_invite(alias, 0)
    rec = limb_keys.resident_enroll(inv['key'], uuid.uuid4().hex, alias, kind=kind, adapter=adapter)
    media = caps if caps is not None else {'camera': True, 'microphone': True, 'speaker': True, 'playback': True}
    limb_keys.resident_update(rec['device_id'], capabilities={'media_session': media, 'ops': ['ibl', 'info', 'media'],
                                                             'abi': 'armeabi-v7a' if kind == 'phone' else 'x64'},
                              last_seen=time.time())
    return limb_keys.get_by_device(rec['device_id'])


# ── 임대 ────────────────────────────────────────────────────────────────────────
def test_lease_renew_order_and_idempotent_close():
    lease = session_lease.Lease('media')
    assert lease.lease_s == 20 and lease.keepalive_s == 5
    assert lease.renew(0, 1) and lease.renew(0, 2)
    assert not lease.renew(0, 2), '지난 순번은 임대를 되살리지 못한다'
    assert not lease.renew(1, 1), '다른 세대의 확인은 거절'
    assert lease.advance_generation() == 1 and lease.renew(1, 1)
    lease.rewind(lease.lease_s + 1)
    assert lease.expired() and not lease.renew()
    assert lease.close('x') and not lease.close('y') and lease.reason == 'x'
    assert session_lease.profile('nope')['lease_s'] == session_lease.profile('media')['lease_s']


def test_signal_order_signature_and_candidate_buffer():
    secret = 'ab' * 32
    f = sig.sign(sig.new_frame('0' * 32, 'caller', 'callee', 'offer', {'sdp': 'v=0\r\na=fingerprint:sha-256 AA:BB'}), secret)
    assert sig.verify(f, secret)
    tampered = {**f, 'payload': {'sdp': 'changed'}}
    assert not sig.verify(tampered, secret), '릴레이가 바꾸면 검증 실패'
    assert sig.fingerprint_of(f['payload']['sdp']) == 'sha-256 AA:BB'
    order = sig.Order()
    assert order.admit({'msg_id': 'a', 'generation': 1, 'seq': 1})[0]
    assert order.admit({'msg_id': 'a', 'generation': 1, 'seq': 2}) == (False, 'duplicate')
    assert order.admit({'msg_id': 'b', 'generation': 0, 'seq': 9}) == (False, 'stale_generation')
    assert order.admit({'msg_id': 'c', 'generation': 1, 'seq': 1}) == (False, 'stale_seq')
    assert order.admit({'msg_id': 'd', 'generation': 2, 'seq': 1})[0]
    buf = sig.CandidateBuffer()
    cand = {'type': 'candidate', 'generation': 0}
    assert buf.observe(cand) == [], '설명 전 candidate 는 붙든다'
    out = buf.observe({'type': 'offer', 'generation': 0})
    assert [x['type'] for x in out] == ['offer', 'candidate']
    assert buf.observe({'type': 'candidate', 'generation': 1}) == [], '새 세대는 새 버퍼'
    with pytest.raises(ValueError, match='invalid_frame_type'):
        sig.validate_frame({'v': 1, 'session_id': '0' * 32, 'type': 'shell', 'from': 'hub', 'to': 'device'})
    assert sig.is_call_frame_content(json.dumps(f)) and not sig.is_call_frame_content('안녕하세요')


# ── 확장관계 ────────────────────────────────────────────────────────────────────
def test_extension_camera_session_envelope_grant_and_lifecycle(hub):
    rec = _device()
    r = hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'camera', 'target': 'cam-pc', 'request_id': 'r1'})
    body = r.json()
    assert body['success'], body
    s = body['session']
    sid = s['session_id']
    assert s['authorization_basis'] == 'extension_grant' and s['state'] == 'connecting'
    assert s['relation_generation'] == rec['registration']['generation']
    assert [t['source'] for t in s['tracks']] == ['camera'] and s['consent_scope']['record'] is False
    assert s['quality_profile']['width'] == 1280 and 'token' not in json.dumps(s['signaling'])
    # 같은 request_id = 같은 세션, 다른 내용 = 충돌
    assert hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'camera', 'target': 'cam-pc', 'request_id': 'r1'}).json()['session']['session_id'] == sid
    assert hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'microphone', 'target': 'cam-pc', 'request_id': 'r1'}).json()['error']['code'] == 'request_id_conflict'
    # 장치가 바쁘면 거절
    assert hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'microphone', 'target': 'cam-pc'}).json()['error']['code'] == 'device_busy'
    # 봉투가 상주 작업으로 접수됐고 grant 가 실려 있다
    task = resident_store.history(device=rec['device_id'])['tasks'][0]
    assert task['summary']['op'] == 'media_session' and task['summary']['grant']['session_id'] == sid
    grant = task['summary']['grant']
    auth = {'key': rec['key'], 'installation_id': rec['registration']['installation_id']}
    # 틀린 grant → 거절, 맞는 grant → ready
    with hub.websocket_connect(f'/limb/resident/media/{sid}') as wrong:
        wrong.send_json({**auth, 'grant': {**grant, 'token': 'x' * 64}})
        err = wrong.receive_json()
        assert err['type'] == 'error' and err['error']['code'] == 'permission_required' and 'token' not in json.dumps(err)
        assert wrong.receive()['type'] == 'websocket.close'
    with hub.websocket_connect(f'/limb/resident/media/{sid}') as dev:
        dev.send_json({**auth, 'grant': grant})
        assert dev.receive_json()['type'] == 'ready'
        with hub.websocket_connect(f'/media/sessions/{sid}/ws', headers={'host': 'localhost'}) as local:
            first = local.receive_json()
            assert first['type'] == 'session' and first['session']['remote_attached'] is True
            # 허브(offerer) → 장치
            local.send_json(sig.new_frame(sid, 'hub', 'device', 'offer', {'sdp': 'v=0\r\na=fingerprint:sha-256 AA'}, generation=0, seq=1))
            msg = dev.receive_json()
            while msg['type'] in ('heartbeat', 'session'):
                msg = dev.receive_json()
            assert msg['type'] == 'offer' and msg['payload']['fingerprint'] == 'sha-256 AA' and sig.verify(msg, ms.get(sid).secret)
            # 장치 → 허브: 지문이 SDP 와 다르면 거절
            dev.send_json(sig.new_frame(sid, 'device', 'hub', 'answer', {'sdp': 'v=0\r\na=fingerprint:sha-256 BB', 'fingerprint': 'sha-256 CC'}, seq=1))
            rej = dev.receive_json()
            while rej['type'] == 'heartbeat':
                rej = dev.receive_json()
            assert rej == {'type': 'rejected', 'reason': 'fingerprint_mismatch', 'msg_id': rej['msg_id']}
            dev.send_json(sig.new_frame(sid, 'device', 'hub', 'answer', {'sdp': 'v=0\r\na=fingerprint:sha-256 BB'}, seq=2))
            got = local.receive_json()
            while got['type'] != 'answer':
                got = local.receive_json()
            # 생존 확인: 순번이 올라야 임대가 갱신된다
            ms.get(sid).lease.rewind(10)
            dev.send_json(sig.new_frame(sid, 'device', 'hub', 'keepalive', {}, seq=3))
            dev.send_json(sig.new_frame(sid, 'device', 'hub', 'state', {'state': 'active', 'path': 'direct', 'quality': {'rtt_ms': 12, 'fps': 15}}, seq=4))
            got = local.receive_json()
            while not (got['type'] == 'session' and got['session']['state'] == 'active'):
                got = local.receive_json()
            assert ms.get(sid).lease.remaining() > 15 and got['session']['path'] == 'direct' and got['session']['quality']['rtt_ms'] == 12
            stale = sig.new_frame(sid, 'device', 'hub', 'keepalive', {}, seq=3)
            dev.send_json(stale)
            rej = dev.receive_json()
            while rej['type'] == 'heartbeat':
                rej = dev.receive_json()
            assert rej['reason'] == 'stale_seq'
            # 종료는 멱등, 장치는 end 를 받고 상주 작업은 취소된다
            assert hub.post(f'/media/sessions/{sid}/end', json={'reason': 'user'}).json()['session']['state'] == 'ended'
            assert hub.post(f'/media/sessions/{sid}/end').json()['success'] is True
            got = dev.receive_json()
            while got['type'] != 'end':
                got = dev.receive_json()
    assert resident_store.history(job=task['id'])['tasks'][0]['state'] in ('cancelled', 'cancel_requested')
    rows = media_store.history()
    assert rows[0]['id'] == sid and rows[0]['end_reason'] == 'user' and rows[0]['path'] == 'direct'
    assert 'token' not in json.dumps(rows) and 'sdp' not in json.dumps(rows)


def test_extension_refusals_and_revocation_hook(hub):
    pc = _device('noeng', caps={})
    assert hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'camera', 'target': 'noeng'}).json()['error']['code'] == 'unsupported_track'
    rec = _device('cam2')
    limb_keys.resident_update(rec['device_id'], last_seen=time.time() - 300)
    assert hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'camera', 'target': 'cam2'}).json()['error']['code'] == 'device_offline'
    limb_keys.resident_update(rec['device_id'], last_seen=time.time())
    sid = hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'microphone', 'target': 'cam2'}).json()['session']['session_id']
    # 에이전트 명령 경로로는 grant 봉투를 보낼 수 없다
    with pytest.raises(ValueError, match='unsupported_resident_operation'):
        pcs.submit('cam2', {'op': 'media_session', 'session_id': sid})
    # 관계 중지 → 세션 종료 + 사유
    hub.post('/remote-pcs/state', json={'target': 'cam2', 'paused': True})
    s = ms.status(sid)
    assert s['state'] == 'ended' and s['error']['code'] == 'relation_revoked'
    # 통화 자격(kind=call)으로 확장관계 등록·명령은 불가능 — 미디어 API 에 등록 기능이 없다
    assert hub.post('/limb/resident/enroll', json={'key': 'nope', 'installation_id': 'a' * 32}).status_code == 400
    assert pc


def test_phone_body_gets_media_envelope_only_through_media_adapter(hub):
    phone = _device('삼성1', kind='phone', adapter='indiebiz-v1')
    s = hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'camera', 'target': '삼성1', 'want_mic': True}).json()['session']
    assert s['quality_profile']['width'] == 640, '32비트 폰 프로필'
    assert [t['source'] for t in s['tracks']] == ['camera', 'mic']
    task = resident_store.history(device=phone['device_id'])['tasks'][0]
    assert task['summary']['op'] == 'media' and task['summary']['action'] == 'start'
    assert task['summary']['session']['grant']['role'] == 'device'
    with pytest.raises(ValueError, match='unsupported_on_this_body'):
        pcs.submit('삼성1', {'op': 'media', 'action': 'stop'})


def test_playback_content_delivery_with_range_and_token(hub, tmp_path):
    rec = _device('spk')
    media = tmp_path / 'song.mp3'
    media.write_bytes(b'0123456789' * 100)
    s = hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'playback', 'delivery': 'content', 'target': 'spk',
                                          'content': {'path': str(media), 'position_s': 12.5}}).json()['session']
    assert s['content']['volume_explicit'] is False
    assert s['content']['kind'] == 'file' and s['content']['position_s'] == 12.5 and s['content']['name'] == 'song.mp3'
    assert '/media/content/' in s['content']['url'] and str(media) not in json.dumps(s), '전체 경로는 노출하지 않는다'
    url = s['content']['url'][s['content']['url'].index('/media/content/'):]
    r = hub.get(url, headers={'Range': 'bytes=10-19'})
    assert r.status_code == 206 and r.content == b'0123456789' and r.headers['Content-Range'] == 'bytes 10-19/1000'
    assert hub.get(url.split('?')[0] + '?token=bad').status_code == 403
    # 대상의 재생 보고 → 세션 content 상태, 허브의 update → 장치에 update 프레임
    task = resident_store.history(device=rec['device_id'])['tasks'][0]
    auth = {'key': rec['key'], 'installation_id': rec['registration']['installation_id'], 'grant': task['summary']['grant']}
    with hub.websocket_connect(f"/limb/resident/media/{s['session_id']}") as dev:
        dev.send_json(auth)
        assert dev.receive_json()['type'] == 'ready'
        dev.send_json(sig.new_frame(s['session_id'], 'device', 'hub', 'state', {'state': 'active', 'content': {'playing': True, 'position_s': 13.0}}, seq=1))
        for _ in range(20):
            st = ms.status(s['session_id'])
            if st['state'] == 'active':
                break
            time.sleep(0.05)
        assert st['content']['playing'] is True and st['content']['position_s'] == 13.0
        r = hub.post(f"/media/sessions/{s['session_id']}/update", json={'expected_revision': st['revision'] - 1, 'changes': {'content': {'paused': True}}})
        assert r.json()['error']['code'] == 'stale_revision'
        r = hub.post(f"/media/sessions/{s['session_id']}/update", json={'expected_revision': st['revision'], 'changes': {'content': {'paused': True, 'volume': 40}}})
        assert r.json()['session']['content']['paused'] is True
        got = dev.receive_json()
        while got['type'] != 'update':
            got = dev.receive_json()
        assert got['payload']['content'] == {'paused': True, 'volume': 40}
    hub.post(f"/media/sessions/{s['session_id']}/end")
    assert hub.get(url).status_code == 403, '종료된 세션의 콘텐츠 참조는 무효'


# ── 일반 통화 ────────────────────────────────────────────────────────────────────
PEER = 'a' * 64


def test_call_invite_bundles_offer_and_accept_moves_to_connecting(hub):
    r = hub.post('/media/sessions', json={'kind': 'call', 'purpose': 'video_call', 'target': PEER, 'request_id': 'c1'}).json()
    s = r['session']
    sid = s['session_id']
    assert s['authorization_basis'] == 'accepted_call' and s['state'] == 'inviting' and s['local_role'] == 'caller'
    assert s['signaling']['route'] == 'nostr' and s['expires_at'] > time.time()
    # 브라우저가 곧바로 offer 를 주면 초대에 동봉된다
    with hub.websocket_connect(f'/media/sessions/{sid}/ws', headers={'host': 'localhost'}) as local:
        local.receive_json()
        local.send_json(sig.new_frame(sid, 'caller', 'callee', 'offer', {'sdp': 'v=0\r\na=fingerprint:sha-256 AA'}, seq=1))
        for _ in range(40):
            if hub.sent:
                break
            time.sleep(0.05)
    to, frame, tags = hub.sent[0]
    assert to == PEER and tags == [['indiebiz-call', '1']] and frame['type'] == 'invite'
    assert frame['payload']['offer']['fingerprint'] == 'sha-256 AA' and sig.verify(frame, ms.get(sid).secret)
    assert frame['payload']['secret'] == ms.get(sid).secret
    # 상대의 수락(+answer) → connecting, answer 는 로컬 엔진으로
    accept = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'accept', {'device': {'id': 'peer-dev'}, 'answer': {'sdp': 'v=0\r\na=fingerprint:sha-256 BB'}}), ms.get(sid).secret)
    assert ms.receive_remote(accept, source='nostr', sender_hex=PEER) is None
    st = ms.status(sid)
    assert st['state'] == 'connecting' and st['expires_at'] is None
    assert [m['type'] for m in ms.get(sid).local_box.take() if m.get('type') == 'answer'] == ['answer']
    # 엉뚱한 발신자·서명 위조·종료 뒤 늦은 프레임
    bad = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'keepalive', {}, seq=5), 'cd' * 32)
    assert ms.receive_remote(bad, source='nostr', sender_hex=PEER) == 'bad_signature'
    ok = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'keepalive', {}, seq=5), ms.get(sid).secret)
    assert ms.receive_remote(ok, source='nostr', sender_hex='b' * 64) == 'wrong_sender'
    hub.post(f'/media/sessions/{sid}/end', json={'reason': 'local_hangup'})
    assert hub.sent[-1][1]['type'] == 'end' and hub.sent[-1][1]['payload']['reason'] == 'local_hangup'
    late = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'candidate', {'candidate': 'x'}, seq=6), ms.get(sid).secret)
    assert ms.receive_remote(late, source='nostr', sender_hex=PEER) == 'session_ended'
    assert hub.sent[-1][1]['type'] == 'end', '늦은 프레임에는 종료됨으로 답한다'


def test_callee_ringing_accept_reject_and_block(hub):
    secret = 'ee' * 32
    sid = uuid.uuid4().hex
    invite = sig.sign(sig.new_frame(sid, 'caller', 'callee', 'invite', {
        'purpose': 'voice_call', 'secret': secret, 'expires_at': time.time() + 30, 'from_user': {'name': '친구'},
        'from_device': {'id': 'd1'}, 'offer': {'sdp': 'v=0\r\na=fingerprint:sha-256 AA'}, 'ice_servers': []}), secret)
    assert ms.receive_remote(invite, source='relay') == 'invite_only_via_nostr'
    assert ms.receive_remote(invite, source='nostr', sender_hex=PEER) is None
    s = ms.status(sid)
    assert s['state'] == 'ringing' and s['local_role'] == 'callee' and s['pending_offer']['fingerprint'] == 'sha-256 AA'
    assert s['participants'][0]['user']['id'] == PEER
    # 수락 전엔 센서 없음(계약) — 수락 뒤 브라우저 answer 가 accept 에 동봉된다
    assert hub.post(f'/media/sessions/{sid}/accept').json()['session']['state'] == 'accepted'
    assert hub.post(f'/media/sessions/{sid}/accept').json()['error']['code'] == 'invalid_state', '두 번째 수락은 거절'
    with hub.websocket_connect(f'/media/sessions/{sid}/ws', headers={'host': 'localhost'}) as local:
        local.receive_json()
        local.send_json(sig.new_frame(sid, 'callee', 'caller', 'answer', {'sdp': 'v=0\r\na=fingerprint:sha-256 BB'}, seq=1))
        for _ in range(40):
            if hub.sent:
                break
            time.sleep(0.05)
    to, frame, _ = hub.sent[0]
    assert to == PEER and frame['type'] == 'accept' and frame['payload']['answer']['fingerprint'] == 'sha-256 BB'
    assert ms.status(sid)['state'] == 'connecting'
    # 두 번째 초대: 거절 + 차단 → 이후 초대는 무시
    sid2 = uuid.uuid4().hex
    inv2 = sig.sign(sig.new_frame(sid2, 'caller', 'callee', 'invite', {'purpose': 'voice_call', 'secret': secret, 'expires_at': time.time() + 30}), secret)
    ms.receive_remote(inv2, source='nostr', sender_hex=PEER)
    assert hub.post(f'/media/sessions/{sid2}/reject', json={'reason': 'busy', 'block': True}).json()['session']['end_reason'] == 'busy'
    assert hub.sent[-1][1]['type'] == 'reject'
    sid3 = uuid.uuid4().hex
    inv3 = sig.sign(sig.new_frame(sid3, 'caller', 'callee', 'invite', {'purpose': 'voice_call', 'secret': secret, 'expires_at': time.time() + 30}), secret)
    ms.receive_remote(inv3, source='nostr', sender_hex=PEER)
    assert sid3 not in ms._sessions, '차단한 상대의 초대는 세션을 만들지 않는다'
    media_store.unblock(PEER)
    # 만료된 초대는 버린다
    old = sig.sign(sig.new_frame(uuid.uuid4().hex, 'caller', 'callee', 'invite', {'purpose': 'voice_call', 'secret': secret, 'expires_at': time.time() - 500}, ttl_s=-1), secret)
    assert ms.receive_remote(old, source='nostr', sender_hex=PEER) is None and len(ms._sessions) == 2


def test_sweep_expires_invites_and_leases(hub):
    sid = hub.post('/media/sessions', json={'kind': 'call', 'purpose': 'voice_call', 'target': PEER}).json()['session']['session_id']
    ms.get(sid).expires_at = time.time() - 1
    assert ms.sweep() == 1 and ms.status(sid)['end_reason'] == 'invite_expired'
    rec = _device('lease-pc')
    sid2 = hub.post('/media/sessions', json={'kind': 'extension', 'purpose': 'camera', 'target': 'lease-pc'}).json()['session']['session_id']
    ms.get(sid2).lease.rewind(100)
    assert ms.sweep() == 1
    st = ms.status(sid2)
    assert st['state'] == 'ended' and st['error']['code'] == 'connectivity_failed'
    assert rec


def test_relay_room_token_and_forwarding(hub):
    secret = '11' * 32
    token = ms.rooms.open('room1', secret)
    with pytest.raises(Exception):
        with hub.websocket_connect('/media/relay/room1?token=bad') as bad:
            bad.receive_json()
    with hub.websocket_connect('/media/relay/room1?token=' + token) as a, hub.websocket_connect('/media/relay/room1?token=' + token) as b:
        frame = sig.sign(sig.new_frame('2' * 32, 'caller', 'callee', 'candidate', {'candidate': 'c'}, seq=1), secret)
        a.send_json(frame)
        got = b.receive_json()
        while got['type'] == 'heartbeat':
            got = b.receive_json()
        assert got == frame, '릴레이는 내용을 바꾸지 않는다'
    ms.rooms.close('room1')
    assert ms.rooms.members('room1') == []


def test_health_and_capabilities_report_honestly(hub):
    h = hub.get('/media/health').json()['health']
    assert h['turn']['configured'] is False and h['turn']['reason'] == 'turn_unconfigured'
    assert h['signaling']['nostr'] is True
    c = hub.get('/media/capabilities').json()['capabilities']
    assert c['call'] is True and c['turn'] is False
    _device('capdev', caps={'camera': False, 'speaker': True})
    d = hub.get('/media/capabilities', params={'target': 'capdev'}).json()['capabilities']
    assert d['online'] and d['media_session'] == {'camera': False, 'speaker': True}
    assert hub.get('/media/capabilities', params={'target': 'nobody'}).json()['error']['code'] == 'device_not_found'



def test_realtime_playback_requires_display_and_device_acknowledgement(hub):
    _device('old-phone', kind='phone', adapter='indiebiz-v1')
    body = {'kind': 'extension', 'purpose': 'playback', 'delivery': 'realtime', 'target': 'old-phone'}
    assert hub.post('/media/sessions', json=body).json()['error']['code'] == 'unsupported_track'
    rec = _device('display-phone', kind='phone', adapter='indiebiz-v1',
                  caps={'playback': True, 'video_receive': True})
    body['target'] = 'display-phone'
    result = hub.post('/media/sessions', json=body).json()
    assert result['success'], result
    sid = result['session']['session_id']
    session = ms._sessions[sid]
    assert {t['kind'] for t in session.tracks} == {'video', 'audio'}
    assert all(t['from'] == 'hub' and t['to'] == 'device' and t['source'] == 'playback' for t in session.tracks)
    frame = sig.new_frame(sid, 'device', 'hub', 'state', {
        'state': 'needs_local_action', 'needs_local_action': {'code': 'display_required', 'message': '폰에서 미디어 화면을 열어 주세요'}}, seq=1)
    assert ms.receive_remote(frame, source='device', device_session=sid, device_id=rec['device_id']) is None
    assert ms.status(sid)['needs_local_action']['code'] == 'display_required'
    assert ms.signal(sid, sig.new_frame(sid, 'hub', 'device', 'state', {'state': 'active'}, seq=1)) is None
    assert ms.status(sid)['state'] == 'needs_local_action', 'sender bytes must not claim remote rendering'
    frame = sig.new_frame(sid, 'device', 'hub', 'state', {'state': 'active'}, seq=2)
    assert ms.receive_remote(frame, source='device', device_session=sid, device_id=rec['device_id']) is None
    assert ms.status(sid)['state'] == 'active'
    ms.end(sid, 'done')
    body['tracks'] = [{'id': 'bad', 'kind': 'video', 'source': 'camera', 'from': 'device', 'to': 'hub'}]
    assert hub.post('/media/sessions', json=body).json()['error']['code'] == 'unsupported_track'


def test_content_display_status_survives_contract(hub, tmp_path):
    _device('video-phone')
    video = tmp_path / 'movie.mp4'
    video.write_bytes(b'fake-content')
    sid = ms.create('extension', 'playback', 'video-phone', delivery='content', content={'path': str(video)})['session_id']
    ms._apply_state_report(ms._sessions[sid], {'state': 'needs_local_action', 'content': {
        'playing': False, 'has_video': True, 'needs_display': True, 'video_visible': False}})
    assert ms.status(sid)['content']['needs_display'] is True
    ms._apply_state_report(ms._sessions[sid], {'state': 'active', 'content': {
        'playing': True, 'video_visible': True, 'needs_display': False}})
    assert ms.status(sid)['content']['video_visible'] is True

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_device_websocket_is_bound_to_its_authenticated_session(hub):
    one, two = _device(alias='one'), _device(alias='two')
    sid = ms.create('extension', 'camera', 'one')['session_id']
    other = ms.create('extension', 'camera', 'two')['session_id']
    with hub.websocket_connect(f'/limb/resident/media/{sid}') as dev:
        dev.send_json({'key': one['key'], 'installation_id': one['registration']['installation_id'],
                       'grant': ms.get(sid).grants['device']})
        assert dev.receive_json()['type'] == 'ready'
        dev.send_json(sig.new_frame(other, 'device', 'hub', 'end', {}, seq=1))
        assert dev.receive_json()['reason'] == 'wrong_session'
        assert ms.status(other)['state'] == 'connecting'
        dev.send_json(sig.new_frame(sid, 'callee', 'caller', 'end', {}, seq=2))
        assert dev.receive_json()['reason'] == 'wrong_role'
        assert ms.status(sid)['state'] == 'connecting'
    assert ms.receive_remote(sig.new_frame(other, 'device', 'hub', 'end', {}), source='device') == 'wrong_session'


def test_media_events_work_without_a_chat_socket(hub):
    _device()
    with hub.websocket_connect('/media/events', headers={'host': 'localhost'}) as events:
        s = ms.create('extension', 'camera', 'cam-pc')
        frame = events.receive_json()
        assert frame['type'] == 'media_event' and frame['session']['session_id'] == s['session_id']
        ms.end(s['session_id'])
        while frame.get('session', {}).get('state') != 'ended':
            frame = events.receive_json()
        assert frame['event'] == 'ended'


def test_phone_identity_and_public_role_do_not_need_pynostr(hub, monkeypatch):
    import sys
    from types import SimpleNamespace
    import indienet
    monkeypatch.setattr(indienet, 'get_indienet', lambda: SimpleNamespace(
        identity=SimpleNamespace(public_key_hex='a' * 64, public_key=None)))
    assert sig.NostrTransport().my_pubkey_hex() == 'a' * 64
    # npub decoding must remain independent of the desktop-only crypto dependency.
    from pynostr import bech32
    monkeypatch.setitem(sys.modules, "bech32", bech32)
    npub = bech32.bech32_encode('npub', bech32.convertbits(bytes.fromhex('b' * 64), 8, 5), bech32.Encoding.BECH32)
    monkeypatch.setitem(sys.modules, 'nip17', None)
    assert ms.resolve_contact(npub) == 'b' * 64


def test_hub_keepalive_and_controls_follow_engine_signals(hub):
    rec = _device()
    sid = ms.create('extension', 'camera', 'cam-pc')['session_id']
    s = ms.attach_device(sid, rec['device_id'], ms.get(sid).grants['device'])
    assert ms.signal(sid, sig.new_frame(sid, 'hub', 'device', 'offer', {'sdp': 'v=0'}, seq=20)) is None
    first = s.remote_box.take()[-1]
    ms.sweep()
    alive = s.remote_box.take()[-1]
    assert alive['type'] == 'keepalive' and alive['seq'] > first['seq']
    ms.update(sid, s.revision, {'mute': True})
    update = s.remote_box.take()[-1]
    assert update['seq'] > alive['seq']
    ms.end(sid)
    assert s.remote_box.take()[-1]['seq'] > update['seq']


def test_ice_restart_refreshes_credentials_and_forwards_them(hub, monkeypatch):
    _device()
    sid = ms.create('extension', 'camera', 'cam-pc')['session_id']
    fresh = [{'urls': ['turn:relay.example:3478'], 'username': 'later:session', 'credential': 'new'}]
    monkeypatch.setattr(sig, 'turn_configured', lambda: (True, 'ok'))
    monkeypatch.setattr(sig, 'ice_servers', lambda session_id='': fresh)
    assert hub.get('/media/ice-config', params={'session_id': sid}).json()['ice_servers'] == fresh
    assert ms.signal(sid, sig.new_frame(sid, 'hub', 'device', 'offer', {'sdp': 'v=0'}, generation=1, seq=1)) is None
    frame = ms.get(sid).remote_box.take()[-1]
    assert frame['payload']['ice_servers'] == fresh and sig.verify(frame, ms.get(sid).secret)


def test_speaker_microphone_source_needs_no_remote_camera(hub):
    _device('speaker-only', caps={'speaker': True})
    session = ms.create('extension', 'speaker', 'speaker-only')
    sid = session['session_id']
    changed = ms.update(sid, session['revision'], {'audio_source': 'mic'})
    assert changed['tracks'] == [dict(session['tracks'][0], source='mic')]
    assert changed['consent_scope'] == {'inputs': ['mic'], 'outputs': [], 'record': False}
    with pytest.raises(ms.MediaError, match='invalid_changes'):
        ms.update(sid, changed['revision'], {'audio_source': 'camera'})
    restored = ms.update(sid, changed['revision'], {'audio_source': 'playback'})
    assert restored['consent_scope']['inputs'] == []
    ms.end(sid)
    with pytest.raises(ms.MediaError, match='session_ended'):
        ms.update(sid, ms.get(sid).revision, {'audio_source': 'mic'})


def test_audio_source_update_cannot_change_other_session_purposes(hub):
    _device()
    session = ms.create('extension', 'microphone', 'cam-pc')
    with pytest.raises(ms.MediaError, match='invalid_changes'):
        ms.update(session['session_id'], session['revision'], {'audio_source': 'mic'})


def test_explicit_initial_volume_is_distinct_from_default(hub, tmp_path):
    _device('initial-volume')
    media = tmp_path / 'audio.mp3'
    media.write_bytes(b'audio')
    response = hub.post('/media/sessions', json={
        'kind': 'extension', 'purpose': 'playback', 'delivery': 'content', 'target': 'initial-volume',
        'content': {'path': str(media), 'volume': 0}})
    session = response.json()['session']
    assert session['content']['volume_explicit'] is True
    assert session['content']['volume'] == 0
    hub.post(f"/media/sessions/{session['session_id']}/end")


def test_sweeper_lifetime_does_not_hold_the_starting_request(monkeypatch):
    import threading
    from types import SimpleNamespace
    import runtime_work as rw

    reg = rw.WorkRegistry("media-service-test")
    reg.gate("ACTIVE")
    monkeypatch.setattr(rw, "_registry", reg)
    rw.install_worker_tracking()
    stop = threading.Event()
    thread_class = threading.Thread
    # 실 스레드 추적 경계를 쓰되 미디어 효과 없는 유한 대기로 바꾼다.
    monkeypatch.setattr(ms, "threading", SimpleNamespace(Thread=lambda **kw: thread_class(
        target=lambda: stop.wait(3), name=kw["name"], daemon=True)))
    monkeypatch.setattr(ms, "_sweeper", None)
    monkeypatch.delenv("INDIEBIZ_MEDIA_NO_SWEEPER", raising=False)
    try:
        with rw.scope("media-request"):
            ms._ensure_sweeper()
        assert ms._sweeper.is_alive()
        assert reg.snapshot()["owners"] == []
        reg.gate("DRAINING")
        assert reg.snapshot()["active_children"] == 0
    finally:
        stop.set()
        if ms._sweeper is not None:
            ms._sweeper.join(3)


def test_each_sweep_is_tracked_and_new_sweeps_defer_during_drain(monkeypatch):
    import runtime_work as rw

    reg = rw.WorkRegistry("media-sweep-test")
    reg.gate("ACTIVE")
    monkeypatch.setattr(rw, "_registry", reg)
    monkeypatch.setattr(ms, "_sessions", {})
    monkeypatch.setattr(ms, "_requests", {})
    seen = []

    def profile(_):
        seen.append(reg.snapshot())
        return {}

    monkeypatch.setattr(ms.session_lease, "profile", profile)
    assert ms.sweep(now=1) == 0
    assert seen[0]["active_roots"] == 1
    assert seen[0]["owners"][0]["label"] == "media-sweep"
    assert reg.snapshot()["owners"] == []
    observations = len(seen)
    reg.gate("DRAINING")
    assert ms.sweep(now=2) is None
    assert len(seen) == observations and reg.snapshot()["owners"] == []
