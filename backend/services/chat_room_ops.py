"""chat_room_ops.py — 멀티채팅 채팅방의 생애주기·참가자·발화 낱말 `[others:chat_room]` (2026-10-05, 설치 목록 ⑩).

저장소는 multi_chat_manager(multi_chat.db) 그대로 — 조종실 HTTP(api_multi_chat)와 같은 매니저 싱글턴을 쓴다(set_manager).
조립 루트(boot_common)가 chat_room_op 을 시스템 라우터 능력으로 주입한다.
"""
from typing import Any, Optional

_manager = None
MESSAGES_MAX = 500   # 한 번에 돌려주는 메시지 상한 — 넘는 요청은 clamped 로 신고


def set_manager(manager) -> None:
    global _manager
    _manager = manager


def get_manager():
    global _manager
    if _manager is None:
        from multi_chat_manager import MultiChatManager
        _manager = MultiChatManager()
    return _manager


def _items(rows, **extra) -> dict:
    return {"success": True, "items": list(rows), "count": len(rows), **extra}


def chat_room_op(params: dict) -> Any:
    op = (params.get("op") or "list").strip()
    m = get_manager()
    if op == "list":
        return _items(m.list_rooms())
    if op == "candidates":
        return _items(m.list_available_agents())
    if op == "create":
        name = (params.get("name") or "").strip()
        if not name:
            return {"success": False, "error": "create 에는 name 이 필요합니다"}
        return {"success": True, "room": m.create_room(name, params.get("description") or "")}
    room_id = str(params.get("room_id") or params.get("id") or "").strip()
    if not room_id:
        return {"success": False, "error": f"{op} 에는 room_id 가 필요합니다"}
    room = m.get_room(room_id)
    if not room:
        return {"success": False, "error": f"채팅방 없음: {room_id}"}
    if op == "info":
        return {"success": True, "room": room, "participants": m.get_room_participants(room_id)}
    if op == "participants":
        return _items(m.get_room_participants(room_id), room_id=room_id)
    if op == "add":
        project_id, agent_id = (params.get("project_id") or ""), (params.get("agent_id") or "")
        if "/" in str(agent_id) and not project_id:
            project_id, agent_id = str(agent_id).split("/", 1)
        if not project_id or not agent_id:
            return {"success": False, "error": "add 에는 project_id 와 agent_id 가 필요합니다('프로젝트/에이전트' 도 됨)"}
        ok = m.add_agent_to_room(room_id, str(project_id), str(agent_id))
        return {"success": bool(ok), "room_id": room_id, "added": f"{project_id}/{agent_id}",
                **({} if ok else {"error": "참가자를 추가하지 못했습니다(이미 있거나 에이전트 없음)"})}
    if op == "remove":
        name = (params.get("agent_name") or params.get("agent_id") or "").strip()
        if not name:
            return {"success": False, "error": "remove 에는 agent_name 이 필요합니다"}
        ok = m.remove_agent_from_room(room_id, name)
        return {"success": bool(ok), "room_id": room_id, "removed": name}
    if op == "messages":
        try:
            requested = int(params.get("limit") or 50)
        except (TypeError, ValueError):
            requested = 50
        limit = max(1, min(MESSAGES_MAX, requested))
        out = _items(m.get_messages(room_id, limit=limit), room_id=room_id)
        if requested != limit:
            out.update(clamped=True, requested=requested, limit=limit)   # 깎았으면 알린다(침묵 클램프 금지)
        return out
    if op == "say":
        message = (params.get("message") or params.get("text") or "").strip()
        if not message:
            return {"success": False, "error": "say 에는 message 가 필요합니다(@이름 으로 지목 가능)"}
        try:
            count = max(1, min(int(params.get("response_count") or 2), 10))
        except (TypeError, ValueError):
            count = 2
        responses = m.send_message(room_id=room_id, message=message, response_count=count, images=None)
        return {"success": True, "room_id": room_id, "user_message": message, "items": responses, "count": len(responses)}
    if op == "clear":
        return {"success": True, "room_id": room_id, "cleared": m.clear_messages(room_id)}
    if op == "trash":
        res = m.move_to_trash(room_id)
        return {"success": bool(res), **(res if isinstance(res, dict) else {}), "room_id": room_id}
    if op == "delete":
        return {"success": bool(m.delete_room(room_id)), "deleted": room_id, "permanent": True}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|candidates|create|info|participants|add|remove|messages|say|clear|trash|delete)"}
