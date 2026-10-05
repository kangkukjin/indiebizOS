"""agent_lifecycle.py — 프로젝트 에이전트의 생애주기(만들기·고치기·지우기·시작·중지·역할·메모) (2026-10-05, 설치 목록 ⑩).

조종실(매니저 창)의 HTTP 라우트(api_agents)가 agents.yaml 과 역할·메모 파일을 라우트 본문에서 직접 다뤄 IBL 이 닿지
못했다. 그 논리를 여기로 내려 라우트와 `[others:agents]{op: create|update|delete|start|stop|role|note}` 가 **같은 함수**를
부른다. 실행 중 러너 명부는 datastore.agent_registry.agent_runners(한 곳).
"""
import uuid
from datetime import datetime
from pathlib import Path

import yaml


def _project_path(project_id: str) -> Path:
    from project_manager import ProjectManager
    return ProjectManager().get_project_path(project_id)


def _load(project_path: Path) -> dict:
    f = project_path / "agents.yaml"
    if not f.exists():
        return {"agents": [], "common": {}}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {"agents": [], "common": {}}


def _save(project_path: Path, data: dict) -> None:
    (project_path / "agents.yaml").write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")


def _apply_fields(agent: dict, name=None, type=None, allowed_nodes=None, allowed_tools=None, channel=None, email=None) -> dict:
    if name is not None:
        agent["name"] = name
    if type is not None:
        agent["type"] = type
    agent.pop("ai", None)   # per-agent 모델 설정 폐지 — 모델은 기어가 단독 결정
    if allowed_nodes is not None:
        agent["allowed_nodes"] = list(allowed_nodes)
        agent["ibl_only"] = True
        agent.pop("allowed_tools", None)
    elif allowed_tools is not None:
        agent["allowed_tools"] = list(allowed_tools)
    if (type or agent.get("type")) == "external" and channel:
        agent["channel"] = channel
        if email:
            agent["email"] = email
    return agent


def create_agent(project_id: str, name: str, type: str = "ai_agent", role: str = None, allowed_nodes=None,
                 allowed_tools=None, channel: str = None, email: str = None) -> dict:
    pp = _project_path(project_id)
    data = _load(pp)
    new = _apply_fields({"id": f"agent_{uuid.uuid4().hex[:8]}", "active": True}, name=name, type=type,
                        allowed_nodes=allowed_nodes, allowed_tools=allowed_tools, channel=channel, email=email)
    data.setdefault("agents", []).append(new)
    _save(pp, data)
    if role:
        (pp / f"agent_{name}_role.txt").write_text(role, encoding="utf-8")
    return new


def update_agent(project_id: str, agent_id: str, **fields) -> dict:
    pp = _project_path(project_id)
    data = _load(pp)
    role = fields.pop("role", None)
    for i, agent in enumerate(data.get("agents", [])):
        if agent.get("id") != agent_id:
            continue
        old_name = agent.get("name", "")
        data["agents"][i] = _apply_fields(agent, **fields)
        new_name = data["agents"][i].get("name", old_name)
        if old_name and old_name != new_name:
            # 이름이 바뀌면 역할·메모 파일도 따라간다(옛 라우트는 role 을 함께 줄 때만 옮겨 고아 파일이 남았다)
            for suffix in ("role", "note"):
                old_f, new_f = pp / f"agent_{old_name}_{suffix}.txt", pp / f"agent_{new_name}_{suffix}.txt"
                if old_f.exists() and not new_f.exists():
                    old_f.rename(new_f)
                elif old_f.exists():
                    old_f.unlink()
        if role is not None:
            (pp / f"agent_{new_name}_role.txt").write_text(role, encoding="utf-8")
        _save(pp, data)
        return data["agents"][i]
    raise KeyError(f"에이전트 '{agent_id}' 를 찾을 수 없습니다")


def delete_agent(project_id: str, agent_id: str) -> str:
    pp = _project_path(project_id)
    data = _load(pp)
    for i, agent in enumerate(data.get("agents", [])):
        if agent.get("id") == agent_id:
            name = agent.get("name")
            del data["agents"][i]
            _save(pp, data)
            for suffix in ("role", "note"):
                f = pp / f"agent_{name}_{suffix}.txt"
                if f.exists():
                    f.unlink()
            return name
    raise KeyError(f"에이전트 '{agent_id}' 를 찾을 수 없습니다")


def read_text(project_id: str, agent_id: str, kind: str) -> str:
    pp = _project_path(project_id)
    agent = next((a for a in _load(pp).get("agents", []) if a.get("id") == agent_id), None)
    if not agent:
        raise KeyError(f"에이전트 '{agent_id}' 를 찾을 수 없습니다")
    f = pp / f"agent_{agent.get('name')}_{kind}.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def write_text(project_id: str, agent_id: str, kind: str, text: str) -> None:
    pp = _project_path(project_id)
    agent = next((a for a in _load(pp).get("agents", []) if a.get("id") == agent_id), None)
    if not agent:
        raise KeyError(f"에이전트 '{agent_id}' 를 찾을 수 없습니다")
    (pp / f"agent_{agent.get('name')}_{kind}.txt").write_text(text or "", encoding="utf-8")


def start_agent(project_id: str, agent_id: str) -> dict:
    from agent_registry import agent_runners
    from agent_runner import AgentRunner
    pp = _project_path(project_id)
    data = _load(pp)
    agent_config = next((a for a in data.get("agents", []) if a.get("id") == agent_id), None)
    if not agent_config:
        raise KeyError(f"에이전트 '{agent_id}' 를 찾을 수 없습니다")
    runners = agent_runners.setdefault(project_id, {})
    if agent_id in runners and getattr(runners[agent_id].get("runner"), "running", False):
        return {"status": "already_running", "agent_id": agent_id}
    agent_config["_project_path"] = str(pp)
    agent_config["_project_id"] = project_id
    runner = AgentRunner(agent_config, data.get("common", {}))
    runner.start()
    runners[agent_id] = {"runner": runner, "config": agent_config, "running": True,
                         "started_at": datetime.now().isoformat()}
    return {"status": "started", "agent_id": agent_id, "name": agent_config.get("name")}


def stop_agent(project_id: str, agent_id: str) -> dict:
    from agent_registry import agent_runners
    entry = (agent_runners.get(project_id) or {}).get(agent_id)
    if not entry:
        return {"status": "not_running", "agent_id": agent_id}
    runner = entry.get("runner")
    if runner:
        runner.stop()
    del agent_runners[project_id][agent_id]
    return {"status": "stopped", "agent_id": agent_id}


def _split(params: dict):
    """agent_id 는 '프로젝트/에이전트id' 또는 project_id 와 함께 — 두 쓰임을 모두 받는다."""
    raw = str(params.get("agent_id") or "").strip()
    project_id = str(params.get("project_id") or "").strip()
    if "/" in raw and not project_id:
        project_id, raw = raw.split("/", 1)
    return project_id, raw


def agents_op(op: str, params: dict) -> dict:
    """[others:agents] 의 생애주기 op (list/info 는 라우터의 기존 능력)."""
    project_id, agent_id = _split(params)
    if not project_id:
        return {"success": False, "error": f"{op} 에는 project_id(또는 '프로젝트/에이전트' 형식의 agent_id)가 필요합니다"}
    try:
        if op == "create":
            name = (params.get("name") or "").strip()
            if not name:
                return {"success": False, "error": "create 에는 name 이 필요합니다"}
            agent = create_agent(project_id, name, type=params.get("type") or "ai_agent", role=params.get("role"),
                                 allowed_nodes=params.get("allowed_nodes"), allowed_tools=params.get("allowed_tools"),
                                 channel=params.get("channel"), email=params.get("email"))
            return {"success": True, "project_id": project_id, "agent": agent}
        if not agent_id:
            return {"success": False, "error": f"{op} 에는 agent_id 가 필요합니다"}
        if op == "update":
            fields = {k: params[k] for k in ("name", "type", "role", "allowed_nodes", "allowed_tools", "channel", "email") if params.get(k) is not None}
            if not fields:
                return {"success": False, "error": "update 에 바꿀 필드가 없습니다"}
            return {"success": True, "project_id": project_id, "agent": update_agent(project_id, agent_id, **fields)}
        if op == "delete":
            return {"success": True, "project_id": project_id, "deleted": agent_id, "name": delete_agent(project_id, agent_id)}
        if op == "start":
            return {"success": True, **start_agent(project_id, agent_id)}
        if op == "stop":
            return {"success": True, **stop_agent(project_id, agent_id)}
        if op in ("role", "note"):
            if params.get("text") is not None:
                write_text(project_id, agent_id, op, str(params["text"]))
                return {"success": True, "project_id": project_id, "agent_id": agent_id, op: str(params["text"])}
            return {"success": True, "project_id": project_id, "agent_id": agent_id, op: read_text(project_id, agent_id, op)}
    except KeyError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|info|create|update|delete|start|stop|role|note)"}
