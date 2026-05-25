import os
import sys
import importlib.util
from pathlib import Path

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

current_dir = Path(__file__).parent

# 싱글턴 패턴 - 재생 프로세스/상태가 유지되도록
_MODULE_KEY = "tool_radio_singleton"

def load_tool_radio():
    if _MODULE_KEY in sys.modules:
        return sys.modules[_MODULE_KEY]
    module_path = current_dir / "tool_radio.py"
    spec = importlib.util.spec_from_file_location(_MODULE_KEY, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_KEY] = module
    spec.loader.exec_module(module)
    return module


def execute(tool_input: dict, context):
    """ToolContext 기반 신규 시그니처."""
    tool_name = context.tool_name
    radio = load_tool_radio()

    if tool_name == "search_radio":
        return radio.search_radio(
            name=tool_input.get("name"),
            tag=tool_input.get("tag"),
            country=tool_input.get("country"),
            state=tool_input.get("state"),
            language=tool_input.get("language"),
            order=tool_input.get("order"),
            bitrateMin=tool_input.get("bitrateMin"),
            limit=tool_input.get("limit", 10),
        )
    elif tool_name == "get_korean_radio":
        return radio.get_korean_radio(
            broadcaster=tool_input.get("broadcaster"),
        )
    elif tool_name == "play_radio":
        return radio.play_radio(
            station_id=tool_input.get("station_id"),
            stream_url=tool_input.get("stream_url"),
            volume=tool_input.get("volume", 70),
        )
    elif tool_name == "stop_radio":
        return radio.stop_radio()
    elif tool_name == "radio_status":
        return radio.radio_status()
    elif tool_name == "set_radio_volume":
        return radio.set_radio_volume(
            volume=tool_input.get("volume", 70),
        )
    elif tool_name == "get_radio_favorites":
        return radio.get_radio_favorites()
    elif tool_name == "save_radio_favorite":
        return radio.save_radio_favorite(
            station_id=tool_input.get("station_id"),
            name=tool_input.get("name"),
            stream_url=tool_input.get("stream_url"),
        )
    elif tool_name == "remove_radio_favorite":
        return radio.remove_radio_favorite(
            name=tool_input.get("name"),
        )
    else:
        raise ValueError(f"Unknown tool: {tool_name}")
