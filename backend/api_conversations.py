"""
api_conversations.py - 대화 관련 API
IndieBiz OS Core
"""

import json

from fastapi import APIRouter, HTTPException

from conversation_db import ConversationDB

router = APIRouter()

# 매니저 인스턴스
project_manager = None


def init_manager(pm):
    """매니저 인스턴스 초기화"""
    global project_manager
    project_manager = pm


# ============ 대화 API ============

@router.get("/conversations/{project_id}")
async def get_conversations(project_id: str):
    """프로젝트의 대화 목록 (에이전트 목록)"""
    try:
        project_path = project_manager.get_project_path(project_id)
        db_path = project_path / "conversations.db"

        if not db_path.exists():
            return {"conversations": []}

        db = ConversationDB(str(db_path))
        agents = []
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, type FROM agents")
            agents = [{"id": row[0], "name": row[1], "type": row[2]} for row in cursor.fetchall()]

        return {"conversations": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{project_id}/{agent_id}/messages")
async def get_messages(project_id: str, agent_id: int, limit: int = 50, offset: int = 0):
    """에이전트와의 대화 메시지 조회"""
    try:
        project_path = project_manager.get_project_path(project_id)
        db_path = project_path / "conversations.db"

        if not db_path.exists():
            return {"messages": []}

        db = ConversationDB(str(db_path))

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, from_agent_id, to_agent_id, content, message_time, tool_calls
                FROM messages
                WHERE from_agent_id = ? OR to_agent_id = ?
                ORDER BY message_time DESC
                LIMIT ? OFFSET ?
            """, (agent_id, agent_id, limit, offset))

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "id": row[0],
                    "from_agent_id": row[1],
                    "to_agent_id": row[2],
                    "content": row[3],
                    "timestamp": row[4],
                    "tool_calls": json.loads(row[5]) if row[5] else None
                })

        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{project_id}/{agent_id}/partners")
async def get_conversation_partners(project_id: str, agent_id: int):
    """특정 에이전트와 대화한 상대 목록"""
    try:
        project_path = project_manager.get_project_path(project_id)
        db_path = project_path / "conversations.db"

        if not db_path.exists():
            return {"partners": []}

        db = ConversationDB(str(db_path))

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    a.id,
                    a.name,
                    a.type,
                    MAX(m.message_time) as last_message_time,
                    COUNT(*) as message_count
                FROM agents a
                INNER JOIN (
                    SELECT CASE
                        WHEN from_agent_id = ? THEN to_agent_id
                        ELSE from_agent_id
                    END as partner_id,
                    message_time
                    FROM messages
                    WHERE from_agent_id = ? OR to_agent_id = ?
                ) m ON a.id = m.partner_id
                GROUP BY a.id, a.name, a.type
                ORDER BY last_message_time DESC
            """, (agent_id, agent_id, agent_id))

            partners = []
            for row in cursor.fetchall():
                partners.append({
                    "id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "last_message_time": row[3],
                    "message_count": row[4]
                })

        return {"partners": partners}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{project_id}/between/{agent1_id}/{agent2_id}")
async def get_messages_between(project_id: str, agent1_id: int, agent2_id: int, limit: int = 100, offset: int = 0):
    """두 에이전트 간의 대화 메시지"""
    try:
        project_path = project_manager.get_project_path(project_id)
        db_path = project_path / "conversations.db"

        if not db_path.exists():
            return {"messages": []}

        db = ConversationDB(str(db_path))

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, from_agent_id, to_agent_id, content, message_time, tool_calls
                FROM messages
                WHERE (from_agent_id = ? AND to_agent_id = ?)
                   OR (from_agent_id = ? AND to_agent_id = ?)
                ORDER BY message_time DESC
                LIMIT ? OFFSET ?
            """, (agent1_id, agent2_id, agent2_id, agent1_id, limit, offset))

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "id": row[0],
                    "from_agent_id": row[1],
                    "to_agent_id": row[2],
                    "content": row[3],
                    "timestamp": row[4],
                    "tool_calls": json.loads(row[5]) if row[5] else None
                })

        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
