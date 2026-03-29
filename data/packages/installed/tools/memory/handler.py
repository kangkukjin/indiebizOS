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


def _get_agent_id():
    """현재 에이전트 ID 가져오기"""
    from thread_context import get_current_agent_id
    return get_current_agent_id()


def execute(tool_name: str, args: dict, project_path: str = ".") -> str:
    """메모리 & 스킬 도구 실행"""
    try:
        # 에이전트 메모리 도구
        if tool_name in ("memory_save", "memory_search", "memory_read", "memory_delete"):
            import memory_db
            agent_id = _get_agent_id()

            if tool_name == "memory_save":
                return _memory_save(memory_db, args, project_path, agent_id)
            elif tool_name == "memory_search":
                return _memory_search(memory_db, args, project_path, agent_id)
            elif tool_name == "memory_read":
                return _memory_read(memory_db, args, project_path, agent_id)
            elif tool_name == "memory_delete":
                return _memory_delete(memory_db, args, project_path, agent_id)

        return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============ 에이전트 메모리 도구 ============

def _memory_save(db, args, project_path, agent_id):
    content = args.get("content", "")
    if not content.strip():
        return json.dumps({"error": "content가 필요합니다."}, ensure_ascii=False)

    memory_id = db.save(
        project_path=project_path,
        agent_id=agent_id,
        content=content,
        keywords=args.get("keywords", ""),
        category=args.get("category", "")
    )

    return json.dumps({
        "memory_id": memory_id,
        "message": f"메모리 저장 완료 (ID: {memory_id})"
    }, ensure_ascii=False, indent=2)


def _memory_search(db, args, project_path, agent_id):
    """통합 검색: 심층 메모리 + 대화 이력"""
    query = args.get("query", "")
    if not query.strip():
        return json.dumps({"error": "query가 필요합니다."}, ensure_ascii=False)

    limit = args.get("limit", 10)
    results = []

    # 1) 심층 메모리 검색
    deep_results = db.search(
        project_path=project_path,
        agent_id=agent_id,
        query=query,
        category=args.get("category"),
        limit=limit
    )
    for r in deep_results:
        r["source"] = "deep_memory"
    results.extend(deep_results)

    # 2) 대화 이력 검색
    conv_results = _search_conversations(project_path, query, limit=min(limit, 5))
    results.extend(conv_results)

    return json.dumps({
        "count": len(results),
        "memories": results
    }, ensure_ascii=False, indent=2)


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


def _memory_read(db, args, project_path, agent_id):
    memory_id = args.get("memory_id")
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


def _memory_delete(db, args, project_path, agent_id):
    memory_id = args.get("memory_id")
    if not memory_id:
        return json.dumps({"error": "memory_id가 필요합니다."}, ensure_ascii=False)

    deleted = db.delete(project_path, agent_id, memory_id)
    return json.dumps({
        "deleted": deleted,
        "message": f"메모리 ID {memory_id} 삭제 완료" if deleted else "삭제 실패"
    }, ensure_ascii=False, indent=2)
