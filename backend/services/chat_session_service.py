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
    import threading
    def watch_rewind():
        while _running.get(key(binding)) is run and not run.cancelled.wait(.25):
            try:
                with sessions.connection(binding.db_path) as conn:
                    pending = conn.execute("SELECT 1 FROM conversation_rewinds WHERE session_id=? AND json_extract(body,'$.state')='quiescing'", (binding.session_id,)).fetchone()
                if pending:
                    run.cancelled.set()
                    return
            except Exception:
                return
    threading.Thread(target=watch_rewind, daemon=True).start()


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


def steering_history(store, sid):
    """접수 사건을 그대로 읽는다. 모델에 전달/처리됐다는 뜻으로 바꾸지 않는다."""
    import json
    with sessions.connection(store.path) as conn:
        store.require(conn, sid)
        rows = conn.execute("SELECT turn_id,created_at,payload FROM conversation_events "
                            "WHERE session_id=? AND json_extract(payload,'$.type')=? "
                            "AND coalesce(json_extract(payload,'$.source'),'user')='user' ORDER BY id",
                            (sid, "handoff.steer.accepted")).fetchall()
    return [{**json.loads(row["payload"]), "turn_id": row["turn_id"],
             "timestamp": row["created_at"]} for row in rows]


def steer(store, sid, turn_id, request_id, message):
    """세션·턴을 고정해 접수한다. 응답 유실 재전송은 영속 접수증으로 돌려준다."""
    from steer_inbox import post
    message = message.strip()
    receipt = {"session_id": sid, "turn_id": turn_id, "request_id": request_id}

    def prior_receipt():
        prior = next((row for row in steering_history(store, sid)
                      if row.get("request_id") == request_id), None)
        if prior is None:
            return None
        if prior["turn_id"] != turn_id or prior["instruction"] != message:
            return {**receipt, "accepted": False, "reason": "같은 요청 신원으로 다른 지시를 보낼 수 없습니다"}
        return {**receipt, "accepted": True}

    prior = prior_receipt()
    if prior:
        return prior
    run = _running.get((str(Path(store.path).resolve()), sid))
    if (not run or run.finished or run.cancelled.is_set()
            or run.session_binding.turn_id != turn_id):
        return {**receipt, "accepted": False,
                "reason": "대상 실행이 종료됐거나 중단 중입니다. 입력을 보존했으니 상태를 확인하고 다시 보내주세요."}
    agent, _, task = run.target
    if not agent or not task:
        return {**receipt, "accepted": False, "reason": "작업을 준비 중입니다. 잠시 후 다시 보내주세요."}
    try:
        count = post(agent, message, task, require_active=True, request_id=request_id)
        if not count:
            return {**receipt, "accepted": False, "reason": "추가 지시를 입력해주세요."}
    except ValueError as exc:
        # 다른 재전송이 먼저 접수되고 종료 경계가 닫힌 경우에도 원 접수증을 보존한다.
        return prior_receipt() or {**receipt, "accepted": False, "reason": str(exc)}
    return {**receipt, "accepted": True}


def snapshot(store, sid, before=None):
    result = store.history(sid, before)
    with sessions.connection(store.path) as conn:
        turn = conn.execute("SELECT * FROM conversation_turns WHERE session_id=? ORDER BY started_at DESC,id DESC LIMIT 1", (sid,)).fetchone()
        from turn_checkpoints import revision
        result['revision'] = revision(conn, sid)
        if result['revision'] and turn:
            cut = conn.execute("SELECT MAX(json_extract(body,'$.completed_at')) FROM conversation_rewinds WHERE session_id=? AND json_extract(body,'$.mode')!='files' AND json_extract(body,'$.state')='completed'", (sid,)).fetchone()[0]
            from datetime import datetime
            if cut and datetime.fromisoformat(turn['started_at']).timestamp() < cut:
                turn = None
        result["turn"] = dict(turn) if turn else None
        if result["turn"] is not None:
            result["turn"]["progress"] = _progress_view(result["turn"].get("progress"))
        result["events"] = []
        if turn:
            import json
            result["events"] = [json.loads(r[0]) for r in conn.execute(
                "SELECT payload FROM conversation_events WHERE session_id=? AND turn_id=? ORDER BY id", (sid, turn["id"]))]
    from conversation_sessions import Binding, state_directory
    import json
    state_dir = state_directory(Binding(store.path, sid, store.owner))
    result["steering"] = steering_history(store, sid) if not result.get("revision") else []
    result["panels"] = {}
    for name in ("todo", "question", "plan_mode"):
        try:
            result["panels"][name] = json.loads((state_dir / (name + "_state.json")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return result


def _progress_view(raw):
    """턴의 progress 칸(JSON 문자열) → dict + age_s(서버 시계 기준 마지막 움직임 경과) — 표면은 시계 차를 안 탄다."""
    if not raw:
        return None
    import json
    import time
    try:
        prog = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(prog, dict):
        return None
    try:
        prog["age_s"] = max(0.0, time.time() - float(prog.get("at") or 0))
    except (TypeError, ValueError):
        pass
    return prog


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
