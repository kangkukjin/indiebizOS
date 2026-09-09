"""기존 일일 순찰에 붙는 과제 생명주기·정합 검사. 새 스케줄러는 만들지 않는다."""
import sqlite3
import time

from pursuit_ledger import PursuitLedger


def ledgers():
    from runtime_utils import get_base_path
    from system_ai_memory import MEMORY_DB_PATH
    from agent_registry import runner_registry
    paths = {MEMORY_DB_PATH, *get_base_path().joinpath("projects").glob("*/conversations.db")}
    for runner in list(runner_registry.values()):
        if getattr(runner, "project_path", None):
            paths.add(runner.project_path / "conversations.db")
    for path in sorted(paths, key=str):
        if not path.exists():
            continue
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        try:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='pursuit'").fetchone():
                for (owner,) in c.execute("SELECT DISTINCT agent_key FROM pursuit"):
                    yield PursuitLedger(path, owner)
        finally:
            c.close()


def run_pursuit_check():
    errors, changed = [], 0
    for ledger in ledgers():
        ledger.recover()
        changed += ledger.maintain()
        with ledger.connect() as c:
            broken = c.execute("PRAGMA foreign_key_check").fetchall()
            errors.extend(str(tuple(r)) for r in broken if r[0].startswith("pursuit"))
            rows = c.execute("SELECT t.task_id FROM pursuit_turn t JOIN pursuit p ON p.id=t.pursuit_id "
                             "WHERE p.agent_key=? AND t.state!='applied' AND t.updated_at<?",
                             (ledger.agent_key, time.time() - 86400)).fetchall()
            errors.extend(f"미반영 과제 턴 {r[0]}" for r in rows)
    return {"node": "__telemetry__", "action": "pursuit", "success": not errors,
            "response_ms": 0, "data_quality": "ok" if not errors else "pending",
            "error_message": "; ".join(errors) or None, "changed": changed}
