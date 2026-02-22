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

def execute(tool_name: str, arguments: dict, project_path: str = None):
    tool_youtube = load_tool_youtube()

    if tool_name == 'download_youtube_music':
        # AI가 다양한 이름으로 파일명을 전달할 수 있으므로 유연하게 처리
        fname = (arguments.get('output_path')
                 or arguments.get('filename')
                 or arguments.get('path')
                 or arguments.get('file')
                 or arguments.get('name')
                 or 'output.mp3')
        return tool_youtube.download_youtube_music(url=arguments['url'], filename=fname)
    elif tool_name == 'get_youtube_info':
        return tool_youtube.get_youtube_info(url=arguments['url'])
    elif tool_name == 'get_youtube_transcript':
        # language를 languages 리스트로 변환
        lang = arguments.get('language') or arguments.get('languages')
        if isinstance(lang, str):
            languages = [lang]
        elif isinstance(lang, list):
            languages = lang
        else:
            languages = ['ko', 'en']
        return tool_youtube.get_youtube_transcript(url=arguments['url'], languages=languages)
    elif tool_name == 'list_available_transcripts':
        return tool_youtube.list_available_transcripts(url=arguments['url'])
    elif tool_name == 'summarize_youtube':
        # summary_length와 languages 파라미터 전달
        summary_length = arguments.get('summary_length', 3000)
        lang = arguments.get('language') or arguments.get('languages')
        if isinstance(lang, str):
            languages = [lang]
        elif isinstance(lang, list):
            languages = lang
        else:
            languages = None  # 자동 선택
        return tool_youtube.summarize_youtube(
            url=arguments['url'],
            summary_length=summary_length,
            languages=languages
        )
    elif tool_name == 'search_youtube':
        return tool_youtube.search_youtube(
            query=arguments.get('query', ''),
            count=arguments.get('count', 5),
        )
    elif tool_name == 'play_youtube':
        return tool_youtube.play_youtube(
            query=arguments.get('query', ''),
            mode=arguments.get('mode', 'audio'),
            count=arguments.get('count', 5),
        )
    elif tool_name == 'add_to_queue':
        return tool_youtube.add_to_queue(
            query=arguments.get('query', ''),
            count=arguments.get('count', 3),
        )
    elif tool_name == 'skip_youtube':
        return tool_youtube.skip_youtube()
    elif tool_name == 'get_queue':
        return tool_youtube.get_queue()
    elif tool_name == 'stop_youtube':
        return tool_youtube.stop_youtube()
    else:
        raise ValueError(f'Unknown tool: {tool_name}')
