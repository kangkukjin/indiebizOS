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


def execute(tool_name: str, params: dict, project_path: str = ".") -> str:
    """도구 실행 엔트리포인트"""

    if tool_name == "search_library_docs":
        query = params.get("query", "")
        library_name = params.get("library_name", "")

        if not query or not library_name:
            return json.dumps({"error": "query와 library_name이 필요합니다."}, ensure_ascii=False)

        # 1단계: 라이브러리 ID 찾기
        libs = _search_library_id(library_name, query)

        if isinstance(libs, dict) and "error" in libs:
            return json.dumps(libs, ensure_ascii=False)

        if not libs:
            return json.dumps({"error": f"'{library_name}' 라이브러리를 찾을 수 없습니다."}, ensure_ascii=False)

        # 첫 번째 결과 사용
        lib = libs[0]
        library_id = lib.get("id", "")

        if not library_id:
            return json.dumps({"error": "라이브러리 ID를 얻지 못했습니다.", "results": libs[:3]}, ensure_ascii=False)

        # 2단계: 문서 가져오기
        docs = _get_docs(library_id, query)

        if not docs or docs.startswith("문서 조회 실패"):
            return json.dumps({
                "library": lib.get("name", library_name),
                "library_id": library_id,
                "error": docs,
            }, ensure_ascii=False)

        return docs

    elif tool_name == "resolve_library":
        library_name = params.get("library_name", "")

        if not library_name:
            return json.dumps({"error": "library_name이 필요합니다."}, ensure_ascii=False)

        libs = _search_library_id(library_name)

        if isinstance(libs, dict) and "error" in libs:
            return json.dumps(libs, ensure_ascii=False)

        if not libs:
            return json.dumps({"error": f"'{library_name}'을 찾을 수 없습니다."}, ensure_ascii=False)

        # 상위 5개 반환
        results = []
        for lib in libs[:5]:
            results.append({
                "id": lib.get("id", ""),
                "name": lib.get("name", ""),
                "description": lib.get("description", "")[:100],
            })

        return json.dumps({
            "query": library_name,
            "count": len(results),
            "libraries": results,
        }, ensure_ascii=False, indent=2)

    else:
        return json.dumps({"error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
