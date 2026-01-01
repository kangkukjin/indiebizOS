"""
time 도구 핸들러
"""
import json
from datetime import datetime


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    도구 실행

    Args:
        tool_name: 도구 이름 (이 패키지에서는 "get_current_time")
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로

    Returns:
        JSON 형식의 결과 문자열
    """
    if tool_name == "get_current_time":
        now = datetime.now()
        return json.dumps({
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
        }, ensure_ascii=False)

    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
