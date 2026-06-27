"""
Memory Handler - 메모리 통합 관리
심층 메모리 + 대화 이력을 통합 검색
"""
import json
import os
import sqlite3
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


# 2026-05-28 dispatcher 표준화 — 단일 액션 op 키 메타데이터 (browser-action 패턴).
# 값은 None — 분기 로직은 execute 안에 그대로 유지.
# --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "memory_op": {"save": None, "search": None, "read": None, "delete": None},
}
# memory_op는 op 필수 — _OP_DEFAULTS 항목 없음.


def execute(tool_input: dict, context) -> str:
    """메모리 & 스킬 도구 실행 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    project_path = context.project_path
    agent_id = context.agent_id

    try:
        # 통합 도구 (op 분기) — IBL 어휘에 노출
        if tool_name == "memory_op":
            import memory_db
            op = (tool_input.get("op") or "").strip()
            if op == "save":
                return _memory_save(memory_db, tool_input, project_path, agent_id)
            if op == "search":
                return _memory_search(memory_db, tool_input, project_path, agent_id)
            if op == "read":
                return _memory_read(memory_db, tool_input, project_path, agent_id)
            if op == "delete":
                return _memory_delete(memory_db, tool_input, project_path, agent_id)
            return json.dumps({"error": f"알 수 없는 op '{op}'. (save|search|read|delete)"}, ensure_ascii=False)

        # 옛 도구 이름 (직접 호출 호환)
        if tool_name in ("memory_save", "memory_search", "memory_read", "memory_delete"):
            import memory_db

            if tool_name == "memory_save":
                return _memory_save(memory_db, tool_input, project_path, agent_id)
            elif tool_name == "memory_search":
                return _memory_search(memory_db, tool_input, project_path, agent_id)
            elif tool_name == "memory_read":
                return _memory_read(memory_db, tool_input, project_path, agent_id)
            elif tool_name == "memory_delete":
                return _memory_delete(memory_db, tool_input, project_path, agent_id)

        return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============ 에이전트 메모리 도구 ============

def _memory_save(db, tool_input, project_path, agent_id):
    content = tool_input.get("content", "")
    if not content.strip():
        return json.dumps({"error": "content가 필요합니다."}, ensure_ascii=False)

    memory_id = db.save(
        project_path=project_path,
        agent_id=agent_id,
        content=content,
        keywords=tool_input.get("keywords", ""),
        category=tool_input.get("category", "")
    )

    return json.dumps({
        "memory_id": memory_id,
        "message": f"메모리 저장 완료 (ID: {memory_id})"
    }, ensure_ascii=False, indent=2)


def _memory_search(db, tool_input, project_path, agent_id):
    """통합 검색: 심층 메모리 + 대화 이력"""
    query = tool_input.get("query", "")
    if not query.strip():
        return json.dumps({"error": "query가 필요합니다."}, ensure_ascii=False)

    limit = tool_input.get("limit", 10)
    results = []

    # 1) 심층 메모리 검색
    deep_results = db.search(
        project_path=project_path,
        agent_id=agent_id,
        query=query,
        category=tool_input.get("category"),
        limit=limit
    )
    for r in deep_results:
        r["source"] = "deep_memory"
    results.extend(deep_results)

    # 2) 대화 이력 검색
    conv_results = _search_conversations(project_path, query, limit=min(limit, 5))
    results.extend(conv_results)

    # 레코드 통화 부착(비파괴) — memories 목록을 records로. >> [engines:document/spreadsheet] 파이프용.
    return json.dumps({
        "count": len(results),
        "memories": results,
        "items": _memories_to_records(results)
    }, ensure_ascii=False, indent=2)


def _memories_to_records(memories: list) -> list:
    """메모리/대화 검색 결과 → 레코드 통화 records[{title,meta,summary,url}].
    deep_memory 행(preview/category/keywords/created_at) + conversation 행(preview/from_agent/created_at) 두 형태 수용."""
    records = []
    for m in (memories or []):
        if not isinstance(m, dict):
            continue
        preview = m.get("preview") or m.get("content") or ""
        source = m.get("source")
        if source == "conversation":
            frm, to = m.get("from_agent"), m.get("to_agent")
            title = (f"{frm} → {to}" if frm and to else (frm or to or "대화")) or "대화"
            meta = [m.get("created_at"), "대화"]
        else:
            # deep_memory: 별도 제목 없음 → preview 첫 줄을 제목으로.
            title = (preview.split("\n", 1)[0][:60]).strip() or "메모"
            meta = [m.get("created_at"), m.get("category"), m.get("keywords")]
        records.append({
            "title": title,
            "meta": " · ".join(str(x) for x in meta if x),
            "summary": "" if preview == title else preview,
            "url": "",
        })
    return records


def _search_conversations(project_path, query, limit=5):
    """conversations.db에서 대화 이력 검색"""
    conv_db_path = os.path.join(project_path, "conversations.db")
    if not os.path.exists(conv_db_path):
        return []

    try:
        conn = sqlite3.connect(conv_db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT m.id, a_from.name as from_agent, a_to.name as to_agent,
                   substr(m.content, 1, 200) as preview,
                   m.message_time as created_at
            FROM messages m
            LEFT JOIN agents a_from ON m.from_agent_id = a_from.id
            LEFT JOIN agents a_to ON m.to_agent_id = a_to.id
            WHERE m.content LIKE ?
            ORDER BY m.message_time DESC
            LIMIT ?
        """, (f"%{query}%", limit)).fetchall()

        conn.close()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "preview": r["preview"],
                "from_agent": r["from_agent"],
                "to_agent": r["to_agent"],
                "created_at": r["created_at"],
                "source": "conversation"
            })
        return results
    except Exception:
        return []


def _memory_read(db, tool_input, project_path, agent_id):
    memory_id = tool_input.get("memory_id")
    if not memory_id:
        return json.dumps({"error": "memory_id가 필요합니다."}, ensure_ascii=False)

    memory = db.read(project_path, agent_id, memory_id)
    if not memory:
        return json.dumps({"error": f"ID {memory_id} 메모리 없음"}, ensure_ascii=False)

    parts = [memory['content']]
    meta = []
    if memory.get('created_at'):
        meta.append(f"작성: {memory['created_at']}")
    if memory.get('used_at'):
        meta.append(f"최근참조: {memory['used_at']}")
    if memory['category']:
        meta.append(f"카테고리: {memory['category']}")
    if memory['keywords']:
        meta.append(f"키워드: {memory['keywords']}")
    if meta:
        parts.append(f"[{' | '.join(meta)}]")

    return "\n".join(parts)


def _memory_delete(db, tool_input, project_path, agent_id):
    memory_id = tool_input.get("memory_id")
    if not memory_id:
        return json.dumps({"error": "memory_id가 필요합니다."}, ensure_ascii=False)

    deleted = db.delete(project_path, agent_id, memory_id)
    return json.dumps({
        "deleted": deleted,
        "message": f"메모리 ID {memory_id} 삭제 완료" if deleted else "삭제 실패"
    }, ensure_ascii=False, indent=2)
