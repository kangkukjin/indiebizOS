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

# 2026-06-03 dispatcher 표준화 — [self:blog]{op} 키 메타데이터. 분기는 execute() 상단.
_OP_DISPATCHERS = {
    "blog_op": {"posts": None, "search": None, "check_new": None, "rebuild_index": None, "stats": None},
}
_OP_DEFAULTS = {"blog_op": "posts"}


def _posts_to_records(posts: list) -> list:
    """블로그 글 목록 → 레코드 통화 records[{title,meta,summary,url}].
    blog_get_posts 결과(post_id/title/category/pub_date/content_preview/summary?)용."""
    records = []
    for p in (posts or []):
        if not isinstance(p, dict):
            continue
        meta = [p.get("pub_date"), p.get("category")]
        kw = p.get("keywords")
        if kw:
            meta.append(kw if isinstance(kw, str) else " ".join(kw))
        title = p.get("title") or ""
        summary = p.get("summary") or p.get("content_preview") or ""
        pid = p.get("post_id")
        records.append({
            "title": title,
            "meta": " · ".join(str(x) for x in meta if x),
            "summary": "" if summary == title else summary,
            "url": p.get("link") or (f"/{pid}" if pid else ""),
        })
    return records


def _results_to_records(results: list) -> list:
    """블로그 RAG 검색 결과 → 레코드 통화 records[{title,meta,summary,url}].
    search_blog/semantic 결과(title/content/date/category/post_id/key_insight)용."""
    records = []
    for r in (results or []):
        if not isinstance(r, dict):
            continue
        meta = [r.get("date"), r.get("category"), r.get("search_type")]
        title = r.get("title") or ""
        summary = r.get("key_insight") or r.get("content") or ""
        pid = r.get("post_id")
        records.append({
            "title": title,
            "meta": " · ".join(str(x) for x in meta if x),
            "summary": "" if summary == title else summary,
            "url": (f"/{pid}" if pid else ""),
        })
    return records


def execute(tool_input: dict, context) -> str:
    """블로그 도구 실행 통합 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    project_path = context.project_path
    # 2026-06-03 어휘 정리: [self:blog]{op} 단일 액션 → 내부 tool_name으로 디스패치.
    if tool_name == "blog_op":
        op = (tool_input.get("op") or _OP_DEFAULTS["blog_op"]).strip()
        tool_name = {
            "posts": "blog_get_posts",
            "search": "blog_search_op",
            "check_new": "blog_check_new_posts",
            "rebuild_index": "rebuild_search_index",
            "stats": "blog_stats",
        }.get(op, "blog_get_posts")
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
            # 레코드 통화 부착(비파괴) — posts 목록을 records로.
            if isinstance(result, dict) and isinstance(result.get("posts"), list):
                result["records"] = _posts_to_records(result["posts"])
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

        # (2026-06-03 kinsight/kinsight2 폐기 — 블로그 인사이트 액션 제거)

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
            # 레코드 통화 부착(비파괴) — 검색 results 목록을 records로(content는 단건이라 미부착).
            if isinstance(result, dict) and isinstance(result.get("results"), list):
                result["records"] = _results_to_records(result["results"])
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

        # === Vault (canonical store) 운영 ===
        elif tool_name == "blog_vault_stats":
            from tool_blog_vault import vault_stats
            return format_json({"success": True, **vault_stats()})

        elif tool_name == "blog_vault_export":
            from tool_blog_vault import export_all
            return format_json(export_all())

        elif tool_name == "blog_vault_rebuild":
            from tool_blog_vault import rebuild_db_from_vault
            result = rebuild_db_from_vault(
                reindex=tool_input.get("reindex", True)
            )
            return format_json(result)

        elif tool_name == "blog_vault_link":
            from tool_blog_vault import build_semantic_links
            result = build_semantic_links(
                k=tool_input.get("k", 6),
                min_sim=tool_input.get("min_sim", 0.55),
            )
            return format_json(result)

        else:
            return format_json({"success": False, "error": f"Unknown tool: {tool_name}"})

    except ImportError as e:
        return format_json({"success": False, "error": f"Import error: {str(e)}"})
    except Exception as e:
        return format_json({"success": False, "error": str(e)})
