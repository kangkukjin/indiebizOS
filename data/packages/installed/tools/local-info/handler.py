"""
Local Info Handler - 지역 정보 검색 및 DB 관리
================================================
도구 3개: local_search, local_db_query, local_db_save
"""

import json
import os
import sys

# 현재 디렉토리를 path에 추가
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


def execute(tool_input: dict, context) -> str:
    """지역 정보 도구 실행 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    try:
        # ─── 1. 사이트 검색 ───
        if tool_name == "local_search":
            from tool_search import search
            result = search(
                query=tool_input.get("query", ""),
                site=tool_input.get("site", "naver_cafe"),
                cafe_id=tool_input.get("cafe_id", "osong1"),
                display=tool_input.get("display", 5)
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ─── 2. DB 조회 ───
        elif tool_name == "local_db_query":
            import tool_db

            action = tool_input.get("action", "search")

            if action == "stats":
                result = tool_db.get_stats()
            elif action == "recent":
                result = tool_db.get_recent(limit=tool_input.get("limit", 10))
            elif action == "detail":
                store_id = tool_input.get("store_id")
                if not store_id:
                    result = {"success": False, "error": "store_id가 필요합니다."}
                else:
                    result = tool_db.get_store_with_mentions(int(store_id))
            else:  # search (기본)
                result = tool_db.query_stores(
                    query=tool_input.get("query"),
                    category=tool_input.get("category"),
                    area=tool_input.get("area"),
                    limit=tool_input.get("limit", 20)
                )
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ─── 3. DB 저장 ───
        elif tool_name == "local_db_save":
            import tool_db

            mode = tool_input.get("mode", "store")

            if mode == "store":
                name = tool_input.get("name")
                if not name:
                    result = {"success": False, "error": "가게 이름(name)은 필수입니다."}
                else:
                    result = tool_db.save_store(
                        name=name,
                        category=tool_input.get("category"),
                        address=tool_input.get("address"),
                        phone=tool_input.get("phone"),
                        description=tool_input.get("description"),
                        area=tool_input.get("area", "오송"),
                        source=tool_input.get("source"),
                        source_url=tool_input.get("source_url"),
                        rating=tool_input.get("rating"),
                        notes=tool_input.get("notes")
                    )
            elif mode == "mention":
                store_id = tool_input.get("store_id")
                if not store_id:
                    result = {"success": False, "error": "store_id는 필수입니다."}
                else:
                    result = tool_db.save_mention(
                        store_id=int(store_id),
                        title=tool_input.get("title"),
                        content=tool_input.get("content"),
                        source=tool_input.get("source"),
                        source_url=tool_input.get("source_url"),
                        post_date=tool_input.get("post_date")
                    )
            elif mode == "delete":
                store_id = tool_input.get("store_id")
                if not store_id:
                    result = {"success": False, "error": "store_id는 필수입니다."}
                else:
                    result = tool_db.delete_store(int(store_id))
            else:
                result = {"success": False, "error": f"지원하지 않는 mode: {mode}. (store, mention, delete)"}

            return json.dumps(result, ensure_ascii=False, indent=2)

        else:
            return json.dumps({
                "success": False,
                "error": f"알 수 없는 도구: {tool_name}"
            }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"도구 실행 오류: {str(e)}",
            "tool_name": tool_name
        }, ensure_ascii=False)
