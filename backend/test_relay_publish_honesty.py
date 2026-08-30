"""릴레이 발행 정직성 회귀 — **거부는 성공이 아니고, 간헐 장애는 실패가 아니다** (2026-08-30).

재현하는 결함(실측): 원격런처 메신저에서 메시지 발송이 실패했다. 추적해 보니 몸 안쪽에
세 자리가 함께 있었다.

  ① `_publish_event` 가 릴레이의 OK 프레임만 세고 수락 플래그를 안 봤다. NIP-01 의 OK 는
     ["OK", <id>, <수락여부>, <사유>] — 세 번째 칸이 false 면 **거부**(rate-limited·blocked)다.
     거부를 성공으로 세면 "발송 완료"라고 거짓 보고한다.
  ② 5초 창 한 번에 OK 가 0개면 곧장 실패. 공개 릴레이의 간헐 503(실측: relay.damus.io
     Cloudflare 503 이 3회 중 2회)이 그대로 사용자 눈의 '발송 실패'가 됐다.
  ③ 실패한 발신이 정본(business.db)에 한 줄도 안 남아 내가 친 말이 통째로 증발했다.

여기서는 ①②를 잰다(③은 create_message(status="failed") 인자 통과로 확인).

실행: .venv/bin/python -m pytest backend/test_relay_publish_honesty.py
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

import pytest

from indienet_relay import IndieNetRelayMixin
import indienet_social as social

EVENT = {"id": "ab" * 32, "kind": 1059, "content": "x", "tags": [],
         "pubkey": "cd" * 32, "sig": "ef" * 64, "created_at": 1}


class _Publisher(IndieNetRelayMixin):
    class _S:
        relays = []
    settings = _S()


def _relay(behavior):
    """로컬 모의 릴레이 — accept/reject/silent. (url, 서버) 반환."""
    serve = pytest.importorskip("websockets.sync.server").serve

    def handler(ws):
        for msg in ws:
            data = json.loads(msg)
            if data[0] != "EVENT":
                continue
            if behavior == "accept":
                ws.send(json.dumps(["OK", data[1]["id"], True, ""]))
            elif behavior == "reject":
                ws.send(json.dumps(["OK", data[1]["id"], False, "blocked: 시험"]))
            # silent: 아무 응답 없음

    server = serve(handler, "127.0.0.1", 0)
    port = server.socket.getsockname()[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.2)
    return f"ws://127.0.0.1:{port}", server


def test_거부는_성공이_아니다():
    """OK 의 수락 플래그가 false 면 발행 실패 — 옛 코드는 이걸 성공으로 셌다."""
    url, server = _relay("reject")
    try:
        report = {}
        event_id = _Publisher()._publish_event(EVENT, relays=[url], report=report)
        assert event_id is None, "거부(OK false)를 성공으로 셌다"
        assert report["ok_count"] == 0
        assert "거부" in report["outcome"][url], report["outcome"]
    finally:
        server.shutdown()


def test_한_릴레이라도_수락하면_성공():
    """거부 + 수락이 섞이면 수락한 쪽 id 로 성공 — 과잉 교정(전부 실패 취급) 방지."""
    bad, s1 = _relay("reject")
    good, s2 = _relay("accept")
    try:
        report = {}
        event_id = _Publisher()._publish_event(EVENT, relays=[bad, good], report=report)
        assert event_id == EVENT["id"]
        assert report["ok_count"] == 1
        assert report["outcome"][good] == "ok"
    finally:
        s1.shutdown()
        s2.shutdown()


def _dm_sender(results):
    """send_dm_nip17 만 실물로 돌리는 최소 몸 — 발행 결과를 results 로 대본화."""
    class _T(social.IndieNetSocialMixin):
        _initialized = True
        calls = 0

        class _Id:
            class _K:
                @staticmethod
                def hex():
                    return "11" * 32
            private_key = _K()
        identity = _Id()

        def _to_hex(self, pubkey):
            return "22" * 32

        def fetch_dm_relays(self, to_hex):
            return ["wss://a", "wss://b"]

        def _publish_event(self, event, relays=None, report=None):
            self.calls += 1
            if report is not None:
                report["outcome"] = {"wss://a": "연결 실패: 503",
                                     "wss://b": "무응답(시간 초과)"}
            return results[min(self.calls - 1, len(results) - 1)]
    return _T()


def test_간헐_장애는_재시도로_넘긴다(monkeypatch):
    """첫 두 번이 릴레이 사정으로 비면 다시 두드린다 — 같은 gift_wrap 재발행은 멱등."""
    monkeypatch.setattr(social, "_DM_PUBLISH_BACKOFF", (0.01, 0.01))
    sender = _dm_sender([None, None, "ee" * 32])
    assert sender.send_dm_nip17("npub_test", "안녕") == "ee" * 32
    assert sender.calls == 3, "재시도 없이 첫 실패로 포기했다"


def test_끝까지_실패하면_사유를_남긴다(monkeypatch):
    """실패는 실패로 신고하되 릴레이별 사유를 그대로 — '전송 실패' 한 줄은 아무것도 못 알려준다."""
    monkeypatch.setattr(social, "_DM_PUBLISH_BACKOFF", (0.01, 0.01))
    sender = _dm_sender([None])
    assert sender.send_dm_nip17("npub_test", "안녕") is None
    assert sender.calls == social._DM_PUBLISH_ATTEMPTS
    reason = sender.dm_failure_reason()
    assert "wss://a" in reason and "503" in reason, reason


# ─────────────────────────────────────────────────────────────────────────────
# DM inbox 릴레이 확장(2026-08-30 사용자 승인) — 선언과 수신이 어긋나지 않게.
# ─────────────────────────────────────────────────────────────────────────────

def test_DM_inbox_선언은_단일_소스다():
    """_self_dm_relays() 와 publish_dm_relays() 기본값이 같은 목록을 본다.

    둘이 각자 하드코딩돼 있으면 "여기로 보내세요"라고 선언한 곳과 우리가 듣는 곳이
    말없이 갈라지고, 그 틈으로 배달된 DM 은 오류 없이 사라진다.
    """
    from indienet_common import DEFAULT_DM_RELAYS

    class _T(social.IndieNetSocialMixin):
        class _S:
            dm_relays = None
        settings = _S()

    t = _T()
    assert t._self_dm_relays() == list(DEFAULT_DM_RELAYS)

    t.settings.dm_relays = ["wss://only.example"]
    assert t._self_dm_relays() == ["wss://only.example"], "설정이 정본이어야 한다"


def test_선언한_릴레이는_반드시_구독한다():
    """실시간 구독 목록 ⊇ kind:10050 선언 목록 (합집합 보정)."""
    from channel_poller import _union_with_dm_inbox
    import indienet

    class _Fake:
        def _self_dm_relays(self):
            return ["wss://a", "wss://새로추가", "wss://b/"]

    real = indienet.get_indienet
    indienet.get_indienet = lambda: _Fake()
    try:
        out = _union_with_dm_inbox(["wss://a", "wss://b"])
    finally:
        indienet.get_indienet = real

    assert "wss://새로추가" in out, out
    assert out[:2] == ["wss://a", "wss://b"], "기존 구독 순서를 흔들지 않는다"
    assert len([u for u in out if u.rstrip("/") == "wss://b"]) == 1, "슬래시 차이로 중복되면 안 된다"


def test_DM_릴레이_기본값은_실측을_통과한_것만():
    """kind:1059 를 거부하는 릴레이(purplepag.es)·죽은 릴레이(snort)는 기본값에 없다.

    ★핸드셰이크 성공률로 고르면 안 된다 — purplepag.es 는 연결 4/4 였지만
    "blocked: kind 1059 is not allowed" 로 gift-wrap 을 거부한다(2026-08-30 실측).
    """
    from indienet_common import DEFAULT_DM_RELAYS
    assert "wss://purplepag.es" not in DEFAULT_DM_RELAYS
    assert "wss://relay.snort.social" not in DEFAULT_DM_RELAYS
    assert len(DEFAULT_DM_RELAYS) >= 3, "이중화가 목적이다 — 2개는 오늘 겪은 그 상황"


if __name__ == "__main__":
    # 러너는 하나 — pytest 에 위임 (test_single_runner 규약).
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
