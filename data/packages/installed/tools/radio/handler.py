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


# 2026-05-28 dispatcher 표준화 — 단일 액션 op 키 메타데이터 (browser-action 패턴).
# 값은 None — 분기 로직은 아래 elif 안에 그대로 유지(refactor 없음).
# --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "radio_op": {"play": None, "stop": None},
    "radio_favorite_op": {"list": None, "add": None, "remove": None},
    # 2026-06-03 [sense:radio]{op} — 방송국 검색/탐색 (재생은 limbs:radio).
    "radio_search_op": {"search": None, "korean": None},
}
_OP_DEFAULTS = {"radio_op": "play", "radio_search_op": "search"}


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
    elif tool_name == "radio_search_op":
        # [sense:radio]{op} — search(전세계)/korean(한국 방송사)
        op = (tool_input.get("op") or _OP_DEFAULTS["radio_search_op"]).strip()
        if op == "korean":
            return radio.get_korean_radio(broadcaster=tool_input.get("broadcaster") or tool_input.get("query"))
        return radio.search_radio(
            name=tool_input.get("name") or tool_input.get("query"),
            tag=tool_input.get("tag"),
            country=tool_input.get("country"),
            state=tool_input.get("state"),
            language=tool_input.get("language"),
            order=tool_input.get("order"),
            bitrateMin=tool_input.get("bitrateMin"),
            limit=tool_input.get("limit", 10),
        )
    elif tool_name == "play_radio":
        return radio.play_radio(
            station_id=tool_input.get("station_id"),
            stream_url=tool_input.get("stream_url"),
            volume=tool_input.get("volume", 70),
            name=tool_input.get("name"),
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
    elif tool_name == "radio_op":
        # 2026-05-27 limbs 라운드 2: [limbs:radio]{op} 단일 액션 디스패치
        op = (tool_input.get("op") or "").strip() or "play"
        if op == "play":
            return radio.play_radio(
                station_id=tool_input.get("station_id"),
                stream_url=tool_input.get("stream_url"),
                volume=tool_input.get("volume", 70),
                name=tool_input.get("name"),
            )
        elif op == "stop":
            return radio.stop_radio()
        else:
            return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: play/stop"}
    elif tool_name == "radio_favorite_op":
        # 2026-05-27 단일 액션 통합: [limbs:radio_favorite]{op} → 내부 op 분기
        op = (tool_input.get("op") or "").strip()
        if op == "list":
            return radio.get_radio_favorites()
        elif op == "add":
            return radio.save_radio_favorite(
                station_id=tool_input.get("station_id"),
                name=tool_input.get("name"),
                stream_url=tool_input.get("stream_url"),
            )
        elif op == "remove":
            return radio.remove_radio_favorite(
                name=tool_input.get("name"),
                stream_url=tool_input.get("stream_url"),
            )
        else:
            return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: list/add/remove"}
    else:
        raise ValueError(f"Unknown tool: {tool_name}")
