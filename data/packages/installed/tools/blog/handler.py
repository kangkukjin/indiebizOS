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


def execute(tool_input: dict, context) -> str:
    """블로그 도구 실행 통합 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    project_path = context.project_path
    try:
        # 인사이트 도구들
        if tool_name == "blog_check_new_posts":
            from tool_blog_insight import blog_check_new_posts
            result = blog_check_new_posts()
            return format_json(result)

        elif tool_name == "blog_get_posts":
            from tool_blog_insight import blog_get_posts
            result = blog_get_posts(
                count=tool_input.get("count", 20),
                offset=tool_input.get("offset", 0),
                category=tool_input.get("category"),
                with_summary=tool_input.get("with_summary", False),
                only_without_summary=tool_input.get("only_without_summary", False)
            )
            return format_json(result)

        elif tool_name == "blog_get_post":
            from tool_blog_insight import blog_get_post
            result = blog_get_post(post_id=tool_input.get("post_id"))
            return format_json(result)

        elif tool_name == "blog_get_summaries":
            from tool_blog_insight import blog_get_summaries
            result = blog_get_summaries(
                count=tool_input.get("count", 20),
                offset=tool_input.get("offset", 0),
                category=tool_input.get("category")
            )
            return format_json(result)

        elif tool_name == "blog_save_summary":
            from tool_blog_insight import blog_save_summary
            result = blog_save_summary(
                post_id=tool_input.get("post_id"),
                summary=tool_input.get("summary"),
                keywords=tool_input.get("keywords", "")
            )
            return format_json(result)

        elif tool_name == "blog_search":
            from tool_blog_insight import blog_search
            result = blog_search(
                query=tool_input.get("query"),
                count=tool_input.get("count", 20),
                search_in=tool_input.get("search_in", "all")
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
                count=tool_input.get("count", 50),
                category=tool_input.get("category"),
                project_path=project_path
            )
            return format_json(result)

        elif tool_name == "kinsight":
            from tool_kinsight import kinsight
            result = kinsight(
                project_path=project_path,
                count=tool_input.get("count", 15),
                before_date=tool_input.get("before_date")
            )
            return format_json(result)

        elif tool_name == "kinsight2":
            return format_json({"success": False, "error": "kinsight2는 kinsight로 통합되었습니다. [self:kinsight]{count: N}을 사용하세요."})

        # 통합 도구 — IBL 어휘에 노출. mode로 분기.
        elif tool_name == "blog_search_op":
            mode = (tool_input.get("mode") or "hybrid").strip()
            if mode == "hybrid":
                from tool_blog_rag import search_blog
                result = search_blog(
                    query=tool_input.get("query"),
                    limit=tool_input.get("limit", 5)
                )
            elif mode == "semantic":
                from tool_blog_rag import search_blog_semantic
                result = search_blog_semantic(
                    query=tool_input.get("query"),
                    limit=tool_input.get("limit", 5)
                )
            elif mode == "content":
                from tool_blog_rag import get_post_content
                result = get_post_content(
                    post_id=tool_input.get("post_id")
                )
            else:
                result = {"success": False, "error": f"알 수 없는 mode '{mode}'. (hybrid|semantic|content)"}
            return format_json(result)

        # RAG 검색 도구들
        elif tool_name == "search_blog_rag":
            from tool_blog_rag import search_blog
            result = search_blog(
                query=tool_input.get("query"),
                limit=tool_input.get("limit", 5)
            )
            return format_json(result)

        elif tool_name == "get_post_content_rag":
            from tool_blog_rag import get_post_content
            result = get_post_content(
                post_id=tool_input.get("post_id")
            )
            return format_json(result)

        elif tool_name == "search_blog_semantic":
            from tool_blog_rag import search_blog_semantic
            result = search_blog_semantic(
                query=tool_input.get("query"),
                limit=tool_input.get("limit", 5)
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
