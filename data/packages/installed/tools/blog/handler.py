"""
Blog Tools Handler - RAG 검색 및 인사이트 분석 통합
"""

import os
import sys

# 현재 디렉토리를 path에 추가
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# common 유틸리티 사용
_backend_dir = os.path.join(CURRENT_DIR, "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.response_formatter import format_json


def execute(tool_name: str, args: dict, project_path: str = ".") -> str:
    """
    블로그 도구 실행 통합 핸들러
    """
    try:
        # 인사이트 도구들
        if tool_name == "blog_check_new_posts":
            from tool_blog_insight import blog_check_new_posts
            result = blog_check_new_posts()
            return format_json(result)

        elif tool_name == "blog_get_posts":
            from tool_blog_insight import blog_get_posts
            result = blog_get_posts(
                count=args.get("count", 20),
                offset=args.get("offset", 0),
                category=args.get("category"),
                with_summary=args.get("with_summary", False),
                only_without_summary=args.get("only_without_summary", False)
            )
            return format_json(result)

        elif tool_name == "blog_get_post":
            from tool_blog_insight import blog_get_post
            result = blog_get_post(post_id=args.get("post_id"))
            return format_json(result)

        elif tool_name == "blog_get_summaries":
            from tool_blog_insight import blog_get_summaries
            result = blog_get_summaries(
                count=args.get("count", 20),
                offset=args.get("offset", 0),
                category=args.get("category")
            )
            return format_json(result)

        elif tool_name == "blog_save_summary":
            from tool_blog_insight import blog_save_summary
            result = blog_save_summary(
                post_id=args.get("post_id"),
                summary=args.get("summary"),
                keywords=args.get("keywords", "")
            )
            return format_json(result)

        elif tool_name == "blog_search":
            from tool_blog_insight import blog_search
            result = blog_search(
                query=args.get("query"),
                count=args.get("count", 20),
                search_in=args.get("search_in", "all")
            )
            return format_json(result)

        elif tool_name == "blog_stats":
            from tool_blog_insight import blog_stats
            result = blog_stats()
            return format_json(result)

        elif tool_name == "blog_insight_report":
            from tool_blog_insight import blog_insight_report
            # project_path 전달 필수
            result = blog_insight_report(
                count=args.get("count", 50),
                category=args.get("category"),
                project_path=project_path
            )
            return format_json(result)

        elif tool_name == "kinsight":
            from tool_kinsight import kinsight
            result = kinsight(
                project_path=project_path,
                before_date=args.get("before_date")
            )
            return format_json(result)

        elif tool_name == "kinsight2":
            from tool_kinsight import kinsight2
            result = kinsight2(
                project_path=project_path,
                count=args.get("count", 10),
                before_date=args.get("before_date")
            )
            return format_json(result)

        # RAG 검색 도구들
        elif tool_name == "search_blog_rag":
            from tool_blog_rag import search_blog
            result = search_blog(
                query=args.get("query"),
                limit=args.get("limit", 5)
            )
            return format_json(result)

        elif tool_name == "get_post_content_rag":
            from tool_blog_rag import get_post_content
            result = get_post_content(
                post_id=args.get("post_id")
            )
            return format_json(result)

        elif tool_name == "search_blog_semantic":
            from tool_blog_rag import search_blog_semantic
            result = search_blog_semantic(
                query=args.get("query"),
                limit=args.get("limit", 5)
            )
            return format_json(result)

        elif tool_name == "rebuild_search_index":
            from tool_blog_rag import rebuild_search_index
            result = rebuild_search_index()
            return format_json(result)

        else:
            return format_json({"success": False, "error": f"Unknown tool: {tool_name}"})

    except ImportError as e:
        return format_json({"success": False, "error": f"Import error: {str(e)}"})
    except Exception as e:
        return format_json({"success": False, "error": str(e)})
