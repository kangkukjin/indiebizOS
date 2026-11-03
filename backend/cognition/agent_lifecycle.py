"""agent_lifecycle.py — 프로젝트 에이전트의 생애주기(만들기·고치기·지우기·시작·중지·역할·메모) (2026-10-05, 설치 목록 ⑩).

조종실(매니저 창)의 HTTP 라우트(api_agents)가 agents.yaml 과 역할·메모 파일을 라우트 본문에서 직접 다뤄 IBL 이 닿지
못했다. 그 논리를 여기로 내려 라우트와 `[others:agents]{op: create|update|delete|start|stop|role|note}` 가 **같은 함수**를
부른다. 실행 중 러너 명부는 datastore.agent_registry.agent_runners(한 곳).
"""
import os
import tempfile
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
    content = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    fd, temporary = tempfile.mkstemp(prefix=".agents-", dir=project_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, project_path / "agents.yaml")
    finally:
        Path(temporary).unlink(missing_ok=True)


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
    _check_name(data, None, name)
    role_path = _text_path(pp, new, "role")
    note_path = _text_path(pp, new, "note")
    if role_path.exists() or note_path.exists():
        raise AgentConflictError("새 에이전트의 역할 또는 메모 파일이 이미 있습니다.")
    data.setdefault("agents", []).append(new)
    created = False
    try:
        if role is not None:
            with role_path.open("x", encoding="utf-8") as stream:
                created = True
                stream.write(role)
        _save(pp, data)
    except BaseException:
        if created:
            role_path.unlink(missing_ok=True)
        raise
    return new


class AgentConfigMissingError(FileNotFoundError):
    """설정 파일의 부재와 실제 파일 I/O 실패를 구분한다."""


class AgentConflictError(ValueError):
    """저장 신원이나 텍스트의 소유권이 불명확하여 변경하지 않았다."""


def _resolve(data: dict, agent_id: str, *, by_name=False) -> dict:
    agents = data.get("agents", [])
    matches = [a for a in agents if a.get("id") == agent_id]
    if not matches and by_name:
        matches = [a for a in agents if a.get("name") == agent_id]
    if len(matches) > 1:
        raise AgentConflictError("에이전트 식별자가 중복되어 선택할 수 없습니다.")
    if not matches:
        raise KeyError(f"에이전트 '{agent_id}' 를 찾을 수 없습니다")
    return matches[0]


def _text_path(pp: Path, agent: dict, kind: str) -> Path:
    if kind not in ("role", "note"):
        raise ValueError("텍스트 종류는 role 또는 note여야 합니다.")
    name = agent.get("name", agent["id"])
    if not isinstance(name, str) or not name or Path(name).name != name or "\\" in name:
        raise AgentConflictError("에이전트 이름에 경로를 사용할 수 없습니다.")
    if "name" not in agent and (pp / f"agent_None_{kind}.txt").exists():
        raise AgentConflictError("이름 없는 에이전트의 이전 텍스트를 확인해야 합니다.")
    path = pp / f"agent_{name}_{kind}.txt"
    if path.is_symlink():
        raise AgentConflictError("에이전트 텍스트의 심볼릭 링크를 확인해야 합니다.")
    return path


def _check_name(data, agent, name):
    if any(a is not agent and a.get("name", a.get("id")) == name for a in data.get("agents", [])):
        raise AgentConflictError("같은 표시 이름의 에이전트가 이미 있습니다.")


def update_agent(project_id: str, agent_id: str, **fields) -> dict:
    pp = _project_path(project_id)
    data = _load(pp)
    agent = _resolve(data, agent_id)
    role = fields.pop("role", None)
    updated = _apply_fields(dict(agent), **fields)
    _check_name(data, agent, updated.get("name", agent_id))
    pairs = [(_text_path(pp, agent, kind), _text_path(pp, updated, kind))
             for kind in ("role", "note")]
    renamed = pairs[0][0] != pairs[0][1]
    if renamed and any(dst.exists() for src, dst in pairs):
        raise AgentConflictError("개명 대상의 역할 또는 메모 파일이 이미 있습니다.")
    created = []
    originals = {}
    role_before = None
    role_path = pairs[0][1]
    try:
        if renamed:
            for index, (src, dst) in enumerate(pairs):
                if src.exists():
                    originals[src] = src.read_bytes()
                content = role.encode("utf-8") if index == 0 and role is not None else originals.get(src)
                if content is not None:
                    try:
                        with dst.open("xb") as stream:
                            created.append((dst, os.fstat(stream.fileno()).st_ino))
                            stream.write(content)
                    except FileExistsError as exc:
                        raise AgentConflictError("개명 중 목적지 파일이 생겨 변경을 중단했습니다.") from exc
        elif role is not None:
            role_before = role_path.read_bytes() if role_path.exists() else None
            role_path.write_text(role, encoding="utf-8")
        data["agents"][data["agents"].index(agent)] = updated
        _save(pp, data)
    except BaseException:
        for path, inode in created:
            if path.exists() and path.stat().st_ino == inode:
                path.unlink()
        if not renamed and role is not None:
            if role_before is None:
                role_path.unlink(missing_ok=True)
            else:
                role_path.write_bytes(role_before)
        raise
    for src, content in originals.items():
        if src.exists() and src.read_bytes() == content:
            src.unlink()
    return updated


def delete_agent(project_id: str, agent_id: str) -> str:
    pp = _project_path(project_id)
    data = _load(pp)
    agent = _resolve(data, agent_id)
    paths = [_text_path(pp, agent, kind) for kind in ("role", "note")]
    name = agent.get("name", agent_id)
    _check_name(data, agent, name)
    data["agents"].remove(agent)
    _save(pp, data)
    for path in paths:
        path.unlink(missing_ok=True)
    return name


def text_record(project_id: str, agent_id: str, kind: str, *, text=None,
                project_path=None) -> dict:
    """입구가 설정을 재조회하지 않도록 공개 이름과 본문만 반환한다."""
    pp = Path(project_path) if project_path is not None else _project_path(project_id)
    if not (pp / "agents.yaml").exists():
        raise AgentConfigMissingError("에이전트 설정을 찾을 수 없습니다.")
    data = _load(pp)
    agent = _resolve(data, agent_id)
    _check_name(data, agent, agent.get("name", agent_id))
    path = _text_path(pp, agent, kind)
    if text is not None:
        path.write_text(text, encoding="utf-8")
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {kind: content, "agent_name": agent.get("name", agent_id)}


def read_text(project_id: str, agent_id: str, kind: str) -> str:
    return text_record(project_id, agent_id, kind)[kind]


def write_text(project_id: str, agent_id: str, kind: str, text: str) -> None:
    text_record(project_id, agent_id, kind, text=text or "")


def start_agent(project_id: str, agent_id: str) -> dict:
    from agent_registry import agent_runners
    from agent_runner import AgentRunner
    pp = _project_path(project_id)
    data = _load(pp)
    agent_config = _resolve(data, agent_id)
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
    except (KeyError, AgentConfigMissingError, AgentConflictError) as exc:
        return {"success": False, "error": str(exc)}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|info|create|update|delete|start|stop|role|note)"}
