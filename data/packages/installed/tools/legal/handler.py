"""
법률 정보 검색 도구 (국가법령정보센터 API)

Phase 0 마이그레이션: common 유틸리티 사용
"""
import sys
import os

# backend/common 모듈 경로 추가
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import get_api_key


# 패키지 디렉토리 (config.json fallback용)
_PACKAGE_DIR = os.path.dirname(__file__)

# 법률 API 대상 매핑
_TARGET_MAP = {
    "search_legal_info": None,       # tool_input에서 target 직접 지정
    "get_legal_detail": None,        # tool_input에서 target 직접 지정
    "search_laws": "law",
    "get_law_detail": "law",
    "search_precedents": "prec",
    "get_precedent_detail": "prec",
}


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """법률 패키지 도구 실행 핸들러"""
    api_key = get_api_key("LAW_API_KEY", package_dir=_PACKAGE_DIR)
    if not api_key:
        return "에러: Law API 키가 설정되지 않았습니다. 패키지 폴더의 config.json에 'api_key'를 입력하거나 LAW_API_KEY 환경 변수를 설정해주세요."

    if tool_name in ("search_legal_info", "search_laws", "search_precedents"):
        target = _TARGET_MAP.get(tool_name) or tool_input.get("target", "law")
        result = api_call(
            "law", "/lawSearch.do",
            params={
                "OC": api_key,
                "target": target,
                "type": "JSON",
                "query": tool_input.get("query"),
            },
            raw_response=True,
        )
        return result if isinstance(result, str) else str(result)

    elif tool_name in ("get_legal_detail", "get_law_detail", "get_precedent_detail"):
        target = _TARGET_MAP.get(tool_name) or tool_input.get("target", "law")
        item_id = tool_input.get("id") or tool_input.get("law_id") or tool_input.get("precedent_id")
        result = api_call(
            "law", "/lawService.do",
            params={
                "OC": api_key,
                "target": target,
                "type": "JSON",
                "ID": item_id,
            },
            raw_response=True,
        )
        return result if isinstance(result, str) else str(result)

    return f"알 수 없는 도구: {tool_name}"
