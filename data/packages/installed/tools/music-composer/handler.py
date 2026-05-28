"""
Music Composer - Handler (도구 디스패처)
"""

import os
import sys
import json

# 패키지 내부 모듈 임포트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from composer import abc_to_midi, midi_to_audio, compose_and_export, search_abc_tunes, get_abc_tune


def execute(tool_input: dict, context) -> str:
    """도구 실행 디스패처 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    project_path = context.project_path

    # 2026-05-27 통합: music {stage} 단일 진입점
    if tool_name == "music":
        stage = (tool_input.get("stage") or "full").lower()
        if stage == "midi_only":
            return abc_to_midi(tool_input, project_path)
        elif stage == "audio_only":
            return midi_to_audio(tool_input, project_path)
        return compose_and_export(tool_input, project_path)

    if tool_name == "abc_to_midi":
        return abc_to_midi(tool_input, project_path)
    elif tool_name == "midi_to_audio":
        return midi_to_audio(tool_input, project_path)
    elif tool_name == "compose_and_export":
        return compose_and_export(tool_input, project_path)
    elif tool_name == "search_abc_tunes":
        return search_abc_tunes(tool_input, project_path)
    elif tool_name == "get_abc_tune":
        return get_abc_tune(tool_input, project_path)
    else:
        return json.dumps({"error": f"알 수 없는 도구: {tool_name}"})
