"""자동 소개의 글자 근거: 어절 경계·반복·긴 복합 요청."""
import boot_paths  # noqa: F401
from recall_relevance import lexical_evidence


def test_one_shared_word_and_repeated_word_do_not_make_two_signals():
    assert not lexical_evidence('본체 음량 낮춰', '나레이션 음량 정렬')
    assert not lexical_evidence('본체 음량 음량을 낮춰', '나레이션 음량 정렬')
    assert not lexical_evidence('파일', '컴파일 도구')
    assert lexical_evidence('파일 압축을 해줘', '파일의 압축')


def test_long_request_can_match_a_local_subtask_without_matching_everything():
    query = ('공신력 있는 소스들을 모아서 하네스 제작에 대한 의견을 비교해줘. '
             '차이를 설명한 뒤 보고서를 읽기 좋게 HTML 파일로 만들어줘. '
             '자료를 덜 읽었다면 어느 자료가 부족한지도 알려줘.')
    assert lexical_evidence(query, '마크다운 보고서 → 자족 HTML')
    assert not lexical_evidence(query, '나레이션 파일 음량 정렬')


def test_single_term_and_unicode_normalization():
    assert lexical_evidence('압축', '파일 압축과 시험 결과')
    assert lexical_evidence('ＨＴＭＬ 보고서', 'html 보고서')
    assert not lexical_evidence('압', '파일 압축')


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
