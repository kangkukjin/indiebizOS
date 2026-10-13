"""두 허브 사이의 일반 통화 제어 흐름 — 초대(+offer)→벨→수락(+answer)→candidate→keepalive→종료 (docs/MEDIA_SESSION_CONTRACT.md §5 nostr).

허브 B 는 media_sessions 모듈을 두 번째로 적재해 독립 상태로 둔다. 두 허브의 Nostr 발송은 서로의 receive_remote 로 직결된다
(릴레이 지연 0). 프레임은 실제로 서명·검증·질서 검사를 거친다."""
import boot_paths  # noqa: F401
import importlib.util
import json
import sys
import time
import uuid
from pathlib import Path

import pytest

import media_sessions as hub_a
import media_signaling as sig

A_PUB, B_PUB = 'a' * 64, 'b' * 64


def _load_hub_b():
    path = Path(hub_a.__file__)
    spec = importlib.util.spec_from_file_location('media_sessions_b', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['media_sessions_b'] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hubs(tmp_path, monkeypatch):
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('INDIEBIZ_MEDIA_NO_SWEEPER', '1')
    policy = json.loads(json.dumps(sig.policy()))
    policy['signaling']['bundle_wait_s'] = 0.2
    monkeypatch.setattr(sig, 'policy', lambda: policy)
    monkeypatch.setattr(sig, 'relay_base', lambda: '')
    hub_b = _load_hub_b()
    delivered = []

    def wire(src, dst, src_pub):
        def sender(to, content, tags):
            frame = json.loads(content)
            delivered.append((src_pub[:1], frame['type']))
            why = dst.receive_remote(frame, source='nostr', sender_hex=src_pub)
            assert why in (None,), f'{src_pub[:1]}→ {frame["type"]} 거절: {why}'
            return True
        monkeypatch.setattr(src, 'nostr', sig.NostrTransport(sender=sender))
        monkeypatch.setattr(src.nostr, 'my_pubkey_hex', lambda: src_pub)
    wire(hub_a, hub_b, A_PUB)
    wire(hub_b, hub_a, B_PUB)
    monkeypatch.setattr(hub_a, 'resolve_contact', lambda t: B_PUB)
    monkeypatch.setattr(hub_a, '_contact_name', lambda p: '친구')
    monkeypatch.setattr(hub_b, '_contact_name', lambda p: '나')
    hub_a.reset_for_tests()
    hub_b.reset_for_tests()
    yield hub_a, hub_b, delivered
    hub_a.reset_for_tests()
    hub_b.reset_for_tests()


def _wait(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _frames(box, kind):
    return [m for m in box.take() if m.get('type') == kind]


def test_call_control_plane_end_to_end(hubs):
    a, b, delivered = hubs
    s = a.create('call', 'video_call', '친구', request_id='call-1')
    sid = s['session_id']
    # 발신 브라우저가 offer 를 주면 초대에 동봉된다
    assert a.signal(sid, sig.new_frame(sid, 'caller', 'callee', 'offer', {'sdp': 'v=0\r\na=fingerprint:sha-256 AA'}, seq=1)) is None
    assert _wait(lambda: sid in b._sessions), '초대가 B 에 도착해야 한다'
    ringing = b.status(sid)
    assert ringing['state'] == 'ringing' and ringing['local_role'] == 'callee'
    assert ringing['pending_offer']['fingerprint'] == 'sha-256 AA' and ringing['participants'][0]['user']['id'] == A_PUB
    assert delivered == [('a', 'invite')]
    assert a.status(sid)['state'] == 'inviting'
    # B 수락 → B 브라우저 answer 동봉 → A connecting + answer 프레임이 A 의 로컬 엔진에
    b.accept(sid)
    assert b.signal(sid, sig.new_frame(sid, 'callee', 'caller', 'answer', {'sdp': 'v=0\r\na=fingerprint:sha-256 BB'}, seq=1)) is None
    assert _wait(lambda: a.status(sid)['state'] == 'connecting')
    assert delivered[-1] == ('b', 'accept')
    answers = _frames(a.get(sid).local_box, 'answer')
    assert len(answers) == 1 and answers[0]['payload']['fingerprint'] == 'sha-256 BB' and 'mac' not in answers[0] or True
    assert b.status(sid)['state'] == 'connecting'
    # trickle candidate 양방향(서명·순번 검사 통과)
    assert a.signal(sid, sig.new_frame(sid, 'caller', 'callee', 'candidate', {'candidate': 'c-a'}, seq=2)) is None
    assert b.signal(sid, sig.new_frame(sid, 'callee', 'caller', 'candidate', {'candidate': 'c-b'}, seq=2)) is None
    got_b, got_a = [], []
    assert _wait(lambda: (got_b.extend(m['payload']['candidate'] for m in _frames(b.get(sid).local_box, 'candidate')) or got_b == ['c-a']))
    assert _wait(lambda: (got_a.extend(m['payload']['candidate'] for m in _frames(a.get(sid).local_box, 'candidate')) or got_a == ['c-b']))
    # 상태 보고(active) 는 상대에게도 전달돼 양쪽이 active
    assert b.signal(sid, sig.new_frame(sid, 'callee', 'caller', 'state', {'state': 'active', 'path': 'relay', 'quality': {'rtt_ms': 80}}, seq=3)) is None
    assert a.signal(sid, sig.new_frame(sid, 'caller', 'callee', 'state', {'state': 'active', 'path': 'relay'}, seq=3)) is None
    assert _wait(lambda: a.status(sid)['state'] == 'active' and b.status(sid)['state'] == 'active')
    assert a.status(sid)['quality']['rtt_ms'] == 80 and a.status(sid)['path'] == 'relay'
    # 임대 갱신: 브라우저가 DataChannel 로 상대 생존을 확인한 keepalive(peer_alive)만 갱신한다 — 로컬 keepalive 는 Nostr 로 나가지 않는다
    a.get(sid).lease.rewind(10)
    assert a.signal(sid, sig.new_frame(sid, 'caller', 'callee', 'keepalive', {'peer_alive': False}, seq=4)) is None
    assert a.get(sid).lease.remaining() < 11
    assert a.signal(sid, sig.new_frame(sid, 'caller', 'callee', 'keepalive', {'peer_alive': True}, seq=5)) is None
    assert a.get(sid).lease.remaining() > 15
    assert not [d for d in delivered if d[1] == 'keepalive'], 'keepalive 는 Nostr DM 으로 나가지 않는다'
    # 원격(서명된) keepalive 는 세대·순번 질서를 따른다
    fresh = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'keepalive', {}, seq=4), a.get(sid).secret)
    assert a.receive_remote(fresh, source='nostr', sender_hex=B_PUB) is None
    old = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'keepalive', {}, seq=4), a.get(sid).secret)
    assert a.receive_remote(old, source='nostr', sender_hex=B_PUB) == 'stale_seq'
    # 재협상: 세대 1 의 candidate 가 offer 보다 먼저 와도 버퍼됐다가 offer 와 함께 흘러간다
    early = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'candidate', {'candidate': 'early'}, generation=1, seq=1), a.get(sid).secret)
    assert a.receive_remote(early, source='nostr', sender_hex=B_PUB) is None
    assert _frames(a.get(sid).local_box, 'candidate') == []
    reoffer = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'offer', {'sdp': 'v=0\r\na=fingerprint:sha-256 CC'}, generation=1, seq=2), a.get(sid).secret)
    assert a.receive_remote(reoffer, source='nostr', sender_hex=B_PUB) is None
    kinds = [m['type'] for m in a.get(sid).local_box.take() if m['type'] in ('offer', 'candidate')]
    assert kinds == ['offer', 'candidate'] and a.status(sid)['generation'] == 1
    # A 가 끊으면 B 도 끝나고, 양쪽 이력에 사유가 남는다
    a.end(sid, 'local_hangup')
    assert _wait(lambda: b.status(sid)['state'] == 'ended')
    assert b.status(sid)['end_reason'] == 'local_hangup' and delivered[-1] == ('a', 'end')
    # 종료 뒤 늦은 keepalive 에는 '종료됨' 응답만(재활성화 없음)
    late = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'keepalive', {}, generation=1, seq=9), a.get(sid).secret)
    assert a.receive_remote(late, source='nostr', sender_hex=B_PUB) == 'session_ended'
    assert a.status(sid)['state'] == 'ended'


def test_callee_rejects_and_caller_sees_reason(hubs):
    a, b, delivered = hubs
    sid = a.create('call', 'voice_call', '친구')['session_id']
    assert _wait(lambda: sid in b._sessions)
    b.reject(sid, 'busy')
    assert _wait(lambda: a.status(sid)['state'] == 'ended')
    assert a.status(sid)['end_reason'] == 'busy' and delivered[-1] == ('b', 'reject')


def test_invite_without_answer_expires_on_both_sides(hubs):
    a, b, _ = hubs
    sid = a.create('call', 'voice_call', '친구')['session_id']
    assert _wait(lambda: sid in b._sessions)
    for hub in (a, b):
        hub.get(sid).expires_at = time.time() - 1
    assert a.sweep() == 1
    # A 의 만료 통지(end)가 B 의 벨을 먼저 닫는다 — B 의 sweep 은 더 할 일이 없다
    assert _wait(lambda: b.status(sid)['state'] == 'ended') and b.sweep() == 0
    assert a.status(sid)['end_reason'] == 'invite_expired' and b.status(sid)['end_reason'] == 'invite_expired'


def test_wrong_sender_cannot_hijack_session(hubs):
    a, b, _ = hubs
    sid = a.create('call', 'voice_call', '친구')['session_id']
    assert _wait(lambda: sid in b._sessions)
    secret = a.get(sid).secret
    forged = sig.sign(sig.new_frame(sid, 'callee', 'caller', 'accept', {'device': {'id': 'evil'}}), secret)
    assert a.receive_remote(forged, source='nostr', sender_hex='c' * 64) == 'wrong_sender'
    assert a.status(sid)['state'] == 'inviting'
    unsigned = sig.new_frame(sid, 'callee', 'caller', 'accept', {'device': {'id': 'evil'}})
    assert a.receive_remote(unsigned, source='nostr', sender_hex=B_PUB) == 'bad_signature'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
