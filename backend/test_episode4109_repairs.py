"""과거 결과와 현재 능력 부정을 구분해 불필요한 재실행을 막는다."""
import json
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import capability_guard as guard


def finish(stream):
    events = []
    while True:
        try:
            events.append(next(stream))
        except StopIteration as stop:
            return events, stop.value


@pytest.mark.parametrize('response', [
    '앞서 공연을 확인하지 못했다고 안내했는데, 이번에는 찾았습니다.',
    '내일 회차의 잔여석과 개인 예매 가능 여부는 확인하지 못했어요.',
    '이번 재검색에서도 내일 열리는 대형 야외축제는 확인하지 못했어요.',
    '현재 파일을 읽지 못했습니다.',
    '요청 시간 안에 결과를 찾지 못하였습니다.',
    '이전에는 화면을 못 봤어요. 지금은 확인했습니다.',
    '지난 검색에서는 근거를 찾을 수 없었습니다.',
    '이 환경에서 자막 기능의 가능 여부는 아직 확인하지 못했습니다.',
])
def test_completed_observations_preserve_answer_without_model_or_lookup(monkeypatch, response):
    monkeypatch.setattr(guard, 'judge_once', lambda *a: pytest.fail('unnecessary model'))
    monkeypatch.setattr(guard, 'body_snapshot', lambda *a: pytest.fail('unnecessary lookup'))
    check = guard.CapabilityGuard(limits=dict(guard.DEFAULTS))
    events, result = finish(check.adopt(SimpleNamespace(), '확인해줘', response, []))
    assert result == response and not events
    assert (check.judgments, check.lookups, check.resumes) == (0, 0, 0)


@pytest.mark.parametrize('denial', [
    '저는 눈이 없어서 이미지를 볼 수 없습니다.',
    '이 파일을 열 수가 없습니다.',
    '지금은 웹 검색을 못합니다.',
    '파일을 읽을 권한이 없습니다.',
    'ffmpeg에는 자막 기능이 없습니다.',
    '현재도 파일을 못 읽어요.',
    'I cannot access the file.',
])
def test_current_denial_survives_past_result_in_same_sentence(denial):
    past = '이전 시도에서는 확인하지 못했지만, '
    matches = guard.candidate_matches(past + denial)
    assert matches and all(m.start() >= len(past) for m in matches)
    assert guard.packet('확인해줘', past + denial, [], guard.DEFAULTS)['candidates']


def test_past_failure_with_explicit_missing_means_still_checked():
    text = '파일을 읽을 권한이 없어서 열지 못했습니다.'
    assert guard.candidate_matches(text)


def test_model_quote_cannot_reintroduce_excluded_observation():
    past = '앞서 결과를 확인하지 못했습니다.'
    present = '이 파일은 열 수 없습니다.'
    text = past + '\n' + present
    packet = guard.packet('확인해줘', text, [], guard.DEFAULTS)
    rows = guard.parse(json.dumps({'claims': [
        {'quote': past, 'status': 'unsupported'},
        {'candidate_id': 'c0', 'status': 'unknown'},
    ]}), text, [], packet['candidates'])
    assert len(rows) == 1 and rows[0]['quote'] == present


def test_episode4109_answer_uses_no_guard_rounds():
    response = ('연극 1편과 전시 2개를 찾았습니다.\n'
                '앞서 공연을 확인하지 못했다고 안내했는데, 놓친 공연을 찾았습니다.\n'
                '다만 내일 회차의 잔여석과 개인 예매 가능 여부는 확인하지 못했어요.\n'
                '이번 재검색에서도 내일 열리는 대형 야외축제는 확인하지 못했어요.')
    check = guard.CapabilityGuard(limits=dict(guard.DEFAULTS))
    assert finish(check.adopt(SimpleNamespace(), '내일 행사를 찾아줘', response, [])) == ([], response)
    assert check.judgments == check.lookups == check.resumes == 0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
