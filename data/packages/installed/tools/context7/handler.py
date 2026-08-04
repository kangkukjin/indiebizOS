"""
context7 패키지 핸들러
라이브러리/프레임워크 최신 공식 문서 검색 (Context7 REST API)
"""

import os
import json
import requests

API_BASE = "https://context7.com/api/v2"
API_KEY = os.environ.get("CONTEXT7_API_KEY", "")


def _headers():
    h = {"Accept": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def _search_library_id(library_name: str, query: str = "") -> dict:
    """라이브러리 이름 → Context7 라이브러리 목록 반환"""
    params = {
        "libraryName": library_name,
        "query": query or library_name,
    }
    try:
        r = requests.get(
            f"{API_BASE}/libs/search",
            params=params,
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        # API는 {"results": [...]} 형태로 반환
        if isinstance(data, dict):
            results = data.get("results", [])
        elif isinstance(data, list):
            results = data
        else:
            results = []
        return results if results else []
    except Exception as e:
        return {"error": str(e)}


def _get_docs(library_id: str, query: str) -> str:
    """라이브러리 ID + 쿼리 → 문서 내용 반환"""
    params = {
        "libraryId": library_id,
        "query": query,
        "type": "txt",  # LLM 친화적 텍스트 형태
    }
    try:
        r = requests.get(
            f"{API_BASE}/context",
            params=params,
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        return r.text
    except Exception as e:
        return f"문서 조회 실패: {e}"


# 2026-06-03 어휘 정리 — resolve_library/search_library_docs → [sense:devdocs]{op}.
# 디스패처 테이블은 op 함수 정의 뒤(파일 하단)에 있다 — music-player 동형.


def _resolve(library_name: str) -> str:
    """라이브러리 이름 → Context7 ID 후보 (상위 5)."""
    if not library_name:
        return json.dumps({"error": "library_name이 필요합니다."}, ensure_ascii=False)
    libs = _search_library_id(library_name)
    if isinstance(libs, dict) and "error" in libs:
        return json.dumps(libs, ensure_ascii=False)
    if not libs:
        return json.dumps({"error": f"'{library_name}'을 찾을 수 없습니다."}, ensure_ascii=False)
    results = [{"id": l.get("id", ""), "name": l.get("name", ""),
                "description": l.get("description", "")[:100]} for l in libs[:5]]
    # 레코드 통화(비파괴) — 라이브러리 목록 >> [table:document/spreadsheet]
    records = [{
        "title": r.get("name", ""),
        "meta": r.get("id", ""),
        "summary": r.get("description", "") if r.get("description", "") != r.get("name", "") else "",
        "url": "",
    } for r in results]
    return json.dumps({"query": library_name, "count": len(results), "libraries": results,
                       "items": records},
                      ensure_ascii=False, indent=2)


def _search(query: str, library_id: str, library_name: str) -> str:
    """문서 검색. library_id 직접 사용, 없으면 library_name으로 자동 해소."""
    if not query:
        return json.dumps({"error": "query가 필요합니다."}, ensure_ascii=False)
    lib_name = library_name
    if not library_id:
        if not library_name:
            return json.dumps({"error": "library_id 또는 library_name이 필요합니다."}, ensure_ascii=False)
        libs = _search_library_id(library_name, query)
        if isinstance(libs, dict) and "error" in libs:
            return json.dumps(libs, ensure_ascii=False)
        if not libs:
            return json.dumps({"error": f"'{library_name}' 라이브러리를 찾을 수 없습니다."}, ensure_ascii=False)
        library_id = libs[0].get("id", "")
        lib_name = libs[0].get("name", library_name)
        if not library_id:
            return json.dumps({"error": "라이브러리 ID를 얻지 못했습니다.", "results": libs[:3]}, ensure_ascii=False)
    docs = _get_docs(library_id, query)
    if not docs or docs.startswith("문서 조회 실패"):
        return json.dumps({"library": lib_name, "library_id": library_id, "error": docs}, ensure_ascii=False)
    # 문서 IR blocks(비파괴) — 문서 텍스트를 문단 블록으로. devdocs:search >> document. message=원문 보존.
    blocks = [{"type": "heading", "level": 1, "text": f"{lib_name} — {query}"}]
    for para in docs.split("\n\n"):
        para = para.strip()
        if para:
            blocks.append({"type": "paragraph", "text": para})
    # 단일 통화 items = 문서 IR(type+text 항목). 소비자 table:document가 type/text 감지.
    return json.dumps({"success": True, "library": lib_name, "library_id": library_id,
                       "message": docs, "items": blocks}, ensure_ascii=False)


# ── op 분기 함수 (진짜 디스패처 — tool_input 에서 인자 추출 후 기존 구현 호출) ──

def _op_resolve(tool_input: dict, context) -> str:
    return _resolve(tool_input.get("library_name") or tool_input.get("query", ""))


def _op_search(tool_input: dict, context) -> str:
    return _search(tool_input.get("query", ""),
                   tool_input.get("library_id", ""),
                   tool_input.get("library_name", ""))


# --check 가 이 dict 키로 src.ops.values 와 정확 비교 — 키 집합 변경 금지.
_OP_DISPATCHERS = {"devdocs_op": {"resolve": _op_resolve, "search": _op_search}}
_OP_DEFAULTS = {"devdocs_op": "resolve"}


def execute(tool_input: dict, context) -> str:
    """도구 실행 엔트리포인트 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name

    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.get("op") or _OP_DEFAULTS.get(tool_name, "")).strip()
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            return json.dumps({"error": f"알 수 없는 op '{op}'. 사용: resolve|search"}, ensure_ascii=False)
        return fn(tool_input, context)

    return json.dumps({"error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
