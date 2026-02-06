"""
Blog Tools Handler - RAG 검색 및 인사이트 분석 통합
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
    블로그 도구 실행 통합 핸들러
    """
    try:
        # 인사이트 도구들
        if tool_name == "blog_check_new_posts":
            from tool_blog_insight import blog_check_new_posts
            result = blog_check_new_posts()
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "blog_get_posts":
            from tool_blog_insight import blog_get_posts
            result = blog_get_posts(
                count=args.get("count", 20),
                offset=args.get("offset", 0),
                category=args.get("category"),
                with_summary=args.get("with_summary", False),
                only_without_summary=args.get("only_without_summary", False)
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "blog_get_post":
            from tool_blog_insight import blog_get_post
            result = blog_get_post(post_id=args.get("post_id"))
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "blog_get_summaries":
            from tool_blog_insight import blog_get_summaries
            result = blog_get_summaries(
                count=args.get("count", 20),
                offset=args.get("offset", 0),
                category=args.get("category")
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "blog_save_summary":
            from tool_blog_insight import blog_save_summary
            result = blog_save_summary(
                post_id=args.get("post_id"),
                summary=args.get("summary"),
                keywords=args.get("keywords", "")
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "blog_search":
            from tool_blog_insight import blog_search
            result = blog_search(
                query=args.get("query"),
                count=args.get("count", 20),
                search_in=args.get("search_in", "all")
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "blog_stats":
            from tool_blog_insight import blog_stats
            result = blog_stats()
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "blog_insight_report":
            from tool_blog_insight import blog_insight_report
            # project_path 전달 필수
            result = blog_insight_report(
                count=args.get("count", 50),
                category=args.get("category"),
                project_path=project_path
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "kinsight":
            from tool_kinsight import kinsight
            result = kinsight(
                project_path=project_path,
                before_date=args.get("before_date")
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "kinsight2":
            from tool_kinsight import kinsight2
            result = kinsight2(
                project_path=project_path,
                count=args.get("count", 10),
                before_date=args.get("before_date")
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        # RAG 검색 도구들
        elif tool_name == "search_blog_rag":
            from tool_blog_rag import search_blog
            result = search_blog(
                query=args.get("query"),
                limit=args.get("limit", 5)
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        else:
            return f"Unknown tool: {tool_name}"

    except ImportError as e:
        return json.dumps({"success": False, "error": f"Import error: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
