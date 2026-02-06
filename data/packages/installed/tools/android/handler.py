import sys
from pathlib import Path

# 현재 디렉토리를 sys.path에 추가하여 tool_android를 import할 수 있도록 함
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from tool_android import use_tool

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> dict:
    """
    안드로이드 도구 패키지 핸들러
    모든 요청을 tool_android.py의 use_tool로 위임합니다.
    """
    # 프로젝트 경로 정보를 컨텍스트로 활용할 수 있도록 입력에 추가 (필요 시)
    if project_path:
        tool_input["_project_path"] = project_path

    return use_tool(tool_name, tool_input)
