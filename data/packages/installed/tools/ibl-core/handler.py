"""
IBL Core 도구 핸들러

ibl_* 도구 호출을 ibl_engine.py로 위임합니다.
"""
import sys
import os

# backend 모듈 경로 추가
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from ibl_engine import execute_ibl

# 도구 이름 → 현재 노드 매핑 (6개 노드: system, interface, messenger, source, stream, forge)
# ibl_* 개별 도구는 레거시이며 현재 execute_ibl 단일 도구만 사용됨.
# 이 매핑은 혹시 ibl_* 도구가 호출될 경우를 위한 폴백.
_TOOL_NODE_MAP = {
    # 현재 노드 직접 매핑
    "ibl_system": "system", "ibl_interface": "interface",
    "ibl_messenger": "messenger", "ibl_source": "source",
    "ibl_stream": "stream", "ibl_forge": "forge",
    # 구 도구명 → 현재 노드 (직접 매핑, 이중 변환 없음)
    "ibl_android": "interface", "ibl_browser": "interface", "ibl_desktop": "interface",
    "ibl_youtube": "stream", "ibl_radio": "stream",
    "ibl_informant": "source", "ibl_librarian": "source",
    "ibl_finance": "source", "ibl_culture": "source", "ibl_study": "source",
    "ibl_legal": "source", "ibl_statistics": "source",
    "ibl_commerce": "source", "ibl_location": "source",
    "ibl_web": "source", "ibl_info": "source",
    "ibl_photo": "source", "ibl_blog": "source",
    "ibl_memory": "source", "ibl_health": "source",
    "ibl_cctv": "source", "ibl_realestate": "source",
    "ibl_creator": "forge", "ibl_webdev": "forge", "ibl_design": "forge",
    "ibl_orchestrator": "system", "ibl_workflow": "system",
    "ibl_automation": "system", "ibl_output": "system",
    "ibl_user": "system", "ibl_filesystem": "system", "ibl_fs": "system",
    # 기타 레거시
    "ibl_channel": "messenger", "ibl_contact": "messenger",
    "ibl_media": "forge", "ibl_viz": "forge",
    "ibl_api": "source", "ibl_shopping": "source",
    "ibl_startup": "source", "ibl_hosting": "forge",
    "ibl_webbuilder": "forge", "ibl_storage": "system",
    "ibl_event": "system", "ibl_agent": "system",
}


def execute(tool_name: str, tool_input: dict, project_path: str = ".", agent_id: str = None) -> str:
    """IBL 노드 도구 실행"""
    # 노드 기반 라우팅 (현재 노드명으로 직접 매핑)
    node = _TOOL_NODE_MAP.get(tool_name)
    if not node:
        return f"알 수 없는 IBL 도구: {tool_name}"

    # 노드 정보를 tool_input에 주입
    tool_input["_node"] = node

    result = execute_ibl(tool_input, project_path, agent_id)

    # dict 결과는 그대로 반환 (system_tools.py가 JSON 변환 처리)
    return result
