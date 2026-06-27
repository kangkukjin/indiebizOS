"""
AI 경진대회 검색 (Kaggle Competitions API)
- Bearer 토큰 인증 (KAGGLE_API_TOKEN, auth_manager 'kaggle' 레지스트리)
- records 통화 반환 → 앱모드 card_list / engines:document 직결
"""
import os
import sys

_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key

# Kaggle competitions/list 가 허용하는 정렬값
_VALID_SORTS = {
    "grouped", "prize", "earliestDeadline", "latestDeadline",
    "numberOfTeams", "recentlyCreated",
}


def _to_records(items: list) -> list:
    """Kaggle 대회 → records 통화 [{title,meta,summary,url,image}].
    meta = 상금·주최·카테고리·마감일·참가팀 중 존재하는 것만 join."""
    records = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        meta_parts = []
        if it.get("reward"):
            meta_parts.append(f"상금 {it['reward']}")
        if it.get("organizationName"):
            meta_parts.append(it["organizationName"])
        if it.get("category"):
            meta_parts.append(it["category"])
        deadline = it.get("deadline") or ""
        if deadline:
            meta_parts.append(f"마감 {deadline[:10]}")
        if it.get("teamCount"):
            meta_parts.append(f"{it['teamCount']}팀")
        records.append({
            "title": it.get("title", "") or "",
            "meta": " · ".join(p for p in meta_parts if p),
            "summary": it.get("description", "") or "",
            "url": it.get("url") or it.get("ref", "") or "",
            "image": it.get("thumbnailImageUrl", "") or "",
        })
    return records


def search_kaggle(query: str = "", sort: str = "recentlyCreated",
                  category: str = "", count: int = 10):
    """Kaggle 경진대회 검색."""
    try:
        ok, err = check_api_key("kaggle")
        if not ok:
            return {"success": False, "error": err}

        params = {"page": "1"}
        if query:
            params["search"] = query
        if sort and sort in _VALID_SORTS:
            params["sortBy"] = sort
        if category:
            params["category"] = category

        result = api_call("kaggle", "/competitions/list",
                          params=params, timeout=25)
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result["error"]}

        # 응답은 대회 객체 리스트
        items = result if isinstance(result, list) else result.get("competitions", [])
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 10
        items = items[:max(1, count)]

        records = _to_records(items)
        return {
            "success": True,
            "source": "Kaggle Competitions",
            "keyword": query if query else "전체",
            "count": len(records),
            "items": records,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute(tool_input: dict, context):
    """ToolContext 기반 메인 핸들러."""
    if context.tool_name == "contest_search":
        return search_kaggle(
            tool_input.get("query") or tool_input.get("keyword", ""),
            tool_input.get("sort", "recentlyCreated"),
            tool_input.get("category", ""),
            tool_input.get("count", 10),
        )
    return {"success": False, "error": f"Unknown tool: {context.tool_name}"}
