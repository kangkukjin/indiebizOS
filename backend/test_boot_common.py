"""boot_common 회귀 — 부팅 때의 작업 원장 정리(긴문장 84회차 L84-2, 2026-10-20).

재현한 결함: 부팅마다 status='completed' 행을 전부 지워, 백그라운드 접수증(status_url)이 재기동을 넘기면
404 "작업을 찾을 수 없습니다" 가 됐고 소비자는 '접수된 적 없음'과 '종료 후 소실'을 가를 수 없었다
(2026-10-07 코딩 앱 "완료 작업은 재기동 때 지워져 접수증 unknown" 과 같은 원인).
수리 계약: 보존 기간(TASK_RETENTION_DAYS) 안의 종료 행은 그대로 살고, 지난 행만 묘비(task_tombstones)로 바뀐다.
실 모델·네트워크 없음 — 임시 SQLite.
"""
import json
import sqlite3

import boot_paths  # noqa: F401
import pytest

import boot_common
import system_ai_memory as memory


@pytest.fixture
def base(tmp_path, monkeypatch):
    """프로젝트 하나(projects.json 등록) + 시스템 AI 원장을 임시 base 아래에 만든다."""
    from conversation_db import ConversationDB
    project_path = tmp_path / "projects" / "fixture"
    project_path.mkdir(parents=True)
    (tmp_path / "projects" / "projects.json").write_text(json.dumps(
        [{"id": "fixture", "type": "project", "path": str(project_path)}]), encoding="utf-8")
    data_path = tmp_path / "data"
    data_path.mkdir()
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", data_path / "system_ai_memory.db")
    monkeypatch.setattr(memory, "DATA_PATH", data_path)
    memory.init_memory_db()
    db = ConversationDB(str(project_path / "conversations.db"))
    return {"tmp": tmp_path, "data": data_path, "db": db, "project_db": project_path / "conversations.db"}


def _age(db_file, task_id, days):
    with sqlite3.connect(db_file) as conn:
        conn.execute("UPDATE tasks SET completed_at = datetime('now', ?) WHERE task_id = ?", (f"-{days} days", task_id))


def _statuses(db_file):
    with sqlite3.connect(db_file) as conn:
        return dict(conn.execute("SELECT task_id, status FROM tasks").fetchall())


def test_restart_cleanup_keeps_recent_terminal_rows_with_full_result(base):
    db = base["db"]
    db.create_task("t_done", "user@gui", "gui", "명령", "조사자")
    db.complete_task("t_done", "결과 전문 " * 300)
    db.create_task("t_failed", "user@gui", "gui", "명령", "조사자")
    db.fail_task("t_failed", "터짐")
    db.create_task("t_running", "user@gui", "gui", "명령", "조사자")
    memory.create_task("s_done", "user@gui", "gui", "시스템 명령")
    memory.complete_task("s_done", "시스템 결과")

    assert boot_common._cleanup_completed_tasks(base["tmp"], base["data"], "[t]") is True   # 재기동 모사

    assert _statuses(base["project_db"]) == {"t_done": "completed", "t_failed": "failed", "t_running": "pending"}
    assert db.get_task("t_done")["result"] == "결과 전문 " * 300          # 전문 그대로
    assert memory.get_task("s_done")["status"] == "completed" and memory.get_task("s_done")["result"] == "시스템 결과"


def test_rows_past_retention_become_tombstones_and_pending_rows_stay(base):
    db = base["db"]
    db.create_task("t_old", "user@gui", "gui", "명령", "조사자")
    db.complete_task("t_old", "옛 결과")
    _age(base["project_db"], "t_old", boot_common.TASK_RETENTION_DAYS + 1)
    db.create_task("t_old_failed", "user@gui", "gui", "명령", "조사자")
    db.fail_task("t_old_failed", "옛 실패")
    _age(base["project_db"], "t_old_failed", boot_common.TASK_RETENTION_DAYS + 5)
    db.create_task("t_fresh", "user@gui", "gui", "명령", "조사자")
    db.complete_task("t_fresh", "새 결과")
    db.create_task("t_pending_old", "user@gui", "gui", "명령", "조사자")   # 진행 중은 나이와 무관하게 산다
    with sqlite3.connect(base["project_db"]) as conn:
        conn.execute("UPDATE tasks SET created_at = datetime('now', '-400 days') WHERE task_id = 't_pending_old'")
    memory.create_task("s_old", "user@gui", "gui", "시스템 명령")
    memory.complete_task("s_old", "옛 시스템 결과")
    _age(memory.MEMORY_DB_PATH, "s_old", boot_common.TASK_RETENTION_DAYS + 1)

    boot_common._cleanup_completed_tasks(base["tmp"], base["data"], "[t]")

    assert _statuses(base["project_db"]) == {"t_fresh": "completed", "t_pending_old": "pending"}
    with sqlite3.connect(base["project_db"]) as conn:
        tombs = {r[0]: r for r in conn.execute(
            "SELECT task_id, status, delegated_to, completed_at, pruned_at FROM task_tombstones").fetchall()}
    assert set(tombs) == {"t_old", "t_old_failed"}
    assert tombs["t_old"][1] == "completed" and tombs["t_old"][2] == "조사자" and tombs["t_old"][3] and tombs["t_old"][4]
    assert tombs["t_old_failed"][1] == "failed"
    assert memory.get_task("s_old") is None
    with sqlite3.connect(memory.MEMORY_DB_PATH) as conn:
        assert conn.execute("SELECT status FROM task_tombstones WHERE task_id='s_old'").fetchone() == ("completed",)
    # 두 번째 부팅은 멱등 — 묘비가 겹쳐도 오류 없음, 남은 행 그대로
    boot_common._cleanup_completed_tasks(base["tmp"], base["data"], "[t]")
    assert _statuses(base["project_db"]) == {"t_fresh": "completed", "t_pending_old": "pending"}


def test_prune_tolerates_db_without_tasks_table(tmp_path):
    empty = tmp_path / "x.db"
    sqlite3.connect(empty).close()
    assert boot_common._prune_terminal_tasks_in(empty) == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
