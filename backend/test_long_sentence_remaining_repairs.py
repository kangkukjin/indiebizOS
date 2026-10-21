"""6~10회차 잔여: 실제 주입·의미 후보 조건·리허설 기록 격리. 모델 호출 없음."""
import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
from test_episode3388_repairs import Runner, isolated  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def test_rehearsal_commands_keep_history_and_polling_separate(tmp_path, monkeypatch, isolated):
    import api_agents
    import api_conversations
    import conversation_db
    import history_checkpoint
    import thread_context as tc

    manager = SimpleNamespace(get_project_path=lambda _: tmp_path)
    monkeypatch.setattr(api_agents, 'project_manager', manager)
    monkeypatch.setattr(api_conversations, 'project_manager', manager)
    scheduled, seen = [], []
    monkeypatch.setattr(conversation_db, '_ckpt_schedule', lambda *a: scheduled.append(a))
    monkeypatch.setattr(conversation_db, '_ckpt_apply', lambda *a: a[-1])

    def stream(**kwargs):
        seen.append((tc.get_task_origin(), kwargs['history']))
        yield {'type': 'final', 'content': '응답'}

    runner = Runner(tmp_path, stream)
    # Use the actual entry boundary while keeping the model and pipeline planning offline.
    def cognitive(command, history, **kw):
        return stream(history=history)
    monkeypatch.setattr(runner, 'cognitive_stream', cognitive)
    for message, origin in [('실사용', None), ('훈련1', 'training'),
                            ('훈련2', 'training'), ('실사용2', None)]:
        assert api_agents._run_agent_command('p', 'a', runner, message, origin) == '응답'
        assert tc.get_task_origin() is None
    assert [x[0] for x in seen] == ['user', 'training', 'training', 'user']
    assert seen[1][1] == []
    assert '훈련1' in str(seen[2][1]) and '실사용' not in str(seen[2][1])
    assert '실사용' in str(seen[3][1]) and '훈련' not in str(seen[3][1])
    assert len(scheduled) == 4  # training must not trigger checkpoint models
    db = conversation_db.ConversationDB(str(tmp_path / 'conversations.db'))
    uid = db.get_or_create_agent('user', 'human')
    aid = db.get_or_create_agent(runner.config['name'], 'ai_agent')
    normal = asyncio.run(api_conversations.get_messages('p', str(aid)))
    rehearsal = asyncio.run(api_conversations.get_messages('p', str(aid), rehearsal=True))
    assert len(normal['messages']) == len(rehearsal['messages']) == 4
    assert '훈련' not in str(normal) and '실사용' not in str(rehearsal)
    assert '훈련' not in str(db.get_messages(aid))
    between = asyncio.run(api_conversations.get_messages_between('p', aid, uid))
    assert '훈련' not in str(between)
    with db.get_connection() as conn:
        assert '훈련' not in str(history_checkpoint._fetch_pair(aid, uid)(conn))
        rows = conn.execute('SELECT requester_channel, status FROM tasks').fetchall()
        assert sorted(tuple(row) for row in rows) == [('gui', 'completed')] * 2 + [('rehearsal', 'completed')] * 2
    with sqlite3.connect(isolated) as conn:
        # pytest's process-wide test marker takes precedence over training.
        assert conn.execute("SELECT COUNT(*) FROM episode_log WHERE source='test'").fetchone()[0] == 4


def test_rehearsal_failure_and_background_keep_origin(tmp_path, monkeypatch, isolated):
    import api_agents
    import thread_context as tc
    monkeypatch.setattr(api_agents, 'project_manager', SimpleNamespace(get_project_path=lambda _: tmp_path))
    origins = []

    def fail(*args, **kwargs):
        origins.append(tc.get_task_origin())
        raise RuntimeError('리허설 오류')

    runner = SimpleNamespace(config={'name': '실패'}, cognitive_stream=fail, ai=True)
    with pytest.raises(RuntimeError):
        api_agents._run_agent_command('p', 'a', runner, '훈련', 'training')
    with sqlite3.connect(tmp_path / 'conversations.db') as conn:
        assert conn.execute('SELECT DISTINCT contact_type FROM messages').fetchall() == [('rehearsal',)]
        assert conn.execute('SELECT status FROM tasks').fetchone()[0] == 'failed'
    monkeypatch.setattr(api_agents, 'agent_runners', {'p': {'a': {'runner': runner}}})
    calls = []
    monkeypatch.setattr(api_agents, '_run_agent_command', lambda *a, **k: calls.append(a))
    monkeypatch.setattr(api_agents.threading, 'Thread', lambda target, **kw: SimpleNamespace(start=target))
    accepted = api_agents.send_agent_command('p', 'a', api_agents.AgentCommand(
        command='훈련', origin='training', background=True))
    assert accepted['status'] == 'started' and accepted['task_id'] and accepted['state'] == 'queued'
    assert calls[0][4] == 'training'
    with sqlite3.connect(tmp_path / 'conversations.db') as conn:
        # 백그라운드 접수는 실행 전에 작업을 선발급하고 리허설 채널로 남긴다.
        assert conn.execute('SELECT requester_channel FROM tasks WHERE task_id=?',
                            (accepted['task_id'],)).fetchone() == ('rehearsal',)
    for background in (True, False):
        with pytest.raises(api_agents.HTTPException) as refused:
            api_agents.send_agent_command('p', 'a', api_agents.AgentCommand(
                command='훈련', origin='unknown', background=background))
        assert refused.value.status_code == 400
    assert len(calls) == 1 and origins == ['training']


def test_compact_prompt_teaches_current_contracts():
    from prompt_builder import _build_system_ai_stable_prompt
    from ibl_v2_runtime import Budget
    prompt = _build_system_ai_stable_prompt()
    maxima = f"{Budget.REQUEST_LIMITS['steps'] // 10000:,}만/{Budget.REQUEST_LIMITS['rows'] // 10000}만"
    for contract in ('calls:true', 'steps_by_line', maxima, '효과 없는 지역 함수', 'get(객체,키)'):
        assert contract in prompt


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
