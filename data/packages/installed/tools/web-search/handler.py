import json
import os
import importlib.util
from pathlib import Path

# 같은 디렉토리의 모듈을 동적으로 로드
current_dir = Path(__file__).parent

def load_module(module_name):
    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def execute(tool_name: str, params: dict, project_path: str = None):
    """
    IndieBiz OS에서 도구를 호출할 때 실행되는 메인 핸들러
    """
    if tool_name == "ddgs_search":
        tool_ddgs = load_module("tool_ddgs_search")
        query = params.get("query")
        count = params.get("count", 5)
        country = params.get("country", "kr-kr")
        return tool_ddgs.search_web(query, count, country)

    elif tool_name == "google_news_search":
        tool_news = load_module("tool_google_news")
        query = params.get("query")
        count = params.get("count", 10)
        language = params.get("language", "ko")
        return tool_news.search_google_news(query, count, language)

    else:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }

def get_definitions():
    """모든 도구 정의 반환"""
    tool_ddgs = load_module("tool_ddgs_search")
    tool_news = load_module("tool_google_news")
    return [tool_ddgs.get_tool_definition(), tool_news.get_tool_definition()]
