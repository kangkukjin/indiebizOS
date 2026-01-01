"""
python-exec 도구 핸들러
"""
import json
import subprocess


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    Python 코드 실행 도구

    Args:
        tool_name: 도구 이름 (이 패키지에서는 "execute_python")
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로

    Returns:
        실행 결과 문자열
    """
    if tool_name == "execute_python":
        code = tool_input.get("code", "")
        try:
            result = subprocess.run(
                ["python3", "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_path
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            return output if output else "(실행 완료, 출력 없음)"
        except subprocess.TimeoutExpired:
            return "실행 시간 초과 (30초)"
        except Exception as e:
            return f"실행 오류: {str(e)}"

    return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
