"""증류 영속 큐 + 과제 독립 + action_health 보존정책 회귀 테스트 (2026-09-02).

  ① distill_queue: 적재→실행→행 삭제 / 실패 재시도(attempts·last_error) / 상한→failed /
     부팅 resume(러너 해소·orphaned·상한) / drain
  ② 시스템 AI 대화 삭제 → 과제는 독립 보존
  ③ _cleanup_old_data 가 action_health 와 큐 종결 행도 보존기간으로 정리

실행: .venv/bin/python -m pytest -q backend/test_distill_queue.py
"""
import sqlite3
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


@pytest.fixture
def dq(tmp_path, monkeypatch):
    import pulse_db
    import distill_queue as mod
    monkeypatch.setattr(pulse_db, "CONSCIOUSNESS_DB_PATH", tmp_path / "world_pulse.db")
    monkeypatch.setattr(mod, "RETRY_BACKOFF_SEC", (0, 0, 0))
    monkeypatch.setattr(mod.DistillQueue, "_instance", None)
    try:
        yield mod
    finally:
        mod.DistillQueue._instance = None


class _Runner:
    def __init__(self, fail_times=0):
        self.calls = []
        self.fail_times = fail_times

    def _after_response(self, user_message, response, **kw):
        self.calls.append((user_message, response, kw))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("경량 프로바이더 무응답")


def _rows(dq):
    conn = dq._conn()
    try:
        return conn.execute("SELECT id, status, attempts, last_error FROM distill_queue ORDER BY id").fetchall()
    finally:
        conn.close()


IDENT = {"registry_key": "p1:a1", "project_id": "p1", "agent_id": "a1", "agent_name": "비서"}


def test_enqueue_runs_and_deletes_row(dq):
    r = _Runner()
    q = dq.DistillQueue.get()
    row_id = q.enqueue(r, {"user_message": "u", "response": "a", "hippo_score": 0.3,
                           "tool_calls": [{"tool_name": "execute_ibl"}], "turn_tokens": 7},
                       ident=IDENT)
    assert row_id >= 1 and q.drain(timeout=5)["drained"]
    assert len(r.calls) == 1
    assert r.calls[0][2]["hippo_score"] == 0.3 and r.calls[0][2]["turn_tokens"] == 7
    assert _rows(dq) == []                         # 성공 = 행 삭제


def test_retry_then_success_keeps_ledger(dq):
    r = _Runner(fail_times=1)
    q = dq.DistillQueue.get()
    q.enqueue(r, {"user_message": "u", "response": "a"}, ident=IDENT)
    assert q.drain(timeout=5)["drained"]
    assert len(r.calls) == 2 and _rows(dq) == []


def test_failed_attempt_cost_survives_job_recreation_and_is_not_counted_twice(dq, tmp_path, monkeypatch):
    spent, events = [100], []
    monkeypatch.setattr('providers.base.read_turn_tokens', lambda: spent[0])
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda kind, data: events.append((kind, data)))

    class Runner(_Runner):
        def _after_response(self, *args, **kwargs):
            spent[0] += 40
            return super()._after_response(*args, **kwargs)

    payload = {'user_message': 'u', 'response': 'a',
               'turn_cost': {'events_path': str(tmp_path / 'events.jsonl')}}
    first = dq._Job(42, Runner(fail_times=1), payload, IDENT, attempts=1)
    with pytest.raises(RuntimeError):
        dq.DistillQueue._execute(first)
    path = tmp_path / 'postprocess.json'
    failed = json.loads(path.read_text())
    assert failed['tokens'] == 40 and not failed['succeeded']
    # 메모리 누계에 기대지 않고 새 Job이 기존 파일을 이어 읽는다.
    resumed = dq._Job(42, Runner(), payload, IDENT, attempts=2)
    dq.DistillQueue._execute(resumed)
    total = json.loads(path.read_text())
    assert total['tokens'] == 80 and total['attempts'] == 2 and total['succeeded']
    assert total['elapsed_s'] >= failed['elapsed_s'] and not total['incomplete']
    assert [(e['attempt'], e['tokens'], e['succeeded']) for _, e in events] == [(1, 40, False), (2, 40, True)]
    saved = path.read_text()
    dq.DistillQueue._record_cost(resumed, dq.time.monotonic(), spent[0], True)
    assert path.read_text() == saved and len(events) == 2


@pytest.mark.parametrize('before,attempt', [(None, 1), (100, 2)])
def test_missing_cost_is_not_reported_as_complete(dq, tmp_path, monkeypatch, before, attempt):
    monkeypatch.setattr('providers.base.read_turn_tokens', lambda: 200)
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda *args: None)
    payload = {'turn_cost': {'events_path': str(tmp_path / 'events.jsonl')}}
    job = dq._Job(43, _Runner(), payload, IDENT, attempts=attempt)
    dq.DistillQueue._record_cost(job, dq.time.monotonic(), before, True)
    cost = json.loads((tmp_path / 'postprocess.json').read_text())
    assert cost['incomplete'] and cost['tokens'] is None


def test_cost_write_failure_does_not_repeat_successful_memory_write(dq, tmp_path, monkeypatch):
    def fail(*args):
        raise OSError('계측 파일 쓰기 실패')

    monkeypatch.setattr(dq.DistillQueue, '_record_cost', fail)
    q, runner = dq.DistillQueue.get(), _Runner()
    q.enqueue(runner, {'user_message': 'u', 'response': 'a',
                      'turn_cost': {'events_path': str(tmp_path / 'events.jsonl')}}, ident=IDENT)
    assert q.drain(timeout=5)['drained']
    assert len(runner.calls) == 1 and _rows(dq) == []


def test_failed_after_max_attempts(dq):
    r = _Runner(fail_times=99)
    q = dq.DistillQueue.get()
    q.enqueue(r, {"user_message": "u", "response": "a"}, ident=IDENT)
    assert q.drain(timeout=5)["drained"]
    rows = _rows(dq)
    assert len(r.calls) == dq.MAX_ATTEMPTS
    assert len(rows) == 1 and rows[0][1] == "failed" and rows[0][2] == dq.MAX_ATTEMPTS
    assert "무응답" in rows[0][3]


def test_resume_resolves_orphans_and_exhausted(dq, monkeypatch):
    import agent_registry
    alive = _Runner()
    monkeypatch.setattr(agent_registry, "runner_registry", {"p1:a1": alive})
    conn = dq._conn()
    now = datetime.now().isoformat()
    conn.execute("INSERT INTO distill_queue (created_at, registry_key, payload, status, attempts) VALUES (?,?,?,?,?)",
                 (now, "p1:a1", '{"user_message":"살아있는 러너","response":"r"}', "running", 1))
    conn.execute("INSERT INTO distill_queue (created_at, registry_key, payload, status, attempts) VALUES (?,?,?,?,?)",
                 (now, "p9:ghost", '{"user_message":"죽은 러너","response":"r"}', "pending", 0))
    conn.execute("INSERT INTO distill_queue (created_at, registry_key, payload, status, attempts) VALUES (?,?,?,?,?)",
                 (now, "p1:a1", '{"user_message":"상한","response":"r"}', "pending", dq.MAX_ATTEMPTS))
    conn.commit(); conn.close()

    q = dq.DistillQueue.get()
    assert q.resume() == {"skipped": "not armed"}      # 무장 없이는(프로브) 재개 금지
    q.arm_resume()
    out = q.resume()
    assert out == {"resumed": 1, "orphaned": 1, "exhausted": 1}
    assert q.resume() == {"skipped": "not armed"}      # 1회성 무장
    assert q.drain(timeout=5)["drained"]
    assert [c[0] for c in alive.calls] == ["살아있는 러너"]
    rows = {r[1]: r for r in _rows(dq)}
    assert set(rows) == {"orphaned", "failed"}
    assert "러너 없음" in rows["orphaned"][3] and rows["failed"][2] == dq.MAX_ATTEMPTS


def test_drain_idle_immediately(dq):
    assert dq.DistillQueue.get().drain(timeout=1) == {"drained": True, "left": 0}


# ---------- ② 대화 삭제와 과제 독립 ----------

def test_clear_conversations_preserves_pursuit(tmp_path, monkeypatch):
    import system_ai_memory as sam
    from pursuit_ledger import PursuitLedger
    monkeypatch.setattr(sam, "MEMORY_DB_PATH", tmp_path / "system_ai_memory.db")
    monkeypatch.setattr(sam, "DATA_PATH", tmp_path)
    sam.init_memory_db()
    ledger = PursuitLedger(sam.MEMORY_DB_PATH, "system_ai:system_ai")
    row = ledger.create("계속할 일", "전체 기준", "turn1")
    sam.clear_conversations()
    assert ledger.get(row["id"])["goal_criteria"] == "전체 기준"


# ---------- ③ 보존정책 ----------

def test_cleanup_prunes_action_health_and_terminal_queue_rows(tmp_path, monkeypatch):
    import pulse_db
    import world_pulse
    import distill_queue as dq_mod
    monkeypatch.setattr(pulse_db, "CONSCIOUSNESS_DB_PATH", tmp_path / "world_pulse.db")
    monkeypatch.setattr(world_pulse, "_load_config", lambda: {"pulse_schedule": {"retention_days": 30}})
    old = (datetime.now() - timedelta(days=40)).isoformat()
    new = (datetime.now() - timedelta(days=3)).isoformat()
    conn = dq_mod._conn()   # 스키마 보장(pulse 테이블 + distill_queue)
    for ts in (old, new):
        conn.execute("INSERT INTO action_health (node, action, success, source, timestamp) VALUES ('self','read',1,'usage',?)", (ts,))
    conn.execute("INSERT INTO distill_queue (created_at, updated_at, payload, status) VALUES (?,?,'{}','failed')", (old, old))
    conn.execute("INSERT INTO distill_queue (created_at, payload, status) VALUES (?,'{}','pending')", (old,))
    conn.commit(); conn.close()

    deleted = world_pulse._cleanup_old_data()
    assert deleted["action_health"] == 1 and deleted["distill_queue"] == 1
    conn = sqlite3.connect(str(tmp_path / "world_pulse.db"), timeout=10)
    assert conn.execute("SELECT COUNT(*) FROM action_health").fetchone()[0] == 1       # 최근 행 보존
    assert conn.execute("SELECT status FROM distill_queue").fetchall() == [("pending",)]  # 미종결 행은 보존
    conn.close()


if __name__ == "__main__":                      # 러너는 하나 — pytest
    sys.exit(pytest.main([__file__, "-q"]))
