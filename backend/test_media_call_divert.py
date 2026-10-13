"""통화 제어 DM 은 채팅·트리거·자동응답으로 가지 않는다 (docs/MEDIA_COMMUNICATION_DESIGN §5·§8, 계약 §5 nostr)."""
import boot_paths  # noqa: F401
import json
import time

import pytest

import channel_poller
import indienet_social
import media_sessions as ms
import media_signaling as sig
import nip17


@pytest.fixture
def poller(monkeypatch, tmp_path):
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('INDIEBIZ_MEDIA_NO_SWEEPER', '1')
    monkeypatch.setattr(channel_poller, '_load_owner_identities', lambda: {})
    p = channel_poller.ChannelPoller(log_callback=lambda *_: None)
    p._nostr_private_key = b'\x01' * 32
    p._nostr_listen_started = time.time() - 10
    saved = []
    monkeypatch.setattr(p, '_save_message_to_db', lambda **kw: saved.append(kw))
    monkeypatch.setattr(p, '_update_last_poll_time', lambda *a: None)
    ms.reset_for_tests()
    yield p, saved
    ms.reset_for_tests()


def _unwrapped(content, tags, sender='a' * 64):
    return {'sender': sender, 'content': content, 'created_at': int(time.time()),
            'rumor': {'id': 'r1', 'tags': tags}}


def test_call_frame_goes_to_media_sessions_not_chat(poller, monkeypatch):
    p, saved = poller
    secret = 'ab' * 32
    sid = '3' * 32
    frame = sig.sign(sig.new_frame(sid, 'caller', 'callee', 'invite', {'purpose': 'voice_call', 'secret': secret,
                                                                      'expires_at': time.time() + 30}), secret)
    content = json.dumps(frame)
    monkeypatch.setattr(nip17, 'unwrap_dm', lambda priv, ev: _unwrapped(content, [['indiebiz', '1'], ['indiebiz-call', '1']]))
    received = []
    monkeypatch.setattr(ms, 'receive_remote', lambda f, source, sender_hex=None: received.append((f['type'], source, sender_hex)) or None)
    p._handle_nostr_giftwrap({'id': 'ev1', 'kind': 1059})
    assert received == [('invite', 'nostr', 'a' * 64)]
    assert saved == [], '통화 제어 프레임은 business.db(자동응답 입력)에 들어가면 안 된다'
    # 태그가 유실돼도(폰 브리지 경로) 모양으로 가른다
    monkeypatch.setattr(nip17, 'unwrap_dm', lambda priv, ev: _unwrapped(content, [['indiebiz', '1']]))
    p._handle_nostr_giftwrap({'id': 'ev2', 'kind': 1059})
    assert len(received) == 2 and saved == []
    # 보통 DM 은 그대로 채팅으로
    monkeypatch.setattr(nip17, 'unwrap_dm', lambda priv, ev: _unwrapped('안녕하세요 {"session_id": "x"}', [['indiebiz', '1']]))
    p._handle_nostr_giftwrap({'id': 'ev3', 'kind': 1059})
    assert len(saved) == 1 and saved[0]['content'].startswith('안녕')
    assert len(received) == 2


def test_inbox_filter_drops_call_frames():
    frame = sig.new_frame('4' * 32, 'callee', 'caller', 'end', {'reason': 'x'})
    assert indienet_social._is_call_control(json.dumps(frame), []) is True
    assert indienet_social._is_call_control('점심 먹었어?', [['indiebiz', '1']]) is False
    assert indienet_social._is_call_control('본문', [['indiebiz-call', '1']]) is True


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
