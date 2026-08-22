r"""다중채팅방 회귀 배터리 — 서로의 답을 읽는가 / 멘션이 조사에 걸리는가 (2026-08-22 수리)

신호: 유튜브 영상(Hermes "Bot Mode")의 그룹 챗 기준으로 우리 다중채팅방을 재보니
"서로의 답을 보면서 대화한다"는 전제가 코드에서 무너져 있었다.

진단 두 건:
  A. `_get_agent_response` 가 `history[:-1]` 로 꼬리를 잘랐다. 꼬리가 사용자
     메시지인 것은 첫 응답자뿐 — 두 번째 응답자부터는 방금 앞사람이 한 말이
     통째로 잘려, 참여자 전원이 서로를 못 본 채 같은 질문에 각자 답했다.
  B. `_parse_mentions` 가 `@(\S+)` 토큰을 이름과 **정확 일치**로 비교했다.
     한글은 이름 뒤에 조사가 붙으므로(`@뉴턴한테`) 매칭이 깨지고, 깨지면
     `random.sample` 로 조용히 폴백해 "못 알아들었다"가 "아무나 답했다"로 둔갑했다.
  C. (A 를 고치다 드러남) `message_time` 은 초 단위라 한 턴의 메시지가 전부 동률이
     되는데, `ORDER BY message_time DESC` 만으로 뽑아 `reversed()` 하면 동률 구간이
     통째로 **거꾸로** 선다. 대화가 역순으로 모델에 들어가고 화면에도 뒤집혀 나온다.
     타이브레이커 `id DESC` 로 못박았다.

    T1. 두 번째 응답자의 히스토리에 첫 응답자의 발언이 들어있다 (A 재현 케이스)
    T2. 첫 응답자는 종전대로 자기 자신을 히스토리에서 보지 않는다 (회귀 없음)
    T3. 조사가 붙은 멘션(`@뉴턴한테`)이 지목으로 해소된다 (B 재현 케이스)
    T4. 긴 이름 우선 — `@김대리` 가 `김` 이 아니라 `김대리` 로 붙는다
    T5. `@everyone`(모두/전체)이 방 전원을 부른다
    T6. 방에 없는 이름을 부르면 랜덤 폴백 대신 정직하게 신고한다
    T7. 멘션이 아예 없을 때의 랜덤 선택은 그대로 (설계된 동작)

실행: python3 -m pytest backend/test_multi_chat_round.py
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BACKEND)
import boot_paths  # noqa: E402,F401

from multi_chat_manager import MultiChatManager  # noqa: E402


class _FakeAgent:
    """AIAgent 대역 — 무엇이 히스토리로 들어왔는지만 기록한다."""

    calls = []

    def __init__(self, **kwargs):
        self.agent_name = kwargs.get("agent_name", "")

    def process_message_with_history(self, message_content="", history=None, images=None):
        _FakeAgent.calls.append({
            "agent": self.agent_name,
            "message": message_content,
            "history": list(history or []),
        })
        return f"{self.agent_name}의 답"


@pytest.fixture
def room(monkeypatch):
    """참여자 3명이 든 빈 방 + AI 호출 대역."""
    tmp = tempfile.mkdtemp(prefix="multichat_test_")
    (Path(tmp) / "data").mkdir(parents=True, exist_ok=True)

    mgr = MultiChatManager(base_path=Path(tmp), ai_config={"provider": "test"})

    import multi_chat_manager as mod
    monkeypatch.setattr(mod, "AIAgent", _FakeAgent)

    import model_resolver
    monkeypatch.setattr(model_resolver, "resolve_agent_ai",
                        lambda cfg, pid, aid: {**cfg, "model": "test-model"})

    room_id = mgr.db.create_room("테스트방", "")
    for name in ("자비스", "뉴턴", "김대리"):
        mgr.db.add_participant(room_id, name, agent_source="", system_prompt="")

    _FakeAgent.calls = []
    return mgr, room_id


def _names(participants):
    return [p["agent_name"] for p in participants]


# ---- A: 서로의 답을 읽는가 ----

def test_t1_second_responder_sees_first(room):
    """T1 — 두 번째 응답자의 히스토리에 첫 응답자의 발언이 들어있다."""
    mgr, room_id = room
    responses = mgr.send_message(room_id, "@자비스 @뉴턴 신제품 검토해줘")

    assert [r["speaker"] for r in responses] == ["자비스", "뉴턴"]
    second = _FakeAgent.calls[1]
    assert second["agent"] == "뉴턴"

    joined = " ".join(h["content"] for h in second["history"])
    assert "자비스의 답" in joined, "앞사람의 발언이 히스토리에서 잘렸다 (수리 전 동작)"
    # 현재 턴의 사용자 메시지는 히스토리가 아니라 message_content 로 간다
    assert second["message"] == "@자비스 @뉴턴 신제품 검토해줘"
    assert "신제품 검토해줘" not in joined


def test_t2_first_responder_history_clean(room):
    """T2 — 첫 응답자는 아직 아무 답도 없으므로 히스토리가 비어 있다."""
    mgr, room_id = room
    mgr.send_message(room_id, "@자비스 시작하자")

    first = _FakeAgent.calls[0]
    assert first["agent"] == "자비스"
    assert first["history"] == []
    assert first["message"] == "@자비스 시작하자"


def test_t2b_prior_turns_survive(room):
    """T2b — 이전 턴들은 그대로 남는다 (사용자 메시지 하나만 빠진다)."""
    mgr, room_id = room
    mgr.send_message(room_id, "@자비스 1턴")
    _FakeAgent.calls = []
    mgr.send_message(room_id, "@뉴턴 2턴")

    hist = _FakeAgent.calls[0]["history"]
    joined = " ".join(h["content"] for h in hist)
    assert "1턴" in joined and "자비스의 답" in joined
    assert _FakeAgent.calls[0]["message"] == "@뉴턴 2턴"


# ---- B: 멘션 해소 ----

def test_t3_korean_particle_mention(room):
    """T3 — `@뉴턴한테` 처럼 조사가 붙어도 지목으로 해소된다."""
    mgr, room_id = room
    participants = mgr.db.get_participants(room_id)

    mentioned, unknown = mgr._parse_mentions("@뉴턴한테 분석 좀 넘겨줘", participants)
    assert _names(mentioned) == ["뉴턴"]
    assert unknown == []


def test_t4_longest_name_wins(room):
    """T4 — 긴 이름 우선. `@김대리` 가 `김대리` 로 붙는다."""
    mgr, room_id = room
    mgr.db.add_participant(room_id, "김", agent_source="", system_prompt="")
    participants = mgr.db.get_participants(room_id)

    mentioned, unknown = mgr._parse_mentions("@김대리 확인 부탁", participants)
    assert _names(mentioned) == ["김대리"]
    assert unknown == []


def test_t5_mention_all(room):
    """T5 — @everyone / @모두 는 방 전원을 부른다."""
    mgr, room_id = room
    participants = mgr.db.get_participants(room_id)

    for token in ("@everyone", "@모두", "@전체"):
        mentioned, unknown = mgr._parse_mentions(f"{token} 논의 시작", participants)
        assert _names(mentioned) == _names(participants), token
        assert unknown == []


def test_t6_unknown_mention_is_reported_not_randomized(room):
    """T6 — 방에 없는 이름을 부르면 아무나 대답하지 않고 정직하게 신고한다."""
    mgr, room_id = room
    responses = mgr.send_message(room_id, "@해밍웨이 카피 좀 써줘")

    assert len(responses) == 1
    assert responses[0]["speaker"] == "시스템"
    assert "@해밍웨이" in responses[0]["content"]
    assert "이 방에 없습니다" in responses[0]["content"]
    assert _FakeAgent.calls == [], "지목 실패가 랜덤 호출로 새어 나갔다"


def test_t8_same_second_messages_stay_chronological(room):
    """T8 — 같은 초에 들어간 메시지도 시간순을 지킨다 (동률 타이브레이커)."""
    mgr, room_id = room
    for speaker, content in [("사용자", "하나"), ("자비스", "둘"),
                             ("사용자", "셋"), ("뉴턴", "넷")]:
        mgr.db.add_message(room_id, speaker, content)

    hist = [h["content"] for h in mgr.db.get_history_for_ai(room_id)]
    assert hist == ["하나", "[자비스] 둘", "셋", "[뉴턴] 넷"], hist

    shown = [m["content"] for m in mgr.db.get_messages(room_id)]
    assert shown == ["하나", "둘", "셋", "넷"], shown


def test_t7_no_mention_still_random(room):
    """T7 — 멘션이 아예 없으면 종전대로 response_count 만큼 랜덤 응답."""
    mgr, room_id = room
    responses = mgr.send_message(room_id, "다들 어떻게 생각해?", response_count=2)

    assert len(responses) == 2
    assert all(r["speaker"] in ("자비스", "뉴턴", "김대리") for r in responses)


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
