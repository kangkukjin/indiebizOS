"""증류 영속 큐 + framing 삭제 훅 + action_health 보존정책 회귀 테스트 (2026-09-02).

  ① distill_queue: 적재→실행→행 삭제 / 실패 재시도(attempts·last_error) / 상한→failed /
     부팅 resume(러너 해소·orphaned·상한) / drain
  ② 시스템 AI 대화 삭제 → framing 재고 폐기(그 에이전트 키만)
  ③ _cleanup_old_data 가 action_health 와 큐 종결 행도 보존기간으로 정리

실행: .venv/bin/python -m pytest -q backend/test_distill_queue.py
"""
import sqlite3
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


# ---------- ② framing 삭제 훅 ----------

def test_clear_conversations_drops_system_ai_framing(tmp_path, monkeypatch):
    import system_ai_memory as sam
    import cognitive_consciousness as cc
    cc.install()
    monkeypatch.setattr(sam, "MEMORY_DB_PATH", tmp_path / "system_ai_memory.db")
    monkeypatch.setattr(sam, "DATA_PATH", tmp_path)
    sam.init_memory_db()
    cc.clear_framing_cache()
    cc.framing_cache_set("system:system_ai", {"task_framing": "지운 대화의 지도"})
    cc.framing_cache_set("proj:비서", {"task_framing": "다른 몸의 지도"})

    sam.clear_conversations()
    assert cc.framing_cache_get("system:system_ai") is None      # 지운 대화의 지도는 폐기
    assert cc.framing_cache_get("proj:비서") is not None          # 다른 에이전트는 무관
    cc.clear_framing_cache()


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
