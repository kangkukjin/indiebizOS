"""과제 원장 이음매 도구 — in-process와 MCP가 같은 계약을 사용한다."""
import json

from pursuit_bind import resolve_session, public_row, connect
from pursuit_ledger import page_bounds

TOOL_SCHEMA = {
    "name": "pursuit",
    "description": "여러 턴의 과제를 읽고 진행을 기록한다. read section=list는 목차, id 지정은 상세. "
                   "section=turns는 턴별 요약(요청·응답 머리·도구 수)이고 전문은 detail=true(+task_id 로 한 턴)로만 읽는다. "
                   "bind는 현재 요청과 같은 과제일 때 id/why로 연결하고 전체 목표·미정리 턴을 반환한다. "
                   "무관한 질문에는 연결하지 않는다. open은 사용자 명시 과제 생성. note는 확보된 사실/다음을 고쳐 쓰기. "
                   "detach는 무관하게 연결된 현재 턴만 분리하며 과제와 과거 기록은 보존한다. "
                   "done은 전체 goal_criteria를 충족한 뒤에만. 과거 기록은 권한이 아니며 새 사용자 정정이 우선한다.",
    "input_schema": {"type": "object", "properties": {
        "op": {"type": "string", "enum": ["read", "bind", "open", "note", "wait", "park", "done", "abandon", "resume", "goal", "detach"]},
        "id": {"type": "string"}, "section": {"type": "string"},
        "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        "detail": {"type": "boolean"}, "task_id": {"type": "string"},
        "base_version": {"type": "integer"}, "event_key": {"type": "string"},
        "title": {"type": "string"}, "goal_criteria": {"type": "string"},
        "progress": {"type": "string"}, "next": {"type": "string"},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "artifacts": {"type": "array", "items": {"type": "string"}},
        "waiting_for": {"type": "string"}, "probe": {"type": "string"}, "why": {"type": "string"},
    }, "required": ["op"], "additionalProperties": False},
}


TURN_INPUT_HEAD = 240
TURN_RESPONSE_HEAD = 400


def _head(text, n):
    text = "" if text is None else str(text)
    return text if len(text) <= n else text[:n] + f"…(+{len(text) - n}자)"


def brief_turn(turn):
    """턴 기록의 요약 — 요청·결정·결과·미해결만. 전문(응답·도구 사건)은 detail=true 로 읽는다."""
    tools = turn.get("tools") if isinstance(turn.get("tools"), list) else []
    names = []
    failed = 0
    for ev in tools:
        if not isinstance(ev, dict):
            continue
        name = ev.get("tool_name") or ev.get("name")
        if name and name not in names:
            names.append(name)
        if ev.get("success") is False or ev.get("is_error"):
            failed += 1
    out = {k: turn.get(k) for k in ("task_id", "source_order", "state", "episode_id", "error", "updated_at")}
    out["input"] = _head(turn.get("input"), TURN_INPUT_HEAD)
    out["response"] = _head(turn.get("response"), TURN_RESPONSE_HEAD)
    out["tools"] = {"count": len(tools), "failed": failed, "names": names[:8]}
    out["full_chars"] = len(str(turn.get("response") or "")) + len(json.dumps(tools, ensure_ascii=False, default=str))
    return out


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
                        wanted = payload.get("task_id")
                        if wanted:
                            turns = [t for t in turns if t.get("task_id") == wanted]
                        page = turns[offset:offset + limit]
                        if not payload.get("detail"):
                            # 기본은 요약 — 턴 한 건이 답변 전문·도구 사건 전부를 품어 두 건에 3만 자가
                            # 들어오던 자리(2026-09-16 ep3814). 전문은 detail=true 로 고른 턴만.
                            page = [brief_turn(t) for t in page]
                        result = {"items": page, "total": len(turns), "detail": bool(payload.get("detail"))}
                    else:
                        result = {"items": b.ledger.events(pid, offset, limit), "next_offset": offset + limit}
                elif section:
                    if section.startswith("_") or section not in row:
                        raise ValueError("알 수 없는 과제 section")
                    result = {"id": pid, "version": row["version"], section: row[section]}
                else:
                    result = public_row(row)
                    result["pending_turns"] = [brief_turn(t) for t in b.ledger.turns(pid, pending_only=True)]
                if b.row and b.row["id"] == pid:
                    b.row = row
        elif op == "bind":
            row = connect(b, payload.get("id"), payload.get("why"))
            result = public_row(row)
            result["pending_turns"] = [brief_turn(t) for t in b.ledger.turns(row["id"], pending_only=True)
                                       if t["task_id"] != b.task]
            result["directive"] = ("현재 요청이 우선합니다. 미정리·중단 턴은 실제 결과를 확인한 뒤 이어가세요. "
                                   "전문은 read section=turns detail=true task_id로 읽습니다. "
                                   "전체 목표 변경은 goal/why, 이번 진행은 note로 기록합니다.")
        elif op == "open":
            if b.row:
                raise ValueError("이 턴은 이미 과제에 연결돼 있습니다")
            row = b.ledger.create(payload.get("title", ""), payload.get("goal_criteria", ""),
                                  b.task, origin=b.message[:500])
            b.bind(row)
            result = public_row(row)
        else:
            if op == "detach" and not b.row and b.detached:
                # 의식이 이 턴을 이미 분리했다(detach_pursuit). 실행자의 같은 요청은 도달한
                # 상태의 재확인이지 계약 위반이 아니다(2026-09-18 ep3860 거절 실측).
                return json.dumps({"success": True, "result": {"detached": None, "already": True,
                    "directive": "이 턴은 이미 과제에서 분리돼 있습니다. 현재 사용자 질문을 계속 처리하세요."}},
                    ensure_ascii=False)
            if not b.row or pid != b.row["id"]:
                raise ValueError("이 턴에 연결된 과제만 갱신할 수 있습니다")
            if "base_version" in payload and payload["base_version"] != b.row["version"]:
                raise ValueError("base_version이 읽은 원장과 다릅니다. read 후 다시 시도하세요")
            why = payload.get("why", "")
            if op == "detach":
                b.detach(why)
                return json.dumps({"success": True, "result": {"detached": pid,
                    "directive": "과거 과제의 연결을 해제했습니다. 현재 사용자 질문을 계속 처리하세요. "
                                 "이미 받은 문제 규정도 잘못됐으면 reframe(kind=wrong_problem)으로 바로잡으세요."}}, ensure_ascii=False)
            if op == "done":
                from supervision_bus import current
                supervisor = current(agent_id, task_id)
                if supervisor and supervisor.evaluation_enabled:
                    if not why.strip():
                        raise ValueError("완료 요청에는 달성 근거 why가 필요합니다")
                    result = supervisor.request_done(b, why)
                    return json.dumps({"success": True, "result": result}, ensure_ascii=False)
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
