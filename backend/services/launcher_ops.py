"""launcher_ops.py — 런처 항목(프로젝트·폴더·휴지통·스위치)의 생애주기 낱말 (2026-10-05, 설치 목록 ⑩).

서비스층: project_manager·switch_manager(datastore)와 system_hooks(생성·삭제 훅)를 부른다. 조립 루트(boot_common)가 라우터 능력으로 주입.

런처 항목은 파일이 아니다 — projects.json 한 목록에 project/folder 가 parent_folder·in_trash 로 살고(project_manager),
스위치는 switches.json(switch_manager), 채팅방은 multi_chat.db 다. 그래서 파일 낱말(self:list/move/delete)이 닿지 못했고
매니저·폴더 창·휴지통이 REST 로만 열려 있었다. 이 모듈은 그 저장소 함수들을 **그대로** 부르는 얇은 op 디스패처다 —
논리를 새로 만들지 않는다(조종실 HTTP 라우트와 같은 함수).
권한: 쓰기 op 는 사전의 `requires`(owner, 파괴적이면 human_confirm)가 실행기 관문에서 집행한다 — 여기서 다시 묻지 않는다.
"""
from typing import Any


def _pm():
    from project_manager import ProjectManager
    return ProjectManager()


def _sm():
    from switch_manager import SwitchManager
    return SwitchManager()


def _need(params: dict, key: str, *alts: str):
    for k in (key,) + alts:
        v = params.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return None


def _items(rows: list, **extra) -> dict:
    return {"success": True, "items": rows, "count": len(rows), **extra}


def _ok(result, **extra) -> dict:
    """저장소 반환(dict | bool | None)을 한 봉투로 — dict 면 펼치고, 거짓이면 실패."""
    if isinstance(result, dict):
        return {"success": result.get("success", True), **result, **extra}
    if result is False:
        return {"success": False, "error": "저장소가 거절했습니다(없는 항목이거나 상태가 맞지 않음)", **extra}
    return {"success": True, **extra}


# ── 승인 전 대상 존재 확인(requires.exists, 긴문장 28회차 L28-4) — 관문이 사람에게 묻기 전에 부른다 ──
# 인자는 별칭 정규화 전의 원 인자라 _need 로 별칭까지 읽는다. None = 있음, 실패 봉투 = 핸들러가 냈을 같은 거절.

def switch_exists(params: dict):
    sid = _need(params or {}, "switch_id", "id")
    if not sid:
        return {"success": False, "error": "delete 에는 switch_id 가 필요합니다"}
    if not _sm().get_switch(sid):
        return {"success": False, "error": f"스위치 없음: {sid}"}
    return None


def project_exists(params: dict):
    pid = _need(params or {}, "project_id", "id")
    if not pid:
        return {"success": False, "error": "delete 에는 project_id 가 필요합니다"}
    if not any(p.get("id") == pid for p in _pm().list_projects()):
        return {"success": False, "error": f"프로젝트 없음: {pid}"}
    return None


# ── 프로젝트 ──────────────────────────────────────────────────────────────────

def project_op(params: dict) -> Any:
    op = (params.get("op") or "list").strip()
    pm = _pm()
    if op == "list":
        rows = [p for p in pm.list_projects() if not p.get("in_trash") and p.get("type", "project") != "folder"]
        return _items(rows)
    if op == "templates":
        return _items(pm.list_templates())
    if op == "create":
        name = _need(params, "name")
        if not name:
            return {"success": False, "error": "name 이 필요합니다"}
        try:
            row = pm.create_project(name, parent_folder=params.get("parent_folder") or None,
                                    template_name=params.get("template") or "기본")
        except (ValueError, FileExistsError) as exc:
            return {"success": False, "error": str(exc)}
        try:
            from system_hooks import on_project_created
            on_project_created(row, pm.list_projects())   # 조종실 POST /projects 와 같은 훅(inventory·overview 갱신)
        except Exception:
            pass
        return {"success": True, "project": row}
    pid = _need(params, "project_id", "id", "name")
    if not pid:
        return {"success": False, "error": f"{op} 에는 project_id 가 필요합니다"}
    try:
        if op == "rename":
            new = _need(params, "new_name", "name")
            if not new:
                return {"success": False, "error": "new_name 이 필요합니다"}
            return {"success": True, "project": pm.rename_item(pid, new)}
        if op == "copy":
            return {"success": True, "project": pm.copy_item(pid, params.get("new_name") or None, params.get("parent_folder") or None)}
        if op == "move":
            folder = params.get("folder_id") or None
            pm.move_to_folder(pid, folder) if folder else pm.move_out_of_folder(pid)
            return {"success": True, "project_id": pid, "folder_id": folder}
        if op == "trash":
            return _ok(pm.move_to_trash(pid), project_id=pid)
        if op == "delete":
            pm.delete_project(pid, move_to_trash=False)
            try:
                from system_hooks import on_project_deleted
                on_project_deleted(pid, pm.list_projects())
            except Exception:
                pass
            return {"success": True, "deleted": pid, "permanent": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        return {"success": False, "error": str(exc)}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|templates|create|rename|copy|move|trash|delete)"}


# ── 런처 폴더 ─────────────────────────────────────────────────────────────────

def folder_op(params: dict) -> Any:
    op = (params.get("op") or "list").strip()
    pm = _pm()
    if op == "list":
        rows = [p for p in pm.list_projects() if p.get("type") == "folder" and not p.get("in_trash")]
        return _items(rows)
    if op == "create":
        name = _need(params, "name")
        if not name:
            return {"success": False, "error": "name 이 필요합니다"}
        try:
            return {"success": True, "folder": pm.create_folder(name, parent_folder=params.get("parent_folder") or None)}
        except (ValueError, FileExistsError) as exc:
            return {"success": False, "error": str(exc)}
    fid = _need(params, "folder_id", "id")
    if not fid:
        return {"success": False, "error": f"{op} 에는 folder_id 가 필요합니다"}
    try:
        if op == "items":
            return _items(pm.get_folder_items(fid), folder_id=fid)
        if op == "rename":
            new = _need(params, "new_name", "name")
            if not new:
                return {"success": False, "error": "new_name 이 필요합니다"}
            return {"success": True, "folder": pm.rename_item(fid, new)}
        if op == "move":
            parent = params.get("parent_folder") or None
            pm.move_to_folder(fid, parent) if parent else pm.move_out_of_folder(fid)
            return {"success": True, "folder_id": fid, "parent_folder": parent}
        if op == "trash":
            return _ok(pm.move_to_trash(fid), folder_id=fid)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        return {"success": False, "error": str(exc)}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|create|items|rename|move|trash)"}


# ── 휴지통(프로젝트·폴더·스위치·채팅방 공통) ─────────────────────────────────

def _chat_mgr():
    try:
        from chat_room_ops import get_manager
        return get_manager()
    except Exception:
        return None


def trash_op(params: dict) -> Any:
    op = (params.get("op") or "list").strip()
    pm, sm = _pm(), _sm()
    if op == "list":
        rows = [{**p, "item_type": "folder" if p.get("type") == "folder" else "project"} for p in pm.list_trash()]
        rows += [{**s, "item_type": "switch"} for s in sm.list_trashed_switches()]
        cm = _chat_mgr()
        if cm is not None:
            rows += [{**r, "item_type": "chat_room"} for r in cm.list_trashed_rooms()]
        return _items(rows)
    if op == "restore":
        iid = _need(params, "item_id", "id")
        kind = (params.get("item_type") or "project").strip()
        if not iid:
            return {"success": False, "error": "restore 에는 item_id 가 필요합니다"}
        try:
            if kind in ("project", "folder"):
                return _ok(pm.restore_from_trash(iid), item_id=iid)
            if kind == "switch":
                return _ok(sm.restore_from_trash(iid), item_id=iid)
            if kind == "chat_room":
                cm = _chat_mgr()
                if cm is None:
                    return {"success": False, "error": "채팅방 관리자가 준비되지 않았습니다"}
                return _ok(cm.restore_from_trash(iid), item_id=iid)
        except (ValueError, KeyError) as exc:
            return {"success": False, "error": str(exc)}
        return {"success": False, "error": "item_type 은 project|folder|switch|chat_room"}
    if op == "empty":
        counts = {"projects": len(pm.list_trash()), "switches": len(sm.list_trashed_switches())}
        pm.empty_trash(); sm.empty_trash()
        cm = _chat_mgr()
        if cm is not None:
            counts["chat_rooms"] = cm.empty_trash()
        return {"success": True, "emptied": counts}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|restore|empty)"}


# ── 스위치(생애주기 — list/run 은 라우터의 기존 능력) ────────────────────────────

def build_switch_config(config: dict) -> dict:
    """스위치는 그 프로젝트의 **설정**(역할·노드·공통 프롬프트)을 얼린다 — 모델은 얼리지 않는다(기어가 런타임에 정함).
    조종실 POST /switches 와 같은 복사 규칙(api_switches 가 이 함수를 부른다)."""
    import yaml
    config = dict(config or {})
    project_id = config.get("projectId")
    agent_name = config.get("agentName")
    if not project_id:
        return config
    agents_file = _pm().get_project_path(project_id) / "agents.yaml"
    if not agents_file.exists():
        return config
    project_config = yaml.safe_load(agents_file.read_text(encoding="utf-8")) or {}
    agents = project_config.get("agents", [])
    agent = next((a for a in agents if a.get("name") == agent_name or a.get("id") == agent_name), None)
    if not agent and agents:
        agent = agents[0]
    if agent:
        config["agent_name"] = agent.get("name", agent_name)
        config["agent_role"] = agent.get("role", "") or agent.get("role_description", "")
        if agent.get("allowed_nodes") and not config.get("allowed_nodes"):
            config["allowed_nodes"] = agent["allowed_nodes"]
        if agent.get("id"):
            config["agent_id"] = agent["id"]
        non_model = {k: v for k, v in (agent.get("ai") or {}).items() if k not in ("provider", "model", "api_key", "apiKey")}
        if non_model:
            config["ai"] = non_model
    config["common_prompt"] = project_config.get("common", {}).get("common_prompt", "")
    return config


def switch_manage_op(params: dict) -> Any:
    op = (params.get("op") or "").strip()
    sm = _sm()
    if op == "create":
        name, command = _need(params, "name"), _need(params, "command")
        if not name or not command:
            return {"success": False, "error": "create 에는 name 과 command 가 필요합니다"}
        config = {"projectId": params.get("project_id"), "agentName": params.get("agent_name") or params.get("agent_id")}
        config.update(params.get("config") or {})
        row = sm.create_switch(name=name, command=command, config=build_switch_config(config),
                               icon=params.get("icon") or "⚡", description=params.get("description") or "")
        return {"success": True, "switch": row}
    sid = _need(params, "switch_id", "id")
    if not sid:
        return {"success": False, "error": f"{op} 에는 switch_id 가 필요합니다"}
    if not sm.get_switch(sid):
        return {"success": False, "error": f"스위치 없음: {sid}"}
    if op == "info":
        return {"success": True, "switch": sm.get_switch(sid)}
    if op == "update":
        updates = {k: params[k] for k in ("name", "command", "icon", "description", "config") if params.get(k) not in (None, "")}
        if not updates:
            return {"success": False, "error": "update 에 바꿀 필드(name|command|icon|description|config)가 없습니다"}
        return {"success": True, "switch": sm.update_switch(sid, updates)}
    if op == "rename":
        new = _need(params, "new_name", "name")
        if not new:
            return {"success": False, "error": "new_name 이 필요합니다"}
        return {"success": True, "switch": sm.rename_switch(sid, new)}
    if op == "copy":
        return {"success": True, "switch": sm.copy_switch(sid)}
    if op == "trash":
        return _ok(sm.move_to_trash(sid), switch_id=sid)
    if op == "delete":
        return {"success": bool(sm.delete_switch(sid)), "deleted": sid, "permanent": True}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|run|info|create|update|rename|copy|trash|delete)"}
