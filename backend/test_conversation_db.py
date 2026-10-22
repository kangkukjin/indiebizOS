"""Rehearsal history keeps source requests outside the recent message window."""
import boot_paths  # noqa: F401
import pytest

import conversation_db as cdb
from consciousness_agent import ConsciousnessAgent


@pytest.mark.parametrize('turns', [4, 30])
def test_rehearsal_old_request_survives_window_and_reopen(tmp_path, monkeypatch, turns):
    monkeypatch.setattr(cdb, '_ckpt_schedule', None)
    def forbidden(*args):
        raise AssertionError('Rehearsal must not consume the live checkpoint')
    monkeypatch.setattr(cdb, '_ckpt_apply', forbidden)
    db = cdb.ConversationDB(str(tmp_path / 'conversation.db'))
    user = db.get_or_create_agent('user', 'human')
    agent = db.get_or_create_agent('worker', 'ai_agent')
    other = db.get_or_create_agent('other', 'ai_agent')
    rule = '첫 요청: inputs와 내 ai만 읽는다. reference·snapshots는 읽지 않는다.'
    saved = []
    for n in range(turns):
        question = rule if n == 0 else f'후속 {n}: 앞서 정한 범위로 계속해.'
        if n == turns - 1:
            question += ' 정정: 예산은 420만원이다.'
        answer = 'assistant의 제안이며 승인 아님. ' + ('중간 분석 ' * 1600) + f' 결과 {n}'
        saved.extend([question, answer])
        db.save_message(user, agent, question, contact_type='rehearsal')
        db.save_message(agent, user, answer, contact_type='rehearsal')
    db.save_message(user, agent, '실사용 비밀', contact_type='gui')
    db.save_message(user, agent, '연구 비밀', contact_type='research')
    db.save_message(user, other, '다른 에이전트 비밀', contact_type='rehearsal')
    reopened = cdb.ConversationDB(db.db_path)
    history = reopened.get_history_for_ai(agent, user, rehearsal=True)
    text = str(history)
    assert rule in text and '예산은 420만원' in text
    assert '실사용 비밀' not in text and '연구 비밀' not in text and '다른 에이전트 비밀' not in text
    assert '[1 user]' in text and 'assistant]' in text
    assert sum(len(m['content']) for m in history) < 61000
    assert not any(a['role'] == b['role'] == 'user' for a, b in zip(history, history[1:]))
    if turns == 30:
        assert '메시지 생략' in text
    plan = ConsciousnessAgent._build_input(None, '인계서에서 계속해', history, '', '', 'worker', '')
    assert rule in plan and '예산은 420만원' in plan
    with db.get_connection() as conn:
        actual = [r[0] for r in conn.execute("SELECT content FROM messages WHERE contact_type='rehearsal' AND (from_agent_id=? OR to_agent_id=?) ORDER BY id", (agent, agent))]
    assert actual == saved
    assert reopened.get_history_for_ai(agent, user, limit=0, rehearsal=True) == []


def test_rehearsal_short_history_keeps_roles_and_no_old_excerpt(tmp_path, monkeypatch):
    monkeypatch.setattr(cdb, '_ckpt_schedule', None)
    db = cdb.ConversationDB(str(tmp_path / 'conversation.db'))
    user = db.get_or_create_agent('user', 'human')
    agent = db.get_or_create_agent('worker', 'ai_agent')
    db.save_message(user, agent, '요청', contact_type='rehearsal')
    db.save_message(agent, user, '응답', contact_type='rehearsal')
    history = db.get_history_for_ai(agent, user, rehearsal=True)
    assert [r['role'] for r in history] == ['user', 'assistant']
    assert history[1]['content'] == '응답'
    assert '이전 원문 발췌' not in str(history)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
