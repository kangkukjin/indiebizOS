"""재기동 제어자의 ACTIVE 통지에서 영속 수리 인계를 소비한다.

웹 요청/사용자 재입력 없이도 같은 에이전트의 기존 명령 경로로 돌아간다.
파일 잠금과 runtime lease는 중복 실행 및 재개 도중 재기동을 막는다.
"""
import asyncio
import threading
import time

from repair_continuation import (TERMINAL, cancelled, claim, directory, outcome, read, resuming,
                                 resume_context, save)
from restart_protocol import OwnerLock, read_json
from runtime_utils import get_base_path

_lock = threading.Lock()
_last_scan = 0.0


def _project_runner(row):
    from api_agents import start_agent
    from agent_registry import agent_runners
    project, agent = row["project_id"], row["agent_id"]
    info = agent_runners.get(project, {}).get(agent, {})
    runner = info.get("runner")
    if runner is None or not runner.running:
        asyncio.run(start_agent(project, agent, None))
        runner = agent_runners[project][agent]["runner"]
    return runner


def _execute(row):
    if not row["system_ai"]:
        from api_agents import _run_agent_command
        return _run_agent_command(row["project_id"], row["agent_id"], _project_runner(row),
                                  row["goal"], continuation=row)
    from system_ai_core import process_system_ai_message
    from system_ai_memory import (create_task, get_task, complete_task, save_conversation,
                                  get_history_for_ai)
    from thread_context import actor_context, get_goal_eval_outcome
    from episode_logger import EpisodeLogger
    task = row["resume_task_id"]
    with actor_context(agent_id="system_ai", task_id=task, origin="user"):
        try:
            EpisodeLogger.start_episode("시스템 AI", row["goal"], task_id=task)
            if not get_task(task):
                create_task(task, "user@gui", "system_ai", row["goal"], parent_task_id=row["task_id"])
            response, images = process_system_ai_message(
                row["goal"], get_history_for_ai(limit=7),
                extra_role=resume_context(row), utterance_author="owner", cancel_check=lambda: cancelled(row))
            evaluation = get_goal_eval_outcome() or {}
            save_conversation("assistant", response, images=images)
            complete_task(task, response)
            return {"response": response, "evaluation": evaluation}
        finally:
            EpisodeLogger.end_episode()


def _deliver_blocked(row):
    text = "[자기수리 미완료] " + row["reason"]
    if row["system_ai"]:
        from system_ai_memory import save_conversation
        save_conversation("assistant", text)
    else:
        from api_agents import project_manager
        from conversation_db import ConversationDB
        path = project_manager.get_project_path(row["project_id"])
        db = ConversationDB(str(path / "conversations.db"))
        user = db.get_or_create_agent("user", "human")
        # 기존 대화의 이름을 사용한다. 에이전트가 없어도 원장에는 차단이 남는다.
        import yaml
        config = yaml.safe_load((path / "agents.yaml").read_text())
        name = next(a["name"] for a in config["agents"] if a["id"] == row["agent_id"])
        agent = db.get_or_create_agent(name, "ai_agent")
        db.save_message(agent, user, text, contact_type="gui")


def _settle(row, status, response, base):
    """마지막 구간이 끝나면 부모 구간의 대기도 함께 해소한다."""
    from api_agents import project_manager
    from conversation_db import ConversationDB
    from system_ai_memory import MEMORY_DB_PATH
    db_path = (MEMORY_DB_PATH if row["system_ai"] else
               project_manager.get_project_path(row["project_id"]) / "conversations.db")
    db = ConversationDB(str(db_path))
    tasks = {row.get("resume_task_id")}
    for path in directory(base).glob("*.json"):
        item = read_json(path)
        if item and item.get("root_task_id") == row["root_task_id"]:
            # 새 적용 예약을 방금 만든 자식은 호출자가 여기로 오지 않는다.
            save({**item, "status": status}, base)
            tasks.update((item["task_id"], item.get("resume_task_id")))
    with db.get_connection() as conn:
        for task in tasks - {None}:
            conn.execute("UPDATE tasks SET status=?, result=?, completed_at=CURRENT_TIMESTAMP WHERE task_id=?",
                         (status, response[:500], task))
        conn.commit()


def process_pending(base, generation, execute=_execute):
    """파일당 한 소유자. 프로세스 사망 뒤에는 같은 인계를 현재 상태 대조부터 재개한다."""
    for path in sorted(directory(base).glob("*.json")):
        lock = OwnerLock(path.with_suffix(".lock"))
        if not lock.acquire():
            continue
        try:
            row = read_json(path)
            if (not row or row.get("status") in TERMINAL or row.get("authorized_origin") != "user"
                    or row.get("status") == "running" and row.get("generation") == generation):
                continue
            if cancelled(row, base):
                _settle(row, "cancelled", "사용자가 수리 재개를 취소했습니다.", base)
                continue
            # 자식 예약을 저장한 직후 부모 상태 기록 전에 죽은 경우에도 중복 재개 금지.
            if any((read_json(p) or {}).get("parent_task_id") == row["task_id"]
                   for p in directory(base).glob("*.json")):
                save({**row, "status": "continued"}, base)
                continue
            result = outcome(row, base)
            if result is None:
                continue
            row = claim(row, generation, result, base)
            if row["status"] == "blocked":
                _deliver_blocked(row)
                _settle(row, "blocked", row["reason"], base)
                continue
            with resuming(row):
                answer = execute(row)
            current = read(row["task_id"], base) or row
            if cancelled(current, base):
                _settle(row, "cancelled", "사용자가 수리 재개를 취소했습니다.", base)
                continue
            if current.get("status") == "continued":
                continue
            evaluation = answer.get("evaluation") or {}
            status = "completed" if evaluation.get("achieved") else "blocked"
            if answer.get("cancelled"):
                status = "cancelled"
            response = answer.get("response", "")
            save({**current, "status": status, "evaluation": evaluation,
                  "reason": evaluation.get("reason", "완료 검증을 확인하지 못했습니다")}, base)
            if status == "blocked":
                _deliver_blocked(read(row["task_id"], base))
            _settle(row, status, response, base)
        except Exception as exc:
            # 실패를 '완료'로 만들거나 매 activate마다 다시 모델을 호출하지 않는다.
            from logging_utils import mask_secrets
            row = read_json(path)
            if row:
                row.update(status="blocked", reason=mask_secrets(str(exc)))
                save(row, base)
                try:
                    _deliver_blocked(row)
                    _settle(row, "blocked", row["reason"], base)
                except Exception:
                    pass
            print(f"[수리 재개] 인계 실패: {mask_secrets(str(exc))}")
        finally:
            lock.close()


def kick():
    """activate는 반복된다. 적용 검증이 끝난 뒤의 ACTIVE에서만 독립 root를 예약한다."""
    import runtime_work
    global _last_scan
    work = runtime_work.registry()
    base = get_base_path()
    if (not work or work.phase != "ACTIVE" or time.monotonic() - _last_scan < 5
            or not directory(base).exists() or not _lock.acquire(False)):
        return
    try:
        _last_scan = time.monotonic()
        if not any((read_json(p) or {}).get("status") not in TERMINAL for p in directory(base).glob("*.json")):
            _lock.release()
            return
        snapshot = work.snapshot()
        if snapshot.get("active_roots") or snapshot.get("active_children"):
            _lock.release()
            return
        def worker():
            try:
                process_pending(base, work.generation)
            finally:
                _lock.release()
        with runtime_work.service_scope():
            callback = runtime_work.bind_lease(worker, "repair-continuation")
            try:
                threading.Thread(target=callback, daemon=True, name="repair-continuation").start()
            except Exception:
                callback.release()
                raise
    except Exception:
        _lock.release()
        raise
