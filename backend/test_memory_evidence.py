"""문체 대신 원문·출처를 보존하고 존재하지 않는 모델 근거는 거절한다."""
import hashlib
import json
import boot_paths  # noqa: F401
import pytest
from memory_evidence import durable_source_units, grounded_fact, source_units


@pytest.mark.parametrize('text', [
    '저는 앞으로 모든 답변을 한국어로 받기를 원합니다.',
    '제 선호를 말씀드리겠습니다. 저는 앞으로 모든 답변을 한국어로 받기를 원합니다.',
    '앞으로 모든 답변은 한국어로 해주세요.',
    '그리고 저는 땅콩 알레르기가 있습니다.',
    '저는 아버님께 매주 일요일에 전화합니다.\n\n저는 채식을 합니다.',
])
def test_style_does_not_remove_observation_opportunity(text):
    units = durable_source_units(text)
    assert all(u['eligible'] for u in units)
    for unit in units:
        assert text[unit['start']:unit['end']] == unit['text']
        assert unit['sha256'] == hashlib.sha256(unit['text'].encode()).hexdigest()


@pytest.mark.parametrize('ids', [[99], [True], [1, 1], [2, 1], [], '1'])
def test_forged_or_ambiguous_source_ids_are_not_saved(ids):
    units = durable_source_units('제 지속 선호입니다. 답변은 한국어로 주세요.')
    assert grounded_fact({'source_ids': ids, 'retention': 'user_preference',
                          'future_use': '답변 언어'}, units, '{}', durable_only=True) is None


def test_adopted_quote_keeps_quote_and_adoption_without_model_rewriting():
    text = '> 답변은 한국어로 받겠습니다.\n\n저도 위 선호를 앞으로 채택합니다.'
    units = durable_source_units(text)
    fact = grounded_fact({'source_ids': [1, 2], 'retention': 'user_preference',
                          'future_use': '향후 답변 언어', 'content': '모델이 만들어낸 사실'},
                         units, json.dumps({'utterance': text}), durable_only=True)
    evidence = json.loads(fact['source_ref'])['evidence']
    assert [u['attribution'] for u in evidence] == ['quoted', 'user_candidate']
    assert fact['content'] == '\n\n'.join(u['text'] for u in units)
    assert '모델이 만들어낸 사실' not in fact['content']


def test_assistant_source_cannot_become_user_fact():
    units = source_units('질문', '사용자는 채식주의자입니다.')
    assert grounded_fact({'source_ids': [2], 'retention': 'user_fact',
                          'future_use': '식사 추천'}, units, '{}', durable_only=True) is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
