import os
import sys
import json
import importlib.util
from pathlib import Path

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

# 같은 디렉토리의 모듈을 동적으로 로드
current_dir = Path(__file__).parent

# sys.modules에 등록하여 tool_loader.py가 handler.py를 여러 번 exec_module해도
# tool_youtube 모듈은 단 한 번만 로드되고 글로벌 상태(재생 프로세스, 큐 등)가 유지됨
_MODULE_KEY = "tool_youtube_singleton"

def load_tool_youtube():
    if _MODULE_KEY in sys.modules:
        return sys.modules[_MODULE_KEY]
    module_path = current_dir / "tool_youtube.py"
    spec = importlib.util.spec_from_file_location(_MODULE_KEY, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_KEY] = module
    spec.loader.exec_module(module)
    return module

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SETTINGS_PATH = os.path.join(BASE_DIR, "tool_settings.json")

# --- op 핸들러 (각 op = 파라미터 셰이핑 후 impl 함수 직접 호출·return) ---
# 2026-07-02: 옛 `tool_name = mapping[op]` 재할당+fall-through(변종2)를 직접-return(변종1)으로
# 전환. 레거시 내부 tool명(download_youtube_music 등)은 더 이상 tool_name으로 부활하지 않으므로
# tool.json에서도 은퇴 — music_op/video_op/search_youtube 3개만 IBL 진입점.

def _resolve_video_url(tool_input):
    url = tool_input.get('url')
    if not url:
        video_id = tool_input.get('video_id')
        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
    return url


def _resolve_languages(tool_input, default):
    lang = tool_input.get('language') or tool_input.get('languages')
    if isinstance(lang, str):
        return [lang]
    if isinstance(lang, list):
        return lang
    return default


def _op_download(tool_input, yt):
    # AI가 다양한 이름으로 파일명을 전달할 수 있으므로 유연하게 처리
    # ('output'은 가장 자연스러운 키 — 의식 에이전트가 자주 사용)
    fname = (tool_input.get('output_path')
             or tool_input.get('output')
             or tool_input.get('filename')
             or tool_input.get('path')
             or tool_input.get('file')
             or tool_input.get('name')
             or 'output.mp3')
    return yt.download_youtube_music(
        url=tool_input.get('url') or tool_input.get('query', ''),
        filename=fname,
        mode=tool_input.get('mode', 'server'))


def _op_info(tool_input, yt):
    url = _resolve_video_url(tool_input)
    if not url:
        return {"error": "url 또는 video_id 파라미터가 필요합니다."}
    return yt.get_youtube_info(url=url)


def _op_transcript(tool_input, yt):
    url = _resolve_video_url(tool_input)
    if not url:
        return {"error": "url 또는 video_id 파라미터가 필요합니다."}
    return yt.get_youtube_transcript(url=url, languages=_resolve_languages(tool_input, ['ko', 'en']))


def _op_languages(tool_input, yt):
    url = _resolve_video_url(tool_input)
    if not url:
        return {"error": "url 또는 video_id 파라미터가 필요합니다."}
    return yt.list_available_transcripts(url=url)


def _op_summarize(tool_input, yt):
    return yt.summarize_youtube(
        url=tool_input['url'],
        summary_length=tool_input.get('summary_length', 3000),
        languages=_resolve_languages(tool_input, None))  # None=자동 선택


def _op_play(tool_input, yt):
    return yt.play_youtube(
        query=tool_input.get('query', ''),
        mode=tool_input.get('mode', 'audio'),
        count=tool_input.get('count', 5))


def _op_add(tool_input, yt):
    return yt.add_to_queue(query=tool_input.get('query', ''), count=tool_input.get('count', 3))


def _op_skip(tool_input, yt):
    return yt.skip_youtube()


def _op_queue(tool_input, yt):
    return yt.get_queue()


def _op_stop(tool_input, yt):
    return yt.stop_youtube()


def _direct_search(tool_input, yt):
    result = yt.search_youtube(
        query=tool_input.get('query', ''),
        count=tool_input.get('count', 5))
    # 단일 통화 — native results(title/channel/duration/video_id/url 등 풍부)를 items로.
    # (옛 records 5칸 변환은 video_id/duration 등을 버려 손실적이라 은퇴.)
    if isinstance(result, dict) and isinstance(result.get('results'), list):
        result['items'] = result.pop('results')
    return result


# 2026-05-28 dispatcher 표준화: _OP_DISPATCHERS 두 단계 dict (op → 핸들러 함수).
#   --check 는 inner dict 의 키(op)만 src.ops.values 와 AST 비교(값 타입 무관).
_OP_DISPATCHERS = {
    # [limbs:music]{op} — 유튜브 음악 재생/큐
    "music_op": {
        "play": _op_play,
        "add": _op_add,
        "skip": _op_skip,
        "queue": _op_queue,
        "stop": _op_stop,
        "download": _op_download,
    },
    # [sense:video]{op} — 유튜브 동영상 조회
    "video_op": {
        "info": _op_info,
        "transcript": _op_transcript,
        "languages": _op_languages,
        "summarize": _op_summarize,
    },
}
_OP_DEFAULTS = {"music_op": "play", "video_op": "info"}
# op 없는 직접 액션(IBL 진입점 = tool명 그대로)
_DIRECT_ACTIONS = {"search_youtube": _direct_search}


def execute(tool_input: dict, context):
    """ToolContext 기반 신규 시그니처."""
    tool_name = context.tool_name
    tool_youtube = load_tool_youtube()

    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.pop('op', '') or '').strip() or _OP_DEFAULTS.get(tool_name, '')
        mapping = _OP_DISPATCHERS[tool_name]
        if op not in mapping:
            return {"error": f"알 수 없는 op '{op}' ({tool_name}). 사용 가능: {sorted(mapping.keys())}"}
        return mapping[op](tool_input, tool_youtube)

    if tool_name in _DIRECT_ACTIONS:
        return _DIRECT_ACTIONS[tool_name](tool_input, tool_youtube)

    raise ValueError(f'Unknown tool: {tool_name}')
