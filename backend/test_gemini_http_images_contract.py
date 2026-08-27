"""GeminiHTTP(REST) 이미지 입력 계약 회귀 (2026-08-27).

process_message(images=…)가 _build_contents 에 배선되지 않아 이미지가 침묵 폐기되던
결함(silent-clamp 부류)의 회귀 — SDK 판(gemini.py)과 같은 계약을 REST 판도 지킨다:
- 현재 턴 images → inline_data parts (base64 문자열 그대로, 텍스트보다 앞).
- 히스토리 h["images"] 도 동승(best-effort).
- 계약 위반(base64 없음)은 침묵 대신 정직 오류.
"""
import pytest

from providers.gemini_http import GeminiHTTPProvider


def _provider():
    p = GeminiHTTPProvider(api_key="test", model="gemini-test", system_prompt="system")
    p._client = True  # init_client 생략 — 네트워크 없는 계약 시험
    return p


IMG = {"base64": "aGVsbG8=", "media_type": "image/jpeg"}


def test_current_images_become_inline_data_parts():
    contents = _provider()._build_contents("보여?", [], images=[IMG])
    parts = contents[-1]["parts"]
    assert parts[0] == {"inline_data": {"mime_type": "image/jpeg", "data": "aGVsbG8="}}
    assert "<current_user_request>" in parts[-1]["text"]


def test_media_type_defaults_to_png():
    contents = _provider()._build_contents("m", [], images=[{"base64": "eA=="}])
    assert contents[-1]["parts"][0]["inline_data"]["mime_type"] == "image/png"


def test_history_images_ride_along():
    history = [{"role": "user", "content": "이전 질문", "images": [IMG]},
               {"role": "assistant", "content": "이전 답"}]
    contents = _provider()._build_contents("다음", history)
    assert contents[0]["parts"][0] == {
        "inline_data": {"mime_type": "image/jpeg", "data": "aGVsbG8="}}
    assert "<user_message>" in contents[0]["parts"][-1]["text"]
    assert len(contents[1]["parts"]) == 1  # 이미지 없는 턴은 텍스트만


def test_missing_base64_is_honest_not_silent():
    with pytest.raises(ValueError, match="base64"):
        _provider()._build_contents("m", [], images=[{"media_type": "image/png"}])
    # process_message 는 크래시 대신 정직 오류 문자열로 착지
    out = _provider().process_message("m", images=[{"media_type": "image/png"}])
    assert out.startswith("[이미지 입력 오류]")


def test_process_message_wires_images_into_request(monkeypatch):
    """원 결함의 회귀: images 인자가 실제 REST 요청 contents 까지 도달한다."""
    provider = _provider()
    seen = []

    def fake_generate(contents, tools):
        seen.append(contents)
        return {"candidates": [{"content": {"parts": [{"text": "봤어요"}]}}]}

    monkeypatch.setattr(provider, "_generate", fake_generate)
    out = provider.process_message("이 이미지 뭐야?", history=[], images=[IMG])
    assert out == "봤어요"
    inline = [p for p in seen[0][-1]["parts"] if "inline_data" in p]
    assert inline == [{"inline_data": {"mime_type": "image/jpeg", "data": "aGVsbG8="}}]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
