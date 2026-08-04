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


# ── op / 내부 tool 분기 함수 (music-player 동형 — 진짜 디스패처) ─────────
# 각 함수 본문 = 옛 execute() if/elif 체인의 해당 분기 그대로.

def _op_check_new(tool_input: dict, context) -> str:
    """인사이트 도구 — 새 글 수집 (옛 blog_check_new_posts)."""
    from tool_blog_insight import blog_check_new_posts
    result = blog_check_new_posts()
    return format_json(result)


def _op_latest(tool_input: dict, context) -> str:
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


def _op_posts(tool_input: dict, context) -> str:
    """글 목록 (옛 blog_get_posts)."""
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


def _tool_blog_get_summaries(tool_input: dict, context) -> str:
    from tool_blog_insight import blog_get_summaries
    result = blog_get_summaries(
        count=tool_input.get("count", 20),
        offset=tool_input.get("offset", 0),
        category=tool_input.get("category")
    )
    return format_json(result)


def _tool_blog_save_summary(tool_input: dict, context) -> str:
    from tool_blog_insight import blog_save_summary
    result = blog_save_summary(
        post_id=tool_input.get("post_id"),
        summary=tool_input.get("summary"),
        keywords=tool_input.get("keywords", "")
    )
    return format_json(result)


def _tool_blog_search(tool_input: dict, context) -> str:
    from tool_blog_insight import blog_search
    result = blog_search(
        query=tool_input.get("query"),
        count=tool_input.get("count", 20),
        search_in=tool_input.get("search_in", "all")
    )
    return format_json(result)


def _op_stats(tool_input: dict, context) -> str:
    from tool_blog_insight import blog_stats
    result = blog_stats()
    return format_json(result)


def _tool_blog_insight_report(tool_input: dict, context) -> str:
    from tool_blog_insight import blog_insight_report
    # project_path 전달 필수
    result = blog_insight_report(
        count=tool_input.get("count", 50),
        category=tool_input.get("category"),
        project_path=context.project_path
    )
    return format_json(result)


# (2026-06-03 kinsight/kinsight2 폐기 — 블로그 인사이트 액션 제거)

def _op_search(tool_input: dict, context) -> str:
    """통합 검색 (옛 blog_search_op) — IBL 어휘에 노출. mode로 분기."""
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
        # post_id 없이 query만 온 호출은 query를 제목 검색어로 폴백
        target = tool_input.get("post_id") or tool_input.get("query")
        if not target or not str(target).strip():
            result = {"success": False,
                      "message": 'post_id 또는 query(제목 검색어)가 필요합니다. mode:"content"는 특정 포스트 하나를 여는 모드입니다.'}
        else:
            from tool_blog_rag import get_post_content
            result = get_post_content(post_id=str(target).strip())
    else:
        result = {"success": False, "error": f"알 수 없는 mode '{mode}'. (hybrid|semantic|content)"}
    # 레코드 통화 부착(비파괴) — 검색 results 목록을 records로(content는 단건이라 미부착).
    if isinstance(result, dict) and isinstance(result.get("results"), list):
        result["items"] = _results_to_records(result["results"])
    return format_json(result)


def _op_rebuild_index(tool_input: dict, context) -> str:
    from tool_blog_rag import rebuild_search_index
    result = rebuild_search_index()
    return format_json(result)


# === Vault (canonical store) 운영 ===

def _op_vault_stats(tool_input: dict, context) -> str:
    from tool_blog_vault import vault_stats
    return format_json({"success": True, **vault_stats()})


def _op_vault_export(tool_input: dict, context) -> str:
    from tool_blog_vault import export_all
    return format_json(export_all())


def _op_vault_rebuild(tool_input: dict, context) -> str:
    from tool_blog_vault import rebuild_db_from_vault
    result = rebuild_db_from_vault(
        reindex=tool_input.get("reindex", True)
    )
    return format_json(result)


def _op_vault_link(tool_input: dict, context) -> str:
    from tool_blog_vault import build_semantic_links
    result = build_semantic_links(
        k=tool_input.get("k", 6),
        min_sim=tool_input.get("min_sim", 0.55),
    )
    return format_json(result)


def _op_vault(tool_input: dict, context) -> str:
    # 2026-07-03 고아 기능 op 승격 — vault(진실소스) 운영은 mode로 재분기.
    mode = (tool_input.get("mode") or "stats").strip()
    vault_fns = {
        "stats": _op_vault_stats,
        "export": _op_vault_export,
        "rebuild": _op_vault_rebuild,
        "link": _op_vault_link,
    }
    fn = vault_fns.get(mode)
    if fn is None:
        return format_json({"success": False, "error": f"알 수 없는 vault mode '{mode}'. (stats|export|rebuild|link)"})
    return fn(tool_input, context)


# 2026-06-03 dispatcher 표준화 → 2026-08-05 진짜 디스패처로 전환 (music-player 동형).
# --check 가 이 dict 키로 src.ops.values 와 정확 비교 — 키 집합 변경 금지.
_OP_DISPATCHERS = {
    "blog_op": {"posts": _op_posts, "search": _op_search, "check_new": _op_check_new, "rebuild_index": _op_rebuild_index, "stats": _op_stats, "vault": _op_vault, "latest": _op_latest},
}
_OP_DEFAULTS = {"blog_op": "posts"}

# op 미보유 내부 tool_name 직행 경로 (옛 체인의 나머지 분기 — 기존 그대로 유지)
_TOOL_FNS = {
    "blog_check_new_posts": _op_check_new,
    "blog_latest_post": _op_latest,
    "blog_get_posts": _op_posts,
    "blog_get_summaries": _tool_blog_get_summaries,
    "blog_save_summary": _tool_blog_save_summary,
    "blog_search": _tool_blog_search,
    "blog_stats": _op_stats,
    "blog_insight_report": _tool_blog_insight_report,
    "blog_search_op": _op_search,
    "rebuild_search_index": _op_rebuild_index,
    "blog_vault_stats": _op_vault_stats,
    "blog_vault_export": _op_vault_export,
    "blog_vault_rebuild": _op_vault_rebuild,
    "blog_vault_link": _op_vault_link,
}


def execute(tool_input: dict, context) -> str:
    """블로그 도구 실행 통합 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    # 2026-06-03 어휘 정리: [self:blog]{op} 단일 액션 → 디스패처 테이블로 분기.
    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.get("op") or _OP_DEFAULTS[tool_name]).strip()
        # 옛 체인의 `.get(op, "blog_get_posts")` 폴백 유지 — 알 수 없는 op 은 posts.
        fn = _OP_DISPATCHERS[tool_name].get(op) or _op_posts
    else:
        fn = _TOOL_FNS.get(tool_name)
    try:
        if fn is None:
            return format_json({"success": False, "error": f"Unknown tool: {tool_name}"})
        return fn(tool_input, context)

    except ImportError as e:
        return format_json({"success": False, "error": f"Import error: {str(e)}"})
    except Exception as e:
        return format_json({"success": False, "error": str(e)})
