"""
IBL Core 도구 핸들러

이 패키지는 `execute_ibl` 도구 **스키마의 집**이다(에이전트에게 IBL 문법을 안내).
execute_ibl 의 실제 실행은 backend/system_tools._execute_ibl_unified 가 담당하므로
이 핸들러를 거치지 않는다.

2026-06-03 정리: 옛 노드 기반 ibl_* 개별 도구(40개)는 현재 시스템(에이전트는 execute_ibl
단일 도구만 사용, 5노드 액션은 ibl_access 가 별도 XML로 노출)에서 호출되지 않아 제거했다.
"""


def execute(tool_input: dict, context) -> str:
    """레거시 ibl_* 도구는 제거됨. execute_ibl 은 system_tools 가 직접 실행한다."""
    return f"미지원 도구: {context.tool_name} (ibl_* 레거시 도구는 제거됨; execute_ibl 사용)"
