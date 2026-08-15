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


# ── op 분기 함수 (music-player 동형 — 진짜 디스패처) ─────────────────────

def _op_run(tool_input: dict, context) -> str:
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


def _op_sites(tool_input: dict, context) -> str:
    from collector import manage_sites
    result = manage_sites(
        action=tool_input.get("action", "list"),
        site_id=tool_input.get("site_id"),
        guide_code=tool_input.get("guide_code"),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


def _op_query(tool_input: dict, context) -> str:
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
    # 통화: db 결과의 raw items 가 이미 단일 통화 {items:[...]} — 항목 내부는 열림(관습).
    # (옛 코드에 records 뷰(recs)를 만들고 부착하지 않던 죽은 블록이 있었음 — 2026-08-05
    #  감사 ① 전환 중 발견·삭제. records 키는 컷오버로 은퇴(common/currency.py)라 부착도 부적절.)
    return json.dumps(result, ensure_ascii=False, indent=2)


# 2026-06-03 어휘 정리: [sense:collect]{op} 단일 액션. op=run은 backend 크롤 엔진 위임.
# --check 가 이 dict 키로 src.ops.values 와 정확 비교 — 키 집합 변경 금지.
_OP_DISPATCHERS = {"collect_op": {"run": _op_run, "sites": _op_sites, "query": _op_query}}
_OP_DEFAULTS = {"collect_op": "run"}


def execute(tool_input: dict, context) -> str:
    """웹 수집 도구 실행 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = (tool_input.get("op") or _OP_DEFAULTS.get(tool_name, "")).strip()
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if fn is None:
                return json.dumps({"success": False, "error": f"알 수 없는 op '{op}'. 사용: run|sites|query"}, ensure_ascii=False)
            return fn(tool_input, context)

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
