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


def execute(tool_name: str, args: dict, project_path: str = ".") -> str:
    """
    지역 정보 도구 실행 핸들러.

    Args:
        tool_name: 도구 이름 (local_search, local_db_query, local_db_save)
        args: 도구 인자
        project_path: 프로젝트 경로

    Returns:
        JSON 문자열 결과
    """
    try:
        # ─── 1. 사이트 검색 ───
        if tool_name == "local_search":
            from tool_search import search
            result = search(
                query=args.get("query", ""),
                site=args.get("site", "naver_cafe"),
                cafe_id=args.get("cafe_id", "osong1"),
                display=args.get("display", 5)
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ─── 2. DB 조회 ───
        elif tool_name == "local_db_query":
            import tool_db

            action = args.get("action", "search")

            if action == "stats":
                result = tool_db.get_stats()
            elif action == "recent":
                result = tool_db.get_recent(limit=args.get("limit", 10))
            elif action == "detail":
                store_id = args.get("store_id")
                if not store_id:
                    result = {"success": False, "error": "store_id가 필요합니다."}
                else:
                    result = tool_db.get_store_with_mentions(int(store_id))
            else:  # search (기본)
                result = tool_db.query_stores(
                    query=args.get("query"),
                    category=args.get("category"),
                    area=args.get("area"),
                    limit=args.get("limit", 20)
                )
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ─── 3. DB 저장 ───
        elif tool_name == "local_db_save":
            import tool_db

            mode = args.get("mode", "store")

            if mode == "store":
                name = args.get("name")
                if not name:
                    result = {"success": False, "error": "가게 이름(name)은 필수입니다."}
                else:
                    result = tool_db.save_store(
                        name=name,
                        category=args.get("category"),
                        address=args.get("address"),
                        phone=args.get("phone"),
                        description=args.get("description"),
                        area=args.get("area", "오송"),
                        source=args.get("source"),
                        source_url=args.get("source_url"),
                        rating=args.get("rating"),
                        notes=args.get("notes")
                    )
            elif mode == "mention":
                store_id = args.get("store_id")
                if not store_id:
                    result = {"success": False, "error": "store_id는 필수입니다."}
                else:
                    result = tool_db.save_mention(
                        store_id=int(store_id),
                        title=args.get("title"),
                        content=args.get("content"),
                        source=args.get("source"),
                        source_url=args.get("source_url"),
                        post_date=args.get("post_date")
                    )
            elif mode == "delete":
                store_id = args.get("store_id")
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
