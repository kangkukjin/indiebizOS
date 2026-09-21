"""SQLite UTC 대화 시간이 현지 오전으로 오인되던 9시간 표시 오차 회귀."""
import os
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import boot_paths  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_conversations as api
import conversation_db as cdb


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    monkeypatch.setattr(cdb, '_ckpt_schedule', None)
    monkeypatch.setattr(cdb, '_ckpt_apply', None)
    db = cdb.ConversationDB(str(tmp_path / 'conversations.db'))
    user = db.get_or_create_agent('user', 'user')
    agent = db.get_or_create_agent('수업보조.')
    question = db.save_message(user, agent, '지금 몇시야?')
    answer = db.save_message_undelivered(agent, user, '오후 6시 23분입니다.')
    with db.get_connection() as conn:
        conn.execute('UPDATE messages SET message_time=? WHERE id=?', ('2026-09-21 09:23:26', question))
        conn.execute('UPDATE messages SET message_time=? WHERE id=?', ('2026-09-21 09:23:32', answer))
    (tmp_path / 'agents.yaml').write_text('agents:\n  - id: agent_001\n    name: 수업보조.\n')
    monkeypatch.setattr(api, 'project_manager', SimpleNamespace(get_project_path=lambda _: tmp_path))
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        yield db, user, agent, client


@pytest.mark.parametrize('original,expected', [
    ('2026-09-21 09:23:32', '2026-09-21T09:23:32Z'),
    ('2026-09-21T09:23:32Z', '2026-09-21T09:23:32Z'),
    ('2026-09-21T18:23:32+09:00', '2026-09-21T09:23:32Z'),
    ('2026-09-21 09:23:32.123456', '2026-09-21T09:23:32.123456Z'),
    (None, None), ('', ''), ('invalid', 'invalid'),
])
def test_message_timestamp_preserves_instant_and_missing_data(original, expected):
    assert cdb.ConversationDB.message_timestamp(original) == expected
    assert cdb.ConversationDB.message_timestamp(expected) == expected


@pytest.mark.parametrize('endpoint', ['history', 'remote_history', 'between', 'undelivered', 'partners'])
def test_all_project_chat_surfaces_expose_timezone(conversation, endpoint):
    db, user, agent, client = conversation
    paths = {
        'history': f'/conversations/school/{agent}/messages',
        'remote_history': '/conversations/school/agent_001/messages',
        'between': f'/conversations/school/between/{user}/{agent}',
        'undelivered': '/conversations/school/수업보조./undelivered',
        'partners': f'/conversations/school/{agent}/partners',
    }
    result = client.get(paths[endpoint])
    assert result.status_code == 200
    data = result.json()
    value = (data['partners'][0]['last_message_time'] if endpoint == 'partners'
             else data['messages'][0]['timestamp'])
    assert value == '2026-09-21T09:23:32Z'
    moment = datetime.fromisoformat(value)
    assert moment.astimezone(ZoneInfo('Asia/Seoul')).strftime('%H:%M') == '18:23'
    assert moment.astimezone(ZoneInfo('America/New_York')).strftime('%H:%M') == '05:23'
    # 화면 교정은 원문 데이터의 일괄 +9시간 변경이 아니다.
    with db.get_connection() as conn:
        assert conn.execute('SELECT message_time FROM messages ORDER BY id DESC LIMIT 1').fetchone()[0] == '2026-09-21 09:23:32'


def test_db_readers_and_new_message_share_utc_contract(conversation):
    db, user, agent, _ = conversation
    assert db.get_messages(agent)[0]['timestamp'] == '2026-09-21T09:23:32Z'
    assert db.get_undelivered_messages(agent, user)[0]['timestamp'] == '2026-09-21T09:23:32Z'
    mid = db.save_message(user, agent, '새 대화')
    value = next(row['timestamp'] for row in db.get_messages(agent) if row['id'] == mid)
    assert value.endswith('Z')
    assert datetime.fromisoformat(value).utcoffset().total_seconds() == 0


@pytest.mark.skipif(not hasattr(time, 'tzset'), reason='프로세스 TZ 전환은 Unix에서 검증')
def test_model_history_uses_local_time_with_offset(conversation):
    db, user, agent, _ = conversation
    previous = os.environ.get('TZ')
    try:
        os.environ['TZ'] = 'Asia/Seoul'
        time.tzset()
        history = db.get_history_for_ai(agent, user)
        assert next(row['content'] for row in history if row['role'] == 'user').startswith('[2026-09-21 18:23 +0900] ')
        assert next(row['content'] for row in history if row['role'] == 'assistant') == '오후 6시 23분입니다.'
    finally:
        if previous is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = previous
        time.tzset()


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
