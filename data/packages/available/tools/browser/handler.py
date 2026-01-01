"""
browser 도구 핸들러
"""
import json
import os
import webbrowser
from pathlib import Path


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    브라우저 열기 도구

    Args:
        tool_name: 도구 이름 (이 패키지에서는 "open_in_browser")
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로

    Returns:
        JSON 형식의 결과 문자열
    """
    if tool_name == "open_in_browser":
        url = tool_input.get("url", "")
        try:
            # 로컬 파일인 경우 file:// 프로토콜 추가
            if not url.startswith(("http://", "https://", "file://")):
                file_path = Path(project_path) / url if not os.path.isabs(url) else Path(url)
                if file_path.exists():
                    url = f"file://{file_path.absolute()}"

            webbrowser.open(url)
            return json.dumps({"success": True, "message": f"브라우저에서 열림: {url}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
