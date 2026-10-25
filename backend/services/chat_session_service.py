"""세션 대상 해소·실행 수명. HTTP와 기존 WebSocket이 같은 저장/실행 계약을 쓴다."""
from pathlib import Path
import conversation_sessions as sessions

project_manager = None
_running = {}


def store_for(target="system_ai", project_id="", agent_id=""):
    if target in ("system_ai", "appmaker"):
        import system_ai_memory as memory
        memory.init_memory_db()
        return sessions.SessionStore(memory.MEMORY_DB_PATH, "conversations", target), {}
    if target != "agent" or not project_manager:
        raise ValueError("대화 대상을 찾을 수 없습니다")
    import yaml
    from conversation_db import ConversationDB
    path = project_manager.get_project_path(project_id)
    if not path or not (path / "agents.yaml").is_file():
        raise ValueError("프로젝트를 찾을 수 없습니다")
    agents = yaml.safe_load((path / "agents.yaml").read_text(encoding="utf-8")) or {}
    config = next((a for a in agents.get("agents", []) if str(a.get("id")) == str(agent_id)
                   or a.get("name") == agent_id), None)
    if not config:
        raise ValueError("에이전트를 찾을 수 없습니다")
    db = ConversationDB(str(path / "conversations.db"))
    user = db.get_or_create_agent("user", "human")
    agent = db.get_or_create_agent(config["name"], "ai_agent")
    return sessions.SessionStore(db.db_path, "messages", sessions.pair_owner(user, agent)), config


def from_data(data):
    target = "agent" if data.get("project_id") else ("appmaker" if data.get("role") == "appmaker" else "system_ai")
    return store_for(target, data.get("project_id", ""), data.get("agent_name", ""))[0]


def key(binding):
    return str(Path(binding.db_path).resolve()), binding.session_id


def attach(run, binding):
    run.session_binding = binding
    _running[key(binding)] = run


def detach(run):
    binding = getattr(run, "session_binding", None)
    if binding and _running.get(key(binding)) is run:
        _running.pop(key(binding), None)


def cancel(store, sid):
    with sessions.connection(store.path) as conn:
        store.require(conn, sid)
    run = _running.get((str(Path(store.path).resolve()), sid))
    if run:
        run.cancelled.set()
    return bool(run)


def snapshot(store, sid, before=None):
    result = store.history(sid, before)
    with sessions.connection(store.path) as conn:
        turn = conn.execute("SELECT * FROM conversation_turns WHERE session_id=? ORDER BY started_at DESC,id DESC LIMIT 1", (sid,)).fetchone()
        result["turn"] = dict(turn) if turn else None
        result["events"] = []
        if turn:
            import json
            result["events"] = [json.loads(r[0]) for r in conn.execute(
                "SELECT payload FROM conversation_events WHERE session_id=? AND turn_id=? ORDER BY id", (sid, turn["id"]))]
    from conversation_sessions import Binding, state_directory
    import json
    state_dir = state_directory(Binding(store.path, sid, store.owner))
    result["panels"] = {}
    for name in ("todo", "question", "plan_mode"):
        try:
            result["panels"][name] = json.loads((state_dir / (name + "_state.json")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return result


def respond_panel(binding, action, message):
    import json
    directory = sessions.state_directory(binding)
    name = "question" if action == "answer" else "plan_mode"
    path = directory / (name + "_state.json")
    state = json.loads(path.read_text(encoding="utf-8"))
    if action == "answer":
        state.update(status="answered", answer=message)
    else:
        state.update(active=action != "approve", phase="approved" if action == "approve" else "designing")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def reset_cli_session(target="system_ai", project_id="", agent_id=""):
    """기존 UI의 현재 대화 소유권을 자연어 초기화와 같은 CLI 키로 해소한다."""
    from providers import clear_cli_sessions_for_agent
    store, config = store_for(target, project_id, agent_id)
    with sessions.connection(store.path) as conn:
        sid = sessions.resolve(conn, store.path, store.owner, store.table)
    registry = f"{project_id}:{config.get('id', agent_id)}" if target == "agent" else "system:system_ai"
    return clear_cli_sessions_for_agent(registry + "@session:" + sid)
