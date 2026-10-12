"""첨부·진행 중인 요청의 후속을 단순 사실 통보와 구분한다."""
import json

import boot_paths  # noqa: F401
import pytest

from cognitive_consciousness import CognitiveConsciousnessMixin
from turn_scope import classification_message


def test_classification_context_is_bounded_text_without_attachment_bytes():
    history = [
        {"role": "user", "content": "old unrelated request"},
        {"role": "user", "content": "x" * 3000},
        {"role": "tool", "content": "tool secret"},
        {"role": "assistant", "content": "수치를 알려주시면 기록하겠습니다.",
         "images": [{"base64": "secret"}]},
    ]
    text = classification_message("117 72이고 맥박 73", history, [{"base64": "secret"}])
    value = json.loads(text)
    assert value["current_message"] == "117 72이고 맥박 73"
    assert value["attached_images"] == 1
    assert [x["role"] for x in value["recent_dialogue"]] == ["user", "assistant"]
    assert len(value["recent_dialogue"][0]["content"]) == 1500
    assert "old unrelated" not in text and "secret" not in text


@pytest.mark.parametrize("images, expected", [([], "CONTEXT_UPDATE"), ([{}], "EXECUTE")])
def test_image_cannot_be_locked_by_text_only_context_classification(monkeypatch, images, expected):
    monkeypatch.setattr("model_resolver.consciousness_enabled", lambda: True)
    seen = []
    monkeypatch.setattr("consciousness_agent.oneshot_ai_call",
                        lambda message, **kw: seen.append(message) or "CONTEXT_UPDATE")
    runner = CognitiveConsciousnessMixin()
    runner._log = lambda *a: None
    history = [{"role": "assistant", "content": "수치를 알려주시면 기록하겠습니다."}]
    assert runner._decide_request_type("오늘 측정 결과야", 0, "", history, images) == (expected, None)
    assert len(seen) == 1
    assert json.loads(seen[0])["recent_dialogue"] == history


def test_plain_notification_keeps_original_classifier_input():
    assert classification_message("숙소 예약되었다.") == "숙소 예약되었다."


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
