"""세션 리셋 키워드는 짧은 대화 문장에서만 선다 — 위임·긴 지시문 안의 같은 글자열은 리셋이 아니다.

2026-10-01 실측(ep4226): 예약 위임 문구에 든 "처음부터 다시 훑지 말고"가 의식 OFF 경로에서 SESSION_RESET 으로
분류돼, 받는 에이전트가 세션을 지우고 표준 응답만 돌려줬다.
"""
import boot_paths  # noqa: F401
import pytest

from cognitive_consciousness import CognitiveConsciousnessMixin as _Owner


def _is_reset(message):
    return _Owner._is_reset_keyword(_Owner.__new__(_Owner), message)


def test_short_conversational_reset_still_detected():
    assert _is_reset("새 세션 시작하자")
    assert _is_reset("오늘은 여기까지 하자. 수고했어")


def test_delegated_task_is_never_a_reset():
    assert not _is_reset("[task:task_2ee6f491] 새 세션 시작")


def test_long_instruction_containing_the_phrase_is_not_a_reset():
    message = ("주간 재조사: 지난 조사 뒤 네 프로젝트 폴더에서 바뀐 파일을 기계가 대조했다. "
               "폴더를 처음부터 다시 훑지 말고 이 목록에서 출발한다. 사용자가 고친 줄은 보존한다.")
    assert not _is_reset(message)


def test_start_over_resets_only_as_a_whole_message():
    for message in ("처음부터 다시", "처음부터 다시 하자", "자, 처음부터 다시 시작하자!"):
        assert _is_reset(message), message
    for message in ("처음부터 다시 써줘", "그 보고서 처음부터 다시 만들어줘", "처음부터 다시 해줘",
                    "이 분석은 처음부터 다시 하자", "처음부터 다시 읽어보고 요약해"):
        assert not _is_reset(message), message


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
