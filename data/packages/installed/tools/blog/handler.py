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
    "blog_op": {"posts": None, "search": None, "check_new": None, "rebuild_index": None, "stats": None, "vault": None, "latest": None},
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
        if op == "vault":
            # 2026-07-03 고아 기능 op 승격 — vault(진실소스) 운영은 mode로 재분기.
            mode = (tool_input.get("mode") or "stats").strip()
            vault_tools = {
                "stats": "blog_vault_stats",
                "export": "blog_vault_export",
                "rebuild": "blog_vault_rebuild",
                "link": "blog_vault_link",
            }
            if mode not in vault_tools:
                return format_json({"success": False, "error": f"알 수 없는 vault mode '{mode}'. (stats|export|rebuild|link)"})
            tool_name = vault_tools[mode]
        else:
            tool_name = {
                "posts": "blog_get_posts",
                "search": "blog_search_op",
                "check_new": "blog_check_new_posts",
                "rebuild_index": "rebuild_search_index",
                "stats": "blog_stats",
                "latest": "blog_latest_post",
            }.get(op, "blog_get_posts")
    try:
        # 인사이트 도구들
        if tool_name == "blog_check_new_posts":
            from tool_blog_insight import blog_check_new_posts
            result = blog_check_new_posts()
            return format_json(result)

        elif tool_name == "blog_latest_post":
            # 최근 글 1개 **선택**. 본문을 여기서 렌더하지 않는다 — vault .md 경로만 준다.
            # 발행은 기존 동사로 잇는다(>> [self:read]{} >> [table:document] >> [self:copy]).
            # self:read 는 path 가 없으면 _prev_result 에서 경로를 자동 추출하므로(_extract_path_from_prev)
            # 이 op 이 top-level `path` 를 내면 파이프가 그대로 이어진다.
            # ★전용 발행 기계를 만들지 않는 이유: 그건 self:copy·table:document 재구현이다
            #   (2026-07-18 warehouse_publish.py 를 같은 이유로 폐기했다).
            from tool_blog_insight import get_db, BLOG_URL
            conn = get_db()
            row = conn.execute(
                "SELECT post_id, title, category, pub_date FROM posts "
                "ORDER BY pub_date DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if not row:
                return format_json({"success": False, "error": "블로그 글이 없습니다. 먼저 op:check_new 로 수집하세요."})

            post_id = str(row["post_id"])
            from tool_blog_vault import find_post_md, write_post_md
            path = find_post_md(post_id)
            if not path or not os.path.exists(path):
                # vault(진실소스)에 아직 .md 가 없으면 지금 만든다 — 옛 글은 vault 이관 전일 수 있다.
                conn2 = get_db()
                full = conn2.execute(
                    "SELECT post_id, title, category, pub_date, content FROM posts WHERE post_id = ?",
                    (post_id,)).fetchone()
                conn2.close()
                if not full:
                    return format_json({"success": False, "error": f"글을 찾을 수 없습니다: {post_id}"})
                path = write_post_md({
                    "post_id": post_id, "title": full["title"], "category": full["category"],
                    "pub_date": full["pub_date"], "content": full["content"],
                })

            title = row["title"]
            meta = f"{row['pub_date']} · {row['category']}"
            url = f"{BLOG_URL}/{post_id}"
            return format_json({
                "success": True, "post_id": post_id, "title": title,
                "category": row["category"], "pub_date": row["pub_date"],
                "path": path, "url": url,
                # 단일 통화 — 목록 소비자(앱·카드 뷰)도 이 op 을 읽을 수 있게.
                "items": [{"title": title, "meta": meta, "path": path, "url": url}],
                "message": f"최근 글: {title} ({row['pub_date']})",
            })

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
                result["items"] = _posts_to_records(result["posts"])
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
                result["items"] = _results_to_records(result["results"])
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
