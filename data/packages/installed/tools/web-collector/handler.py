"""
Web Collector v2 Handler - 가이드 + DB 프레임워크
=================================================
도구 3개: wc_sites, wc_save, wc_query
"""

import json
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


def execute(tool_name: str, args: dict, project_path: str = ".") -> str:
    """
    웹 수집 도구 실행 핸들러.

    Args:
        tool_name: 도구 이름 (wc_sites, wc_save, wc_query)
        args: 도구 인자
        project_path: 프로젝트 경로

    Returns:
        JSON 문자열 결과
    """
    try:
        # ─── 1. 사이트 가이드 관리 ───
        if tool_name == "wc_sites":
            from collector import manage_sites
            result = manage_sites(
                action=args.get("action", "list"),
                site_id=args.get("site_id"),
                guide_code=args.get("guide_code"),
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ─── 2. 데이터 저장 ───
        elif tool_name == "wc_save":
            from collector import save_items
            result = save_items(
                site_id=args.get("site_id", ""),
                items=args.get("items", []),
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        # ─── 3. DB 조회 ───
        elif tool_name == "wc_query":
            import collector_db as db

            action = args.get("action", "search")

            if action == "stats":
                result = db.get_stats(site_id=args.get("site_id"))
            elif action == "recent":
                result = db.get_recent(
                    site_id=args.get("site_id"),
                    limit=args.get("limit", 20)
                )
            elif action == "detail":
                item_id = args.get("item_id")
                if not item_id:
                    result = {"success": False, "error": "item_id가 필요합니다."}
                else:
                    result = db.get_item_detail(int(item_id))
            elif action == "delete":
                item_id = args.get("item_id")
                if not item_id:
                    result = {"success": False, "error": "item_id가 필요합니다."}
                else:
                    result = db.delete_item(int(item_id))
            else:  # search (기본)
                result = db.search_items(
                    query=args.get("query"),
                    site_id=args.get("site_id"),
                    limit=args.get("limit", 20),
                    offset=args.get("offset", 0)
                )

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
