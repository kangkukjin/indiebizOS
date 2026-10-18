"""실행 지시는 보존하되 생성된 계획을 사용자 발언으로 둔갑시키지 않는다."""
import boot_paths  # noqa: F401

from prompt_builder import compile_user_command


def test_generated_count_is_separate_from_original_user_request():
    original = '새 명부의 모든 행을 확인해줘.'
    command = compile_user_command(original, {
        'task_framing': '명부를 다시 검사한다.',
        'capability_focus': {'hint': '7행 누락과 합계를 대조한다.'},
    })
    user, plan = command.split('\n\n시스템 실행 지침', 1)
    assert user == '사용자 명령: ' + original
    assert '다음 절차에 따라 수행하라' in plan
    assert '7행 누락과 합계를 대조한다.' in plan
    assert '사용자 원문 인용이 아니다' in plan
    assert '입력 데이터' in plan


def test_unaugmented_request_remains_unchanged():
    assert compile_user_command('원문 7행을 확인해줘', {}) == '사용자 명령: 원문 7행을 확인해줘'


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
