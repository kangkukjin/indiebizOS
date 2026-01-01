import json
import os
import sys
import importlib.util
from pathlib import Path

# 같은 디렉토리의 모듈을 동적으로 로드
current_dir = Path(__file__).parent
tool_webcrawl_path = current_dir / "tool_webcrawl.py"

def load_tool_webcrawl():
    spec = importlib.util.spec_from_file_location("tool_webcrawl", tool_webcrawl_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def execute(tool_name, args, project_path=None):
    """
    IndieBiz OS용 실행 핸들러
    """
    if tool_name != "crawl_website":
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)

    url = args.get("url")
    max_length = args.get("max_length", 10000)

    if not url:
        return json.dumps({"success": False, "error": "URL이 제공되지 않았습니다."}, ensure_ascii=False)

    try:
        # tool_webcrawl.py의 crawl_website 함수 호출
        tool_webcrawl = load_tool_webcrawl()
        result = tool_webcrawl.crawl_website(url, max_length)

        # 결과를 JSON 문자열로 변환하여 반환
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
