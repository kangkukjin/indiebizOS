"""ep3772: 이전 답변의 조사 예고만 남던 DB→의식 이중 절단 회귀."""
import sqlite3

import boot_paths  # noqa: F401
import pytest

from history_excerpt import history_excerpt, HISTORY_TEXT_CHARS, CONSCIOUSNESS_HISTORY_CHARS
from consciousness_agent import ConsciousnessAgent


def plan_input(history):
    return ConsciousnessAgent._build_input(
        None, '그 정책이 계속되는 이유를 설명해', history, '', '', '데이터', '')


def test_regular_answer_keeps_middle_findings_and_final_artifact():
    body = ('조사하겠습니다.\n' * 80 + '\n결과: 2025년 방문 159만 명, 전년 대비 14.8%.\n'
            + '근거와 해석을 구분한다.\n' * 100 + '\n산출물: /reports/jeju_compare.md')
    assert 500 < len(body) < HISTORY_TEXT_CHARS
    assert history_excerpt(body) == body
    assert body in plan_input([{'role': 'assistant', 'content': history_excerpt(body)}])


@pytest.mark.parametrize('limit', [1000, HISTORY_TEXT_CHARS, CONSCIOUSNESS_HISTORY_CHARS])
def test_long_excerpt_preserves_context_and_result_with_explicit_gap(limit):
    body = '요청 대상: 제주 정책 비교\n' + '중간 원문. ' * 8000 + '\n정정: 2025년, 159만 명. 파일: /reports/jeju.md'
    excerpt = history_excerpt(body, limit)
    assert len(excerpt) <= limit
    assert excerpt.startswith('요청 대상: 제주 정책 비교')
    assert excerpt.endswith('정정: 2025년, 159만 명. 파일: /reports/jeju.md')
    assert '중간 ' in excerpt and '자 생략' in excerpt and f'원문 {len(body)}자' in excerpt
    assert history_excerpt(excerpt, limit) == excerpt


@pytest.mark.parametrize('surface', ['project', 'system'])
@pytest.mark.parametrize('long', [False, True])
def test_saved_answer_reaches_consciousness_without_losing_result(tmp_path, monkeypatch, surface, long):
    import conversation_db as cdb
    import system_ai_memory as sm
    import onboarding_state
    for module in (cdb, sm):
        monkeypatch.setattr(module, '_ckpt_schedule', None)
        monkeypatch.setattr(module, '_ckpt_apply', None)
    monkeypatch.setattr(onboarding_state, '_marked_this_process', True)
    body = ('정책과 시기를 조사하겠습니다.\n' + '도입과 설명. ' * (2500 if long else 200)
            + '\n확인 결과: 2010년 제도 도입. 2023년 기준 10억 원. 산출물: /reports/jeju.md')
    rows = [('user', '제주 정책의 연혁을 조사해'), ('assistant', body),
            ('user', '확인했어'), ('assistant', '다음 질문을 받겠습니다.')]
    if surface == 'project':
        path = tmp_path / 'conversations.db'
        db = cdb.ConversationDB(str(path))
        user = db.get_or_create_agent('user', 'user')
        agent = db.get_or_create_agent('데이터')
        for i, (role, content) in enumerate(rows):
            mid = db.save_message(agent if role == 'assistant' else user,
                                  user if role == 'assistant' else agent, content)
            with db.get_connection() as conn:
                conn.execute('UPDATE messages SET message_time=? WHERE id=?',
                             (f'2026-09-14 10:00:0{i}', mid))
        history = db.get_history_for_ai(agent, user, limit=5)
        query = 'SELECT content FROM messages ORDER BY id'
    else:
        path = tmp_path / 'system_ai_memory.db'
        monkeypatch.setattr(sm, 'MEMORY_DB_PATH', path)
        for role, content in rows:
            sm.save_conversation(role, content)
        history = sm.get_history_for_ai()
        query = 'SELECT content FROM conversations ORDER BY id'
    selected = next(h['content'] for h in history if h['role'] == 'assistant')
    assert selected == history_excerpt(body)
    actual = plan_input(history)
    assert selected in actual  # DB 발췌를 의식 입구가 재절단하지 않는다.
    assert '2010년 제도 도입' in actual and '2023년 기준 10억 원' in actual
    assert '/reports/jeju.md' in actual
    with sqlite3.connect(path) as conn:
        assert conn.execute(query).fetchall()[1][0] == body


def test_checkpoint_and_projected_user_message_both_survive():
    from history_checkpoint import inject_head, MAX_CKPT_CHARS
    checkpoint = '## 핵심 사실과 결정\n' + '결정. ' * 850 + '\n마지막 정정: 기준 연도 2025년.'
    assert len(checkpoint) <= MAX_CKPT_CHARS
    user = history_excerpt('긴 지시. ' * 8000 + '\n완료 기준: /reports/jeju.md를 갱신')
    history = inject_head([{'role': 'user', 'content': user}],
                          {'role': 'user', 'content': checkpoint})
    actual = plan_input(history)
    assert checkpoint in actual and user in actual


def test_checkpoint_batch_reads_result_without_unbounded_growth():
    import history_checkpoint as hc
    content = '조사 예고. ' * 5000 + '\n결과: 2025년 159만 명. 파일 /reports/jeju.md'
    for count in [2, hc.MAX_ROWS_PER_UPDATE]:
        prompt = hc._build_prompt(None, [('assistant', content)] * count)
        assert prompt.count('결과: 2025년 159만 명. 파일 /reports/jeju.md') == count
        assert len(prompt) <= hc.BATCH_CHAR_CAP + 2000
        assert '진행 예고보다 실제 결론' in prompt


def test_partial_history_selection_still_controls_execution():
    from cognitive_consciousness import CognitiveConsciousnessMixin
    history = [{'role': 'assistant', 'content': history_excerpt('옛 블루칼라 과제. ' * 3000)},
               {'role': 'assistant', 'content': '제주 비교 결과: 2025년 159만 명. /reports/jeju.md'}]
    co = {'history_summary': '제주 비교 결과: 2025년 159만 명. /reports/jeju.md'}
    selected = CognitiveConsciousnessMixin()._apply_consciousness_to_history(history, co)
    assert '블루칼라' not in selected[0]['content']
    assert co['history_summary'] in selected[0]['content']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
