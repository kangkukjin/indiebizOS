"""기억 위생 수리 3종 회귀 테스트 (2026-09-02 기억관리 감사).

  ① 대화 삭제 = 원문 + 요약 체크포인트 한 트랜잭션 (system_ai_memory.clear_conversations)
     — 원문만 지우면 지운 대화가 다음 대화 머리에 되살아났다.
  ② 해마 귀속 관문 — 회상 top-1 액션이 실행에 안 쓰였으면 성공/실패를 귀속하지 않는다
     (record_recall_outcome ← _recall_was_used).
  ③ 심층기억 자동 회상은 used_at 을 올리지 않는다 (memory_db.read(touch=False))
     — 검색에 걸린 것과 쓰인 것은 다르다.

실행: .venv/bin/python -m pytest -q backend/test_memory_hygiene_2026_09.py
"""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


# ---------- ① 삭제 의미 ----------

def test_clear_conversations_drops_checkpoints(tmp_path, monkeypatch):
    import system_ai_memory as sam
    import history_checkpoint as hc
    db = tmp_path / "system_ai_memory.db"
    monkeypatch.setattr(sam, "MEMORY_DB_PATH", db)
    sam.init_memory_db()

    conn = sqlite3.connect(str(db))
    for i in range(3):
        conn.execute("INSERT INTO conversations(timestamp, role, content) VALUES (?,?,?)",
                     (f"2026-09-02T00:0{i}:00", "user", f"지워야 할 대화 {i}"))
    hc._ensure_table(conn)
    hc._store_ckpt(conn, "system_ai", "## 핵심 사실\n- 지워야 할 요약", 3)
    conn.commit()
    conn.close()
    assert hc._head_message(str(db), "system_ai") is not None  # 삭제 전엔 머리 주입

    deleted = sam.clear_conversations()
    assert deleted == {"conversations": 3, "checkpoints": 1}

    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM history_checkpoints").fetchone()[0] == 0
    conn.close()
    assert hc._head_message(str(db), "system_ai") is None  # 지운 대화가 되살아나지 않는다


def test_clear_conversations_without_checkpoint_table(tmp_path, monkeypatch):
    """체크포인트 테이블이 아직 없는 DB(신규 설치)에서도 삭제가 죽지 않는다."""
    import system_ai_memory as sam
    db = tmp_path / "system_ai_memory.db"
    monkeypatch.setattr(sam, "MEMORY_DB_PATH", db)
    sam.init_memory_db()
    assert sam.clear_conversations() == {"conversations": 0, "checkpoints": 0}


# ---------- ② 해마 귀속 관문 ----------

class _StubUsageDB:
    calls = []

    def update_success_by_code(self, code, success, elapsed_ms=None, tokens=None):
        _StubUsageDB.calls.append((code, success, elapsed_ms, tokens))
        return True


@pytest.fixture
def stub_usage_db(monkeypatch):
    import ibl_usage_db as mod
    _StubUsageDB.calls = []
    monkeypatch.setattr(mod, "IBLUsageDB", _StubUsageDB)
    return _StubUsageDB


def _tc(code, success=True):
    return {"tool_name": "execute_ibl", "input": {"code": code}, "success": success,
            "elapsed_ms": 12}


def test_attribution_skipped_when_recall_unused(stub_usage_db):
    from ibl_usage_rag import record_recall_outcome
    top = '[self:read]{path:"a.txt"}'
    ok = record_recall_outcome(top, 0.9, [_tc('[sense:search]{q:"자동화"}')])
    assert ok is False
    assert stub_usage_db.calls == []  # 안 쓰인 회상에 성공이 귀속되지 않는다


def test_attribution_recorded_when_recall_used(stub_usage_db):
    from ibl_usage_rag import record_recall_outcome
    top = '[self:read]{path:"a.txt"}'
    ok = record_recall_outcome(top, 0.9, [_tc('[self:read]{path:"b.txt"}')], turn_tokens=100)
    assert ok is True
    assert stub_usage_db.calls == [(top, True, 12, 100)]


def test_attribution_failure_still_requires_usage(stub_usage_db):
    """실패 귀속(감쇠)도 같은 관문 — 안 쓰인 회상이 남의 실패로 깎이지 않는다."""
    from ibl_usage_rag import record_recall_outcome
    top = '[self:read]{path:"a.txt"}'
    assert record_recall_outcome(top, 0.9, [_tc('[sense:search]{}', success=False)]) is False
    assert stub_usage_db.calls == []
    assert record_recall_outcome(top, 0.9, [_tc('[self:read]{}', success=False)]) is True
    assert stub_usage_db.calls == [(top, False, None, None)]


# ---------- ③ 자동 회상은 used_at 을 올리지 않는다 ----------

@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    pkg = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools" / "memory"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    import memory_db as mod
    monkeypatch.setattr(mod, "_index_one", lambda *a, **k: None)  # 임베딩 모델 무접촉
    return mod


def test_read_touch_false_keeps_used_at(tmp_path, memory_db):
    project = tmp_path / "proj"
    project.mkdir()
    mid = memory_db.save(str(project), "agent_x", "사용자는 아침형이다", "아침", "사용자선호")

    before = memory_db.read(str(project), "agent_x", mid, touch=False)
    assert before is not None and before["used_at"] is None       # 자동 회상: 그대로

    after = memory_db.read(str(project), "agent_x", mid)            # 명시 읽기: 갱신
    assert after["used_at"] is not None

    again = memory_db.read(str(project), "agent_x", mid, touch=False)
    assert again["used_at"] == after["used_at"]                    # 자동 회상이 덮지 않는다


if __name__ == "__main__":                      # 러너는 하나 — pytest
    sys.exit(pytest.main([__file__, "-q"]))
