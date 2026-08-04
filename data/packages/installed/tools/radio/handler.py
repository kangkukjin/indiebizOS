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


# ── op 분기 함수 (music-player 동형 — 진짜 디스패처) ─────────────────────
# load_tool_radio() 는 sys.modules 싱글턴이라 각 함수에서 재호출해도 비용 0.

def _op_search(tool_input: dict, context):
    """[sense:radio]{op:search} — 전세계 방송국 검색."""
    radio = load_tool_radio()
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


def _op_korean(tool_input: dict, context):
    """[sense:radio]{op:korean} — 한국 방송사."""
    radio = load_tool_radio()
    return radio.get_korean_radio(broadcaster=tool_input.get("broadcaster") or tool_input.get("query"))


def _op_play(tool_input: dict, context):
    # 2026-05-27 limbs 라운드 2: [limbs:radio]{op} 단일 액션 디스패치
    radio = load_tool_radio()
    return radio.play_radio(
        station_id=tool_input.get("station_id"),
        stream_url=tool_input.get("stream_url"),
        volume=tool_input.get("volume", 70),
        name=tool_input.get("name"),
        # 출력지(client=보고 있는 기기 / host=이 기계). 미지정이면 표면이 정한다.
        mode=tool_input.get("mode"),
    )


def _op_stop(tool_input: dict, context):
    radio = load_tool_radio()
    return radio.stop_radio()


def _op_favorite_list(tool_input: dict, context):
    # 2026-05-27 단일 액션 통합: [limbs:radio_favorite]{op} → 내부 op 분기
    radio = load_tool_radio()
    return radio.get_radio_favorites()


def _op_favorite_add(tool_input: dict, context):
    radio = load_tool_radio()
    return radio.save_radio_favorite(
        station_id=tool_input.get("station_id"),
        name=tool_input.get("name"),
        stream_url=tool_input.get("stream_url"),
    )


def _op_favorite_remove(tool_input: dict, context):
    radio = load_tool_radio()
    return radio.remove_radio_favorite(
        name=tool_input.get("name"),
        stream_url=tool_input.get("stream_url"),
    )


# 2026-05-28 dispatcher 표준화 → 2026-08-05 진짜 디스패처로 전환 (music-player 동형).
# --check 가 이 dict 키로 src.ops.values 와 정확 비교 — 키 집합 변경 금지.
_OP_DISPATCHERS = {
    "radio_op": {"play": _op_play, "stop": _op_stop},
    "radio_favorite_op": {"list": _op_favorite_list, "add": _op_favorite_add, "remove": _op_favorite_remove},
    # 2026-06-03 [sense:radio]{op} — 방송국 검색/탐색 (재생은 limbs:radio).
    "radio_search_op": {"search": _op_search, "korean": _op_korean},
}
_OP_DEFAULTS = {"radio_op": "play", "radio_search_op": "search"}

# 알 수 없는 op — 옛 체인 동작 그대로:
#  - radio_search_op 는 korean 외 전부 search 로 흘렀다(fallthrough) → search 폴백 유지.
#  - radio_op / radio_favorite_op 는 기존 오류 메시지 그대로.
_OP_FALLBACKS = {"radio_search_op": "search"}
_OP_USAGE = {"radio_op": "play/stop", "radio_favorite_op": "list/add/remove"}


def execute(tool_input: dict, context):
    """ToolContext 기반 신규 시그니처."""
    tool_name = context.tool_name
    radio = load_tool_radio()

    if tool_name in _OP_DISPATCHERS:
        default = _OP_DEFAULTS.get(tool_name, "")
        # 공백 op 도 기본 op 로 (옛 radio_op 의 `.strip() or "play"` 동작 보존)
        op = (tool_input.get("op") or default).strip() or default
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            fallback = _OP_FALLBACKS.get(tool_name)
            if fallback:
                fn = _OP_DISPATCHERS[tool_name][fallback]
            else:
                return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: {_OP_USAGE[tool_name]}"}
        return fn(tool_input, context)
    elif tool_name == "radio_status":
        return radio.radio_status()
    elif tool_name == "set_radio_volume":
        return radio.set_radio_volume(
            volume=tool_input.get("volume", 70),
        )
    else:
        raise ValueError(f"Unknown tool: {tool_name}")
