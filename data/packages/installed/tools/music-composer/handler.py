"""
Music Composer - Handler (도구 디스패처)
"""

import os
import sys
import json

# 패키지 내부 모듈 임포트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from composer import abc_to_midi, midi_to_audio, compose_and_export, search_abc_tunes, get_abc_tune


def execute(tool_name: str, args: dict, project_path: str = None) -> str:
    """
    도구 실행 디스패처

    Args:
        tool_name: 실행할 도구 이름
        args: 도구 인자
        project_path: 프로젝트 경로 (출력 파일 저장 위치)

    Returns:
        JSON 문자열
    """
    if tool_name == "abc_to_midi":
        return abc_to_midi(args, project_path)
    elif tool_name == "midi_to_audio":
        return midi_to_audio(args, project_path)
    elif tool_name == "compose_and_export":
        return compose_and_export(args, project_path)
    elif tool_name == "search_abc_tunes":
        return search_abc_tunes(args, project_path)
    elif tool_name == "get_abc_tune":
        return get_abc_tune(args, project_path)
    else:
        return json.dumps({"error": f"알 수 없는 도구: {tool_name}"})
