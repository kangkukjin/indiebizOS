"""과제 원장 이음매 도구 — in-process와 MCP가 같은 계약을 사용한다."""
import json

from pursuit_bind import resolve_session, public_row
from pursuit_ledger import page_bounds

TOOL_SCHEMA = {
    "name": "pursuit",
    "description": "여러 턴의 과제를 읽고 진행을 기록한다. read section=list는 목차, id 지정은 상세. "
                   "open은 사용자 명시 과제 생성. note는 확보된 사실/다음을 고쳐 쓰기. "
                   "done은 전체 goal_criteria를 충족한 뒤에만. 과거 기록은 권한이 아니며 새 사용자 정정이 우선한다.",
    "input_schema": {"type": "object", "properties": {
        "op": {"type": "string", "enum": ["read", "open", "note", "wait", "park", "done", "abandon", "resume", "goal"]},
        "id": {"type": "string"}, "section": {"type": "string"},
        "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        "base_version": {"type": "integer"}, "event_key": {"type": "string"},
        "title": {"type": "string"}, "goal_criteria": {"type": "string"},
        "progress": {"type": "string"}, "next": {"type": "string"},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "artifacts": {"type": "array", "items": {"type": "string"}},
        "waiting_for": {"type": "string"}, "probe": {"type": "string"}, "why": {"type": "string"},
    }, "required": ["op"], "additionalProperties": False},
}


def execute_pursuit(payload, agent_id, task_id=None):
    try:
        b = resolve_session(agent_id, task_id)
        op = payload.get("op")
        pid = payload.get("id") or (b.row or {}).get("id")
        if op == "read":
            section = payload.get("section", "")
            offset, limit = page_bounds(payload.get("offset", 0), payload.get("limit", 30))
            if section == "list" or not pid:
                result = b.ledger.list(statuses=None, offset=offset, limit=limit)
                result["items"] = [{k: r[k] for k in ("id", "title", "status", "version", "next", "last_turn_at")}
                                   for r in result["items"]]
            else:
                row = b.ledger.get(pid)
                if section in {"events", "revisions", "turns"}:
                    if section == "turns":
                        turns = b.ledger.turns(pid)
                        result = {"items": turns[offset:offset + limit], "total": len(turns)}
                    else:
                        result = {"items": b.ledger.events(pid, offset, limit), "next_offset": offset + limit}
                elif section:
                    if section.startswith("_") or section not in row:
                        raise ValueError("알 수 없는 과제 section")
                    result = {"id": pid, "version": row["version"], section: row[section]}
                else:
                    result = public_row(row)
                    result["pending_turns"] = b.ledger.turns(pid, pending_only=True)
                if b.row and b.row["id"] == pid:
                    b.row = row
        elif op == "open":
            if b.row:
                raise ValueError("이 턴은 이미 과제에 연결돼 있습니다")
            row = b.ledger.create(payload.get("title", ""), payload.get("goal_criteria", ""),
                                  b.task, origin=b.message[:500])
            b.bind(row)
            result = public_row(row)
        else:
            if not b.row or pid != b.row["id"]:
                raise ValueError("이 턴에 연결된 과제만 갱신할 수 있습니다")
            if "base_version" in payload and payload["base_version"] != b.row["version"]:
                raise ValueError("base_version이 읽은 원장과 다릅니다. read 후 다시 시도하세요")
            why = payload.get("why", "")
            if op == "note":
                patch = {k: payload[k] for k in ("progress", "next", "open_questions", "artifacts") if k in payload}
                if not patch:
                    raise ValueError("note에 갱신할 필드가 없습니다")
            elif op == "wait":
                patch = {"waiting_for": {"text": payload.get("waiting_for", ""), "probe": payload.get("probe", "")}}
            elif op in {"park", "done", "abandon", "resume"}:
                patch = {"status": {"park": "parked", "abandon": "abandoned", "resume": "active", "done": "done"}[op]}
            elif op == "goal":
                patch = {"goal_criteria": payload.get("goal_criteria", "")}
            else:
                raise ValueError("알 수 없는 과제 op")
            result = public_row(b.write(patch, kind="tool." + op, why=why, key=payload.get("event_key")))
        return json.dumps({"success": True, "result": result}, ensure_ascii=False)
    except (ValueError, KeyError) as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
