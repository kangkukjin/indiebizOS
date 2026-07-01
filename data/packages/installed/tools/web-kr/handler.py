"""
web-kr 패키지 핸들러 — 네이버 검색(한국어 콘텐츠 전용).

web 패키지에서 로케일 기준으로 분리됨: 보편·키없음 검색(ddg/crawl/news/newspaper/launch)은
web, 한국 전용 네이버 검색은 web-kr. 이렇게 나눠야 universal 로케일 설치에서 web(보편)이
살아남고, 네이버(kr, 키 필요)만 별도 kr 능력으로 분리 관리된다.

액션 이름·tool 문자열 불변(sense:search_naver / naver_search) — 소속 패키지만 이동.
"""

import os
import sys
import importlib.util
from pathlib import Path

# common 유틸리티 사용 (backend/common — 저장소 루트 기준 5단계 상위)
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.response_formatter import format_json

current_dir = Path(__file__).parent


def load_module(module_name):
    """같은 디렉토리의 모듈을 동적으로 로드"""
    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(tool_input: dict, context):
    """ToolContext 기반 핸들러."""
    tool_name = context.tool_name

    # 네이버 검색 (웹/뉴스/블로그/카페/지식인/책/백과/전문자료/쇼핑 통합)
    if tool_name == "naver_search":
        tool_naver = load_module("tool_naver_search")
        result = tool_naver.search_naver(
            query=tool_input.get("query", ""),
            type=tool_input.get("type", "webkr"),
            display=tool_input.get("display", 5),
            sort=tool_input.get("sort", "sim"),
        )
        return format_json(result)

    return format_json({"success": False, "error": f"Unknown tool: {tool_name}"})
