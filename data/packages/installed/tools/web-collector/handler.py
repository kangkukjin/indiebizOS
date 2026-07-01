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

# 2026-06-03 어휘 정리: [sense:collect]{op} 단일 액션. op=run은 backend 크롤 엔진 위임.
_OP_DISPATCHERS = {"collect_op": {"run": None, "sites": None, "query": None}}
_OP_DEFAULTS = {"collect_op": "run"}


def _collect_op(tool_input: dict) -> str:
    op = (tool_input.get("op") or _OP_DEFAULTS["collect_op"]).strip()
    if op == "run":
        # backend 크롤 엔진 위임 (패키지→backend, 정상 방향)
        bd = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "..", "..", "..", "backend"))
        if bd not in sys.path:
            sys.path.insert(0, bd)
        from web_collector import collect_ad_hoc, collect_with_profile, list_profiles
        source = tool_input.get("source") or tool_input.get("url") or tool_input.get("profile") or ""
        if source and source.startswith(("http://", "https://")):
            result = collect_ad_hoc(source, tool_input.get("selectors", {}), tool_input.get("max_items", 20))
        elif source:
            result = collect_with_profile(source, tool_input)
        else:
            profiles = list_profiles()
            result = {"message": "source(프로필 ID 또는 URL)를 지정하세요.",
                      "available_profiles": profiles, "count": len(profiles)}
        return json.dumps(result, ensure_ascii=False, indent=2)
    if op == "sites":
        from collector import manage_sites
        result = manage_sites(
            action=tool_input.get("action", "list"),
            site_id=tool_input.get("site_id"),
            guide_code=tool_input.get("guide_code"),
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    if op == "query":
        import collector_db as db
        action = tool_input.get("action", "search")
        if action == "stats":
            result = db.get_stats(site_id=tool_input.get("site_id"))
        elif action == "recent":
            result = db.get_recent(site_id=tool_input.get("site_id"), limit=tool_input.get("limit", 20))
        elif action == "detail":
            item_id = tool_input.get("item_id")
            result = db.get_item_detail(int(item_id)) if item_id else {"success": False, "error": "item_id가 필요합니다."}
        elif action == "delete":
            item_id = tool_input.get("item_id")
            result = db.delete_item(int(item_id)) if item_id else {"success": False, "error": "item_id가 필요합니다."}
        else:
            result = db.search_items(query=tool_input.get("query"), site_id=tool_input.get("site_id"),
                                     limit=tool_input.get("limit", 20), offset=tool_input.get("offset", 0))
        # 레코드 통화(비파괴) — 수집 아이템 목록 >> 파이프. data 스키마가 사이트마다 달라 best-effort.
        if isinstance(result, dict) and isinstance(result.get("items"), list):
            recs = []
            for it in result["items"]:
                if not isinstance(it, dict):
                    continue
                dat = it.get("data") if isinstance(it.get("data"), dict) else {}
                title = dat.get("title") or dat.get("name") or dat.get("location") or it.get("item_key") or ""
                summary = " · ".join(f"{k}:{v}" for k, v in list(dat.items())[:4]) if dat else ""
                recs.append({
                    "title": str(title),
                    "meta": " · ".join(x for x in [it.get("site_id"), it.get("collected_at")] if x),
                    "summary": summary[:200],
                    "url": dat.get("url") or dat.get("link") or "",
                })
        return json.dumps(result, ensure_ascii=False, indent=2)
    return json.dumps({"success": False, "error": f"알 수 없는 op '{op}'. 사용: run|sites|query"}, ensure_ascii=False)


def execute(tool_input: dict, context) -> str:
    """웹 수집 도구 실행 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    try:
        if tool_name == "collect_op":
            return _collect_op(tool_input)

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
