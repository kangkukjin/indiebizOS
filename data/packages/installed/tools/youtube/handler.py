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

# 2026-05-28 dispatcher 표준화: browser-action 패턴 통일 (_OP_DISPATCHERS 두 단계 dict).
_OP_DISPATCHERS = {
    "music_op": {
        "play": "play_youtube",
        "add": "add_to_queue",
        "skip": "skip_youtube",
        "queue": "get_queue",
        "stop": "stop_youtube",
        "download": "download_youtube_music",
    },
    # 2026-06-03 어휘 정리: [sense:video]{op} — 유튜브 동영상 조회.
    "video_op": {
        "info": "get_youtube_info",
        "transcript": "get_youtube_transcript",
        "languages": "list_available_transcripts",
        "summarize": "summarize_video",
    },
}
_OP_DEFAULTS = {"music_op": "play", "video_op": "info"}


def execute(tool_input: dict, context):
    """ToolContext 기반 신규 시그니처."""
    tool_name = context.tool_name
    tool_youtube = load_tool_youtube()

    # 2026-05-27 limbs 라운드 2: [limbs:music]{op} 단일 액션 디스패치
    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.pop('op', '') or '').strip() or _OP_DEFAULTS.get(tool_name, '')
        mapping = _OP_DISPATCHERS[tool_name]
        if op not in mapping:
            return {"error": f"알 수 없는 op '{op}' ({tool_name}). 사용 가능: {sorted(mapping.keys())}"}
        tool_name = mapping[op]

    if tool_name == 'download_youtube_music':
        # AI가 다양한 이름으로 파일명을 전달할 수 있으므로 유연하게 처리
        # ('output'은 가장 자연스러운 키 — 의식 에이전트가 자주 사용)
        fname = (tool_input.get('output_path')
                 or tool_input.get('output')
                 or tool_input.get('filename')
                 or tool_input.get('path')
                 or tool_input.get('file')
                 or tool_input.get('name')
                 or 'output.mp3')
        return tool_youtube.download_youtube_music(
            url=tool_input.get('url') or tool_input.get('query', ''),
            filename=fname,
            mode=tool_input.get('mode', 'server'))
    elif tool_name == 'get_youtube_info':
        # url 또는 video_id 파라미터 지원 (transcript와 동일 해소)
        url = tool_input.get('url')
        if not url:
            video_id = tool_input.get('video_id')
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                return {"error": "url 또는 video_id 파라미터가 필요합니다."}
        return tool_youtube.get_youtube_info(url=url)
    elif tool_name == 'get_youtube_transcript':
        # url 또는 video_id 파라미터 지원
        url = tool_input.get('url')
        if not url:
            video_id = tool_input.get('video_id')
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                return {"error": "url 또는 video_id 파라미터가 필요합니다."}
        # language를 languages 리스트로 변환
        lang = tool_input.get('language') or tool_input.get('languages')
        if isinstance(lang, str):
            languages = [lang]
        elif isinstance(lang, list):
            languages = lang
        else:
            languages = ['ko', 'en']
        return tool_youtube.get_youtube_transcript(url=url, languages=languages)
    elif tool_name == 'list_available_transcripts':
        # url 또는 video_id 파라미터 지원
        url = tool_input.get('url')
        if not url:
            video_id = tool_input.get('video_id')
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                return {"error": "url 또는 video_id 파라미터가 필요합니다."}
        return tool_youtube.list_available_transcripts(url=url)
    elif tool_name == 'summarize_video':
        # summary_length와 languages 파라미터 전달
        summary_length = tool_input.get('summary_length', 3000)
        lang = tool_input.get('language') or tool_input.get('languages')
        if isinstance(lang, str):
            languages = [lang]
        elif isinstance(lang, list):
            languages = lang
        else:
            languages = None  # 자동 선택
        return tool_youtube.summarize_youtube(
            url=tool_input['url'],
            summary_length=summary_length,
            languages=languages
        )
    elif tool_name == 'search_youtube':
        result = tool_youtube.search_youtube(
            query=tool_input.get('query', ''),
            count=tool_input.get('count', 5),
        )
        # 레코드 통화 부착(비파괴) — results 목록을 records로. >> 파이프가 자동으로 흐름.
        if isinstance(result, dict) and isinstance(result.get('results'), list):
            records = []
            for r in result['results']:
                meta_parts = [r.get('channel'), r.get('duration')]
                rec = {
                    'title': r.get('title', ''),
                    'meta': ' · '.join(p for p in meta_parts if p),
                    'summary': '',
                    'url': r.get('url', ''),
                }
                records.append(rec)
            result['records'] = records
        return result
    elif tool_name == 'play_youtube':
        return tool_youtube.play_youtube(
            query=tool_input.get('query', ''),
            mode=tool_input.get('mode', 'audio'),
            count=tool_input.get('count', 5),
        )
    elif tool_name == 'add_to_queue':
        return tool_youtube.add_to_queue(
            query=tool_input.get('query', ''),
            count=tool_input.get('count', 3),
        )
    elif tool_name == 'skip_youtube':
        return tool_youtube.skip_youtube()
    elif tool_name == 'get_queue':
        return tool_youtube.get_queue()
    elif tool_name == 'stop_youtube':
        return tool_youtube.stop_youtube()
    else:
        raise ValueError(f'Unknown tool: {tool_name}')
